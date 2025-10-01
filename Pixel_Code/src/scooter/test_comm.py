# test_comm.py
import time
from comm import Comm

c = Comm("/dev/ttyACM0", 115200)

# 1) 부팅 메시지 수집
print("=== Boot lines ===")
print("\n".join(c.poll_events(1.0)))

# 2) 모드 전환, 속도캡, 명령 전송
c.send_mode("NORMAL")
c.send_hb()
c.send_cmd("SAFE")
print("=== After MODE NORMAL + HB + SAFE ===")
print("\n".join(c.poll_events(0.5)))

c.send_mode("CORNER")
c.send_speed_cap(11)
c.send_hb()
c.send_cmd("BRAKE")   # CORNER에서도 명령은 보냄(ESP32가 무시/반영 정책은 이후 결정)
print("=== After MODE CORNER + SPD_CAP 11 + HB + BRAKE ===")
print("\n".join(c.poll_events(0.8)))

# 3) HB 중단 → fail-safe 이벤트 확인
print("=== Stop HB for 1.2s to trigger fail-safe ===")
time.sleep(1.2)
print("\n".join(c.poll_events(0.5)))

c.close()