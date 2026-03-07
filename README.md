# 📡 Satellite Ground Station Controller
**위성 상태 실시간 모니터링 및 자율 관제(Auto-Commanding) 시스템**

이 프로젝트는 위성(OBC)과 UDP 통신을 통해 실시간으로 텔레메트리(TM)를 수신하고, 위성의 상태에 따라 자동으로 명령(TC)을 송신하는   
파이썬 기반의 지상국 시뮬레이터입니다.

## 🚀 Key Features
* **Autonomous Closed-Loop Control:** 운용자의 개입 없이, 위성 배터리가 20% 이하로 떨어지면 자동으로 SAFE 모드 명령을 전송하여  
  시스템을 보호하는 자율 관제 로직 구현.
* **Real-time Telemetry Monitoring:** `struct` 모듈을 활용한 바이너리 패킷 언패킹 및 위성 상태(배터리, 온도, 모드) 실시간 콘솔 시각화.
* **CRC-16 Error Detection:** 수신된 패킷의 무결성을 검증하고, 명령어 전송 시 CRC-16-XMODEM 지문을 직접 계산하여 부착함으로써  
  통신 신뢰성 확보.
* **Reliable Command Execution:** 명령 송신 후 위성의 `ACK` (수신 성공) / `NAK` (수신 실패) 응답을 대기하여 명령 수행 여부를 확실하게 검증.

---

## 🛠️ Tech Stack
* **Language:** Python 3.9.12
* **Network:** UDP Socket Programming (`socket`)
* **Data Parsing:** Binary Data Packing/Unpacking (`struct`)

---

## 🔄 Auto-Commanding Scenario (운용 시나리오)
지상국 시스템은 다음과 같은 폐루프 제어 시나리오를 무한히 반복하며 위성을 안전하게 운용합니다.

1. **[초기화]** 지상국 가동 시 위성을 `NOMINAL` 모드로 기동하는 명령 송신.
2. **[모니터링]** 타임아웃 없이 1초 주기로 위성의 배터리 및 온도 상태 수신 및 출력.
3. **[위험 감지 및 개입]** 배터리가 20% 이하 도달 시 강제로 `SAFE` (충전/대기) 모드 전환 명령 송신.
4. **[복구 및 재개]** 배터리가 95% 이상 충전 완료 시 다시 `NOMINAL` (임무 수행) 명령 송신.
