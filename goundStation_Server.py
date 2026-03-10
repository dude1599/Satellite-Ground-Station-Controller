import socket
import struct
import threading
import time

# === 지상국 : Client (수신 및 중계 서버) ===
# TC : 0x10=SAFE, 0x20=NOMINAL / TM : 0x05 / 응답 : 0x00=ACK, 0xFF=NAK

# 위성 주소 설정
SAT_IP = "127.0.0.1"
SAT_PORT = 9000
LOCAL_CMD_PORT = 8000 # 운영자 터미널과 연결할 내부 포트

tc_seq = 1  # 지상국이 보내는 명령의 시퀀스 번호

def crc16_xmodem(data: bytes):
    crc = 0
    for byte in data:                       # data에서 1bytes(8bit : "0xCA", "0xFE")씩 꺼낸다.
        crc ^= (byte << 8)                  # ^은 XOR연산으로, 같으면 0, 다르면 1 ->"배타적" :  순수하게 하나만 참(1)인 상태만 인정. 
        # crc 변수에는 xor로 인해 byte가 왼쪽으로 8비트(1byte) 이동한 것과 같은 값이 담긴다. ex) crc = 0xCA00
        for _ in range(8):                  # 1byte = 8bit이므로 한 비트씩 나눗셈을 수행, <<8 로 앞에 8비트만 유효하므로 8번 실행.
            if crc & 0x8000:                # CRC의 첫 비트(MSB)가 1이면 나눗셈(XOR)이 가능하므로. 1021 = 0001 0000 0010 0001로 CRC에서 쓰는 생성다항식
                crc = (crc << 1) ^ 0x1021   # 16진수는 15차항까지만 가능하고, 1021은 실제로 16차항이 1로 생략.. 이를 맞추기 위해 crc를 왼쪽 1 shift한다.
            else:
                crc <<= 1                   # MSB가 0이므로 최고차항이 맞지 않아 XOR이 불가능하므로 다음 연산을 위해 왼쪽으로 1만큼 shift.
            crc &= 0xFFFF                   # 16진수에서 계속 연산하기 위해.. 16비트 유지하기 위해..
    return crc

# 명령 전송을 언제든 호출할 수 있도록 함수로 분리
def send_command(sock, p_type):
    global tc_seq
    # p_type (인자로 받음) : Type: 모드 명령   B : (1 byte)  : 명령어 분류: 패킷이 명령(TC)인지, 상태보고(TM)인지, 응답(ACK/NAK)인지
    # > : Big-Endian
    # H : unsigned short (2 bytes), h : signed short
    # B : unsigned char (1 byte)
    magic = 0xCAFE      # Magic Number      // H : (2 bytes) : 데이터 동기화 및 식별: 수신측에서 "이것이 우리 위성의 패킷인가?"를 가장 먼저 판단.
    ver = 0x01          # Version 1         // B : (1 byte)  : 프로토콜 호환성: 추후 패킷 구조가 변경되었을 때, 구버전과 신버전을 구분하여 처리하기 위함.
    seq = tc_seq        # Sequence Number   // H : (2 bytes) : 추적 및 중복 방지: 지상국이 보낸 패킷에 번호를 매겨, 위성이 보낸 답장(ACK)과 짝을 맞춤.
    p_len = 0           # Payload 길이      // H : (2 bytes) : 가변 데이터 길이: 헤더 뒤에 붙는 실제 본문(Payload)의 크기를 알림.

    # 포맷: >(빅엔디안) H(Magic) B(Ver) B(Type) H(Seq) H(Len) = 총 8바이트
    header = struct.pack('>HBBHH', magic, ver, p_type, seq, p_len)  # struct.pack은 자료형을 C 구조체 포맷에 맞춰 바이너리 bytes로 변환해준다.

    crc_val = crc16_xmodem(header)
    packet = header + struct.pack('>H', crc_val)

    sock.sendto(packet, (SAT_IP, SAT_PORT))
    print(f"\n[송신] 위성으로 명령 전송 완료 (Type: 0x{p_type:02X}, Seq: {seq})")
    
    tc_seq += 1 # 보낼 때마다 지상국 시퀀스 번호 1씩 증가

# 운영자 터미널(operator.py)에서 오는 문자열 명령을 받아 위성으로 중계하는 스레드
def listen_for_operator_commands(sat_sock):
    cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    cmd_sock.bind(("127.0.0.1", LOCAL_CMD_PORT))
    
    while True:
        data, _ = cmd_sock.recvfrom(1024)
        cmd_str = data.decode('utf-8').strip().upper()
        
        if cmd_str == "SAFE":
            print("\n👨‍🚀 [운영자 수동 개입] SAFE 모드 전환 명령 수신!")
            send_command(sat_sock, 0x10)
        elif cmd_str == "NOMINAL":
            print("\n👨‍🚀 [운영자 수동 개입] NOMINAL 모드 전환 명령 수신!")
            send_command(sat_sock, 0x20)

def auto_control_center():
    # socket.AF_INET: IPv4 주소 체계를 사용 / socket.SOCK_DGRAM: UDP(User Datagram Protocol) 방식을 사용
    sat_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # 처음 켤 때 위성을 NOMINAL 모드로
    print("지상국 서버 시작: 위성 초기화 명령 전송 (NOMINAL 모드)")
    send_command(sat_sock, 0x20) 
    
    # 위성(OBC)측에서 LOS(통신두절)될 경우 TM을 못받는 상황을 알기 위해 2.0초 타임아웃 설정
    sat_sock.settimeout(2.0) 

    # 운영자 명령 수신 스레드 가동
    cmd_thread = threading.Thread(target=listen_for_operator_commands, args=(sat_sock,), daemon=True)
    cmd_thread.start()
    
    print("=" * 60)
    print("📡 위성 자동 관제(Auto-Commanding) 서버 가동 중... (모니터링 화면)")
    print("   수동 제어는 'operator.py' 터미널 창을 이용하세요.")
    print("=" * 60)

    # 통신 단절(LOS) 상태를 추적하는 플래그 변수
    is_los = False
    
    # 명령 폭주 방지를 위한 쿨타임 변수
    last_auto_cmd_time = 0.0
    
    try:
        while True:
            try:
                # 위성에서 응답(또는 TM) 올때까지 대기 상태 들어갔다가 응답 올시 변수에 저장
                data, addr = sat_sock.recvfrom(1024) 

                # 통신이 끊겼다가 다시 데이터가 들어오면 AOS(통신 복구) 선언
                if is_los:
                    print("\n📡 [AOS] 위성 통신 복구! 과거 데이터 덤프(Dump) 및 수신 재개...")
                    is_los = False # 다시 정상 상태로 변경

                # 헤더(8바이트) 먼저 파싱
                magic, ver, p_type, seq, p_len = struct.unpack('>HBBHH', data[:8])
                
                # 1. ACK 패킷이 도착한 경우 (지상국 명령을 위성이 잘 받았다는 뜻)
                if p_type == 0x00:
                    print(f"  └─ ✅ [ACK 수신] 위성이 지상국 명령(Seq:{seq})을 정상적으로 수행했습니다.")
                elif p_type == 0xFF:
                    print(f"  └─ ❌ [NAK 수신] 위성 명령 수신 실패 (CRC 에러 등, Seq:{seq})")
                
                # 2. TM 패킷이 도착한 경우
                elif p_type == 0x05:
                    # 페이로드(5바이트) 파싱: H(배터리 2, 무부호) + h(온도 2, 부호있음) + B(모드 1)
                    battery, temperature, mode_byte = struct.unpack('>HhB', data[8:13])
                    
                    mode_map = {
                        0x40: "BOOT",
                        0x20: "NOMINAL",
                        0x10: "SAFE",
                        0x30: "EMERGENCY"
                    }
                    mode_str = mode_map.get(mode_byte, "UNKNOWN")
                    
                    print(f"[TM 수신] Seq: {seq:04d} | 모드: [{mode_str:<9}] | 🔋 배터리: {battery:3d}% | 🌡️ 온도: {temperature:3d}°C")
                    
                    # ==========================================
                    # 지상국 자율 관제 로직 (쿨타임 3초 적용)
                    # ==========================================
                    current_time = time.time()
                    
                    # 마지막 자동 명령 발송 후 3초가 지났을 때만 개입 (덤프 시 명령 폭주 방지)
                    if current_time - last_auto_cmd_time > 3.0:
                        
                        # 위급 상황(EMERGENCY) 감지 시 긴급표시 로그 출력
                        if mode_byte == 0x30:
                            # 온도가 0도 이하로 충분히 식었다면 지상국이 SAFE 모드 전환 전송
                            if temperature <= 0:
                                print("\n🛠️ [자동 복구] 위성 온도가 안정권(0°C 이하)으로 식었습니다. SAFE 모드로 시스템을 재부팅합니다!")
                                send_command(sat_sock, 0x10) # 0x10 = SAFE
                                last_auto_cmd_time = current_time # 시간 갱신
                            else:
                                # 아직 안 식었으면 사이렌 계속 울림
                                print("🚨🚨🚨 [비상 사태] 위성 셧다운 상태 유지 중... 온도 냉각 대기 🚨🚨🚨")
                                last_auto_cmd_time = current_time # 사이렌 폭주 방지를 위해 시간 갱신

                        # 배터리가 20% 이하로 떨어지면 강제로 SAFE 모드 전환 (정상 운용 중일 때만)
                        elif mode_byte == 0x20 and battery <= 20:
                            print("\n⚠️ [경고] 배터리 고갈 임박! 태양광 충전을 위해 SAFE 모드 전환 명령을 송신합니다!")
                            send_command(sat_sock, 0x10) 
                            last_auto_cmd_time = current_time # 시간 갱신
                        
                        # 배터리가 95% 이상 충전되면 다시 임무 수행(NOMINAL) 지시 (충전 중일 때만)
                        elif mode_byte == 0x10 and battery >= 95:
                            print("\n✅ [안정] 배터리 충전 완료. 임무 재개를 위해 NOMINAL 모드 전환 명령을 송신합니다!")
                            send_command(sat_sock, 0x20)
                            last_auto_cmd_time = current_time # 시간 갱신

            # 2초간 데이터가 안 와서 타임아웃 발생 시
            except socket.timeout:
                if not is_los: # 처음 끊겼을 때만 메시지 1번 출력
                    print("\n⚠️ [LOS] 위성과 통신이 끊겼습니다! (Telemetry 수신 대기 중...)")
                    is_los = True
                continue # 다시 while 문 처음으로 돌아가서 계속 대기
                
    except KeyboardInterrupt:
        print("\n🛑 서버를 종료합니다. (Ctrl+C)")
    finally:
        sat_sock.close()

if __name__ == "__main__":
    auto_control_center()