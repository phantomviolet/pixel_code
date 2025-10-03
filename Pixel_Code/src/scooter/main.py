import os, sys, time
from pyrplidar import PyRPlidar
from decision import DecisionCore
from esp32_comm import ESP32BrakeSerial

# ========= 라이다 연결 설정(네 설정 최우선) =========
PRIMARY_PORT = "/dev/ttyUSB0"    
PRIMARY_BAUD = 460800
PRIMARY_TIMEOUT = 3

# 라즈베리파이 표준 포트(자동 폴백, 기본값 실패 시에만 시도)
FALLBACK_PORTS = ["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyAMA0"]

# ========= 런타임 파라미터 =========
PWM = 500            # 라이다 모터 PWM
LOOP_HZ = 20         # 판단 주기(초당 20회)
USE_MOCK_SPEED = True
MOCK_SPEED_KMH = 12  # 홀센서 미연동 시 가짜 속도

# ========= 유틸 =========
def try_connect_lidar(lidar: PyRPlidar) -> bool:
    # 1) 최우선 포트
    try:
        lidar.connect(port=PRIMARY_PORT, baudrate=PRIMARY_BAUD, timeout=PRIMARY_TIMEOUT)
        print(f"[LIDAR] 연결 성공: {PRIMARY_PORT}")
        return True
    except Exception as e:
        print(f"[LIDAR] 1차 포트 실패({PRIMARY_PORT}): {e}")

    # 2) 폴백
    for p in FALLBACK_PORTS:
        try:
            lidar.connect(port=p, baudrate=PRIMARY_BAUD, timeout=PRIMARY_TIMEOUT)
            print(f"[LIDAR] 폴백 연결 성공: {p}")
            return True
        except Exception as e:
            print(f"[LIDAR] 폴백 실패({p}): {e}")
    return False


def main():
    # -------- LIDAR 준비 --------
    lidar = PyRPlidar()
    if not try_connect_lidar(lidar):
        print("[오류] 라이다 포트 연결 실패. 설정은 바꾸지 않았고, 폴백도 모두 실패했습니다.")
        sys.exit(1)

    lidar.set_motor_pwm(PWM)
    time.sleep(2.0)

    scan_gen = lidar.force_scan()()

    # -------- 의사결정 & ESP32 연결 --------
    core = DecisionCore()

    esp = ESP32BrakeSerial()  # 포트 자동 탐색(ACM/USB)
    try:
        esp.connect()
    except Exception as e:
        print(f"[경고] ESP32 연결 실패: {e}  (브레이크 명령 전송은 생략됩니다)")
        esp = None

    # 각도별 최신 최소 거리(mm) 테이블
    dist_by_deg = [None] * 360

    print("[RUN] 판단 루프 시작")
    interval = 1.0 / LOOP_HZ
    next_t = time.time()
    last_level = None

    try:
        while True:
            # ---- 라이다 포인트 소비하여 테이블 업데이트 ----
            consumed = 0
            while consumed < 500:  # 한 루프에서 대략 500점 정도
                m = next(scan_gen)  # PyRPlidarMeasurement
                dmm = getattr(m, "distance", 0.0)
                ang = getattr(m, "angle", 0.0)
                if dmm and dmm > 0:
                    a = int(ang) % 360
                    prev = dist_by_deg[a]
                    if prev is None or dmm < prev:
                        dist_by_deg[a] = dmm
                consumed += 1

            # ---- 속도(임시) ----
            if USE_MOCK_SPEED:
                v_kmh = MOCK_SPEED_KMH
            else:
                v_kmh = 10.0  # TODO: ESP32의 V:xx.xx 수신하여 반영
            v_mps = v_kmh / 3.6

            # ---- 의사결정 ----
            level, info = core.decide(dist_by_deg, v_mps)

            # ---- ESP32로 브레이크 명령 전송 ----
            if esp:
                try:
                    if level != last_level:
                        esp.send_level(level)   # SAFE/MILD/STRONG/EMERGENCY → A:<angle>
                        last_level = level
                    # (선택) ESP32의 V: 로그 읽기
                    line = esp.poll_read()
                    if line:
                        print(f"[ESP32] {line}")
                except Exception as e:
                    print(f"[ESP32 ERR] {e}. 재연결 시도…")
                    try:
                        esp.close()
                        time.sleep(0.5)
                        esp.connect()
                    except Exception as e2:
                        print(f"[ESP32 RECONNECT FAIL] {e2}")

            # ---- 코너 검출 로그 ----
            if info.get("corner"):
                ang_c, dist_c = info["corner"]
                print(f"코너 검출 (거리: {int(dist_c)}mm, 각도: {int(ang_c)}°)")
                print("감속 수행")

            # ---- 상태 요약 ----
            dshow = f"{info['d_min_m']:.2f}m" if info['d_min_m'] is not None else "None"
            tshow = f"{info['ttc_s']:.2f}s" if info['ttc_s'] is not None else "None"
            print(f"[STATE] v={v_kmh:.1f}km/h d_min={dshow} TTC={tshow} level={info['level']} state={info['state']}")

            # ---- 루프 주기 유지 ----
            next_t += interval
            sleep = next_t - time.time()
            if sleep > 0:
                time.sleep(sleep)
            else:
                next_t = time.time()

    except KeyboardInterrupt:
        print("\n[종료] 사용자 인터럽트")
    finally:
        # 안전 정지
        try:
            lidar.stop()
            lidar.set_motor_pwm(0)
            lidar.disconnect()
        except Exception:
            pass
        try:
            if esp:
                esp.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()