import socket

# === 운영자 UI ===
# 지상국 수신/중계 서버(gs_server.py)와 통신하기 위한 로컬 포트.
# 사용자가 텍스트를 입력해, 백엔드 서버(gs_server.py)로 전달.
LOCAL_CMD_PORT = 8000

def run_terminal():
    # socket.AF_INET: IPv4 주소 체계를 사용 / socket.SOCK_DGRAM: UDP(User Datagram Protocol) 방식을 사용
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    print("=" * 50)
    print("👨‍🚀 지상국 운영자 수동 제어 터미널 (송신 전용 화면)")
    print("=" * 50)
    print("사용 가능한 명령:")
    print(" - SAFE    : 안전 모드로 강제 전환 (충전)")
    print(" - NOMINAL : 정상 임무 모드로 강제 전환")
    print("종료하려면 'quit' 또는 'exit'를 입력하세요.")
    print("-" * 50)
    
    while True:
        # 사용자에게 텍스트 입력받기
        cmd = input("\n명령 입력 (SAFE / NOMINAL) >> ").strip().upper()
        
        if cmd in ["QUIT", "EXIT"]:
            print("터미널을 종료합니다.")
            break
            
        if cmd in ["SAFE", "NOMINAL"]:
            # 지상국 수신 서버(8000 포트)로 단순 문자열 전송
            # gs_server.py 의 listen_for_operator_commands 스레드가 이 문자열을 받아 처리.
            sock.sendto(cmd.encode('utf-8'), ("127.0.0.1", LOCAL_CMD_PORT))
            print(f"👉 '{cmd}' 명령을 중계 서버로 전송했습니다.")
        else:
            print("❌ 알 수 없는 명령입니다. (SAFE 또는 NOMINAL만 입력 가능)")

if __name__ == "__main__":
    run_terminal()