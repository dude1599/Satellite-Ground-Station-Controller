import socket
import struct
import threading
import time
import queue

SAT_IP = "127.0.0.1"
SAT_PORT = 9000
LOCAL_CMD_PORT = 8000

tc_seq = 1
tc_cmd_queue = queue.Queue()
pending_tc = None

# Baseline UDP 비교 지표
stats = {
    "tc_sent_first": 0,          # 실제 제어 명령 최초 전송 횟수 (0x10, 0x20만)
    "tc_ack_success": 0,         # ACK 성공 횟수
    "tc_failed": 0,              # timeout 후 실패 횟수
    "tc_rtt_samples": [],        # 성공한 명령의 RTT
    "tc_completion_samples": [], # baseline에서는 RTT와 동일 개념
    "total_tx_packets": 0        # 전체 송신 패킷 수 (Ping 포함 가능)
}

def crc16_xmodem(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc

def enqueue_command(p_type: int) -> bool:
    global pending_tc

    if pending_tc is not None and pending_tc["p_type"] == p_type:
        return False

    with tc_cmd_queue.mutex:
        if len(tc_cmd_queue.queue) > 0 and tc_cmd_queue.queue[-1] == p_type:
            return False

    tc_cmd_queue.put(p_type)
    return True

def build_tc_packet(p_type: int):
    global tc_seq
    magic = 0xCAFE
    ver = 0x01
    seq = tc_seq
    p_len = 0

    header = struct.pack(">HBBHH", magic, ver, p_type, seq, p_len)
    crc_val = crc16_xmodem(header)
    packet = header + struct.pack(">H", crc_val)

    tc_seq += 1
    return packet, seq

def listen_for_operator_commands():
    cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    cmd_sock.bind(("127.0.0.1", LOCAL_CMD_PORT))

    while True:
        data, _ = cmd_sock.recvfrom(1024)
        cmd_str = data.decode("utf-8").strip().upper()

        if cmd_str == "SAFE":
            if enqueue_command(0x10):
                print("\n👨‍🚀 [운영자 수동 개입] SAFE 모드 전환 명령 수신! (큐에 적재)")
        elif cmd_str == "NOMINAL":
            if enqueue_command(0x20):
                print("\n👨‍🚀 [운영자 수동 개입] NOMINAL 모드 전환 명령 수신! (큐에 적재)")

def print_stats():
    print("\n📊 [Baseline UDP 성능 지표]")
    print(f" - 최초 전송 TC: {stats['tc_sent_first']} 회")
    print(f" - 최종 전송 성공: {stats['tc_ack_success']} 회")
    print(f" - 영구 실패: {stats['tc_failed']} 회")

    if stats["tc_sent_first"] > 0:
        success_rate = (stats["tc_ack_success"] / stats["tc_sent_first"]) * 100.0
        overhead = stats["total_tx_packets"] / stats["tc_sent_first"]
        print(f" - 명령 최종 성공률: {success_rate:.1f}%")
        print(f" - 명령 1건당 평균 전송 횟수: {overhead:.2f} 회")

    if len(stats["tc_rtt_samples"]) > 0:
        avg_rtt = sum(stats["tc_rtt_samples"]) / len(stats["tc_rtt_samples"])
        avg_completion = sum(stats["tc_completion_samples"]) / len(stats["tc_completion_samples"])
        print(f" - 평균 RTT: {avg_rtt:.3f} 초")
        print(f" - 평균 명령 완료 시간: {avg_completion:.3f} 초")
    print("-" * 40)

def auto_control_center():
    global pending_tc

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.5)

    cmd_thread = threading.Thread(target=listen_for_operator_commands, daemon=True)
    cmd_thread.start()

    print("=" * 60)
    print("📡 Baseline UDP 지상국 서버 시작")
    print("=" * 60)

    # 초기 링크 seed용 Ping (통계 제외)
    print("🚀 [System] 위성과의 UDP 링크 생성을 위해 Ping 패킷을 전송합니다.")
    enqueue_command(0x0F)

    is_los = False
    last_auto_cmd_time = 0.0
    last_tm_recv_time = time.time()

    try:
        while True:
            current_time = time.time()

            # Baseline: 재전송 없음, timeout 시 바로 실패 처리
            if pending_tc is not None:
                if current_time - pending_tc["last_send_time"] > 2.0:
                    if pending_tc["p_type"] == 0x0F:
                        print(f"⚠️ [Ping 실패] 초기 링크 확보용 Ping(Seq:{pending_tc['seq']}) 응답 없음 (통계 제외)")
                    else:
                        print(f"❌ [UDP 실패] TC(Seq:{pending_tc['seq']}) ACK 미수신. 재전송 없이 실패 처리")
                        stats["tc_failed"] += 1
                        print_stats()
                    pending_tc = None

            else:
                if not tc_cmd_queue.empty():
                    p_type = tc_cmd_queue.get()
                    packet, seq = build_tc_packet(p_type)
                    sock.sendto(packet, (SAT_IP, SAT_PORT))
                    stats["total_tx_packets"] += 1

                    if p_type == 0x0F:
                        print(f"\n🌱 [Link Seed] 위성 연결용 Ping 패킷 발송 (Seq: {seq})")
                    else:
                        print(f"\n🚀 [TC 송신] 위성으로 명령 전송 (Type: 0x{p_type:02X}, Seq: {seq})")
                        stats["tc_sent_first"] += 1

                    send_t = time.time()
                    pending_tc = {
                        "packet": packet,
                        "seq": seq,
                        "p_type": p_type,
                        "original_send_time": send_t,
                        "last_send_time": send_t
                    }

            try:
                data, addr = sock.recvfrom(1024)
                recv_time = time.time()

                if len(data) < 10:
                    continue

                magic, ver, p_type, seq, p_len = struct.unpack(">HBBHH", data[:8])
                crc_start_idx = 8 + p_len

                if len(data) >= crc_start_idx + 2:
                    received_crc = struct.unpack(">H", data[crc_start_idx:crc_start_idx + 2])[0]
                    calculated_crc = crc16_xmodem(data[:crc_start_idx])
                    if received_crc != calculated_crc:
                        print(f"  └─ ❌ [CRC 에러] 손상된 패킷 무시 (Seq:{seq})")
                        continue
                else:
                    continue

                if p_type == 0x00:
                    print(f"  └─ ✅ [ACK 수신] TC(Seq:{seq})가 위성에서 수락/처리 완료되었습니다.")
                    if pending_tc is not None and pending_tc["seq"] == seq:
                        rtt = recv_time - pending_tc["last_send_time"]
                        completion_time = recv_time - pending_tc["original_send_time"]

                        if pending_tc["p_type"] == 0x0F:
                            print(f"  └─ 🌱 [Link Established] 위성과의 통신 링크가 정상적으로 확보되었습니다! (RTT: {rtt:.3f}s)")
                        else:
                            stats["tc_ack_success"] += 1
                            stats["tc_rtt_samples"].append(rtt)
                            stats["tc_completion_samples"].append(completion_time)
                            print(f"  └─ 🎯 [UDP 완료] TC 전송 성공! (RTT: {rtt:.3f}s)")
                            print_stats()

                        pending_tc = None

                elif p_type == 0xFF:
                    print(f"  └─ ❌ [NAK 수신] 위성 명령 수신 거부 (Seq:{seq})")
                    if pending_tc is not None and pending_tc["seq"] == seq:
                        if pending_tc["p_type"] != 0x0F:
                            stats["tc_failed"] += 1
                            print_stats()
                        pending_tc = None

                elif p_type == 0x05 or p_type == 0x06:
                    # Ping ACK 없이도 TM 수신이 오면 링크 확보로 간주
                    if pending_tc is not None and pending_tc["p_type"] == 0x0F:
                        print("  └─ 🌱 [Link Established] Ping ACK 없이도 Downlink TM 수신으로 링크 확보 확인")
                        pending_tc = None

                    last_tm_recv_time = recv_time

                    if is_los:
                        print("\n📡 [AOS] 위성 통신 복구! 과거 데이터 덤프(Dump) 및 수신 재개...")
                        is_los = False

                    # Java 현재 TM payload = battery(2) + temp(2) + mode(1) + orbit(2) = 7 bytes
                    if len(data) < 17:
                        continue

                    battery, temperature, mode_byte, raw_orbit_angle = struct.unpack(">HhBh", data[8:15])
                    orbit_angle = raw_orbit_angle / 10.0

                    mode_map = {
                        0x40: "BOOT",
                        0x20: "NOMINAL",
                        0x10: "SAFE",
                        0x30: "EMERGENCY"
                    }
                    mode_str = mode_map.get(mode_byte, "UNKNOWN")

                    if p_type == 0x06:
                        print(f" 💾 [PB 수신] Seq: {seq:04d} | 모드: [{mode_str:<9}] | 🔋 배터리: {battery:3d}%")
                    else:
                        print(f"[RT 수신] Seq: {seq:04d} | 모드: [{mode_str:<9}] | 🔋 배터리: {battery:3d}% | 🌡️ 온도: {temperature:3d}°C | 🛰️ 궤도: {orbit_angle:.1f}°")

                        if recv_time - last_auto_cmd_time > 3.0:
                            if mode_byte == 0x30:
                                if temperature <= 0:
                                    if enqueue_command(0x10):
                                        print("\n🛠️ [자동 복구] 위성 온도가 안정권으로 식었습니다. SAFE 모드 명령 큐 적재!")
                                    last_auto_cmd_time = recv_time
                                else:
                                    print("🚨🚨🚨 [비상 사태] 위성 셧다운 상태 유지 중... 냉각 대기 🚨🚨🚨")
                                    last_auto_cmd_time = recv_time

                            elif mode_byte == 0x20 and battery <= 20:
                                if enqueue_command(0x10):
                                    print("\n⚠️ [경고] 배터리 고갈 임박! SAFE 모드 명령 큐 적재!")
                                last_auto_cmd_time = recv_time

                            elif mode_byte == 0x10 and battery >= 95:
                                if enqueue_command(0x20):
                                    print("\n✅ [안정] 배터리 충전 완료. NOMINAL 모드 명령 큐 적재!")
                                last_auto_cmd_time = recv_time

            except socket.timeout:
                pass

            check_time = time.time()
            if check_time - last_tm_recv_time > 2.0 and not is_los:
                print("\n⚠️ [LOS] 위성이 가시권을 벗어났거나 통신이 끊겼습니다!")
                is_los = True

    except KeyboardInterrupt:
        print("\n🛑 Baseline UDP 서버를 종료합니다.")
        print_stats()
    finally:
        sock.close()

if __name__ == "__main__":
    auto_control_center()