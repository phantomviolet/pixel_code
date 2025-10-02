# -*- coding: utf-8 -*-
import sys, time
from pyrplidar import PyRPlidar
from decision import DecisionCore
from brake_controller import BrakeController, BrakeLevel
# ESP32 사용 시:
# from brake_controller_esp32 import BrakeController, BrakeLevel

# ========= 라이다 연결 설정 =========
PRIMARY_PORT = "/dev/ttyUSB0"      # 네 설정
PRIMARY_BAUD = 460800
PRIMARY_TIMEOUT = 3

# (필요시만) 폴백
FALLBACK_PORTS = ["/dev/ttyUSB1", "/dev/ttyAMA0"]

# ========= 런타임 =========
PWM = 500
LOOP_HZ = 20
MOCK_SPEED_KMH = 5.0
USE_MOCK_SPEED = True

def try_connect_lidar(lidar: PyRPlidar):
    try:
        lidar.connect(port=PRIMARY_PORT, baudrate=PRIMARY_BAUD, timeout=PRIMARY_TIMEOUT)
        print(f"[LIDAR] 연결 성공: {PRIMARY_PORT}")
        return True
    except Exception as e:
        print(f"[LIDAR] 1차 포트 실패({PRIMARY_PORT}): {e}")

    for p in FALLBACK_PORTS:
        try:
            lidar.connect(port=p, baudrate=PRIMARY_BAUD, timeout=PRIMARY_TIMEOUT)
            print(f"[LIDAR] 폴백 연결 성공: {p}")
            return True
        except Exception as e:
            print(f"[LIDAR] 폴백 실패({p}): {e}")
    return False

def main():
    lidar = PyRPlidar()
    if not try_connect_lidar(lidar):
        print("[오류] 라이다 포트 연결 실패.")
        sys.exit(1)

    # 모터 가동
    lidar.set_motor_pwm(PWM)
    time.sleep(2)

    # 스캔 시작 (force_scan 유지)
    scan_gen = lidar.force_scan()()

    core = DecisionCore()
    brake = BrakeController()

    print("[RUN] 판단 루프 시작")
    interval = 1.0 / LOOP_HZ
    next_t = time.time()

    try:
        while True:
            loop_start = time.time()

            # ⭐ 루프마다 신선한 테이블로 시작
            dist_by_deg = [None] * 360

            # 각도별 '최소 거리'로 테이블 채우기
            consumed = 0
            target_points = 700   # 필요시 500~1200 조정
            while consumed < target_points:
                scan = next(scan_gen)
                dist = getattr(scan, "distance", 0.0)
                ang  = getattr(scan, "angle", 0.0)
                if dist > 0:
                    a = int(ang) % 360
                    prev = dist_by_deg[a]
                    if prev is None or dist < prev:
                        dist_by_deg[a] = dist
                consumed += 1

            # 속도 (홀센서 없으면 mock)
            v_kmh = MOCK_SPEED_KMH if USE_MOCK_SPEED else 10.0
            v_mps = v_kmh / 3.6

            # 의사결정(정면 180° 정책 반영됨)
            level, info = core.decide(dist_by_deg, v_mps)

            # 브레이크 명령 (지금은 스텁 → 프린트)
            if level == "SAFE":
                brake.set_level(BrakeLevel.SAFE)
            elif level == "MILD":
                brake.set_level(BrakeLevel.MILD)
            elif level == "STRONG":
                brake.set_level(BrakeLevel.STRONG)
            elif level == "EMERGENCY":
                brake.set_level(BrakeLevel.EMERGENCY)

            # 코너 검출 시 콘솔 출력
            if info["corner"] is not None:
                ang_c, dist_c = info["corner"]
                print(f"코너 검출 (거리: {int(dist_c)}mm, 각도: {int(ang_c)}°)")
                print("감속 수행")

            # 상태 요약
            dshow = f"{info['d_min_m']:.2f}m" if info['d_min_m'] is not None else "None"
            tshow = f"{info['ttc_s']:.2f}s" if info['ttc_s'] is not None else "None"
            loop_ms = (time.time() - loop_start) * 1000.0
            print(f"[STATE] v={v_kmh:.1f}km/h d_min={dshow} TTC={tshow} "
                  f"level={info['level']} state={info['state']} loop={loop_ms:.1f}ms")

            # 주기 유지
            next_t += interval
            sleep = next_t - time.time()
            if sleep > 0:
                time.sleep(sleep)
            else:
                next_t = time.time()

    except KeyboardInterrupt:
        print("\n[종료] 사용자 인터럽트")
    finally:
        try:
            lidar.stop()
            lidar.set_motor_pwm(0)
            lidar.disconnect()
        except Exception:
            pass

if __name__ == "__main__":
    main()