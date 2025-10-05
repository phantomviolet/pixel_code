# -*- coding: utf-8 -*-
import os, sys, time
from pyrplidar import PyRPlidar
from decision import DecisionCore
from esp32_comm import ESP32BrakeSerial

# ========= 전역 설정 =========
PRIMARY_PORT = "/dev/ttyUSB0"     # 네 환경 유지
PRIMARY_BAUD = 460800
PRIMARY_TIMEOUT = 3
FALLBACK_PORTS = ["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyAMA0"]

PWM = 500            # 라이다 모터 PWM
LOOP_HZ = 20         # 판단 주기(초당 20회)

# ===== 우선순위 정의 =====
LEVEL_PRIO = {"EMERGENCY": 3, "STRONG": 2, "MILD": 1, "SAFE": 0}

class LevelHysteresis:
    """
    상향(강해짐)은 즉시 적용.
    하향(풀림)은
      - 최근 전송 후 actuation_ms(서보 이동시간) 지나야 하고
      - 최소 유지시간(min_hold_ms) 지나야 하고
      - 동일 하향 레벨이 deesc_stable_ms 동안 연속 유지될 때만 적용.
    + EMERGENCY 래치:
      - EMERGENCY 걸리면 속도 ≤ emergency_clear_v_kmh 가
        emergency_clear_stable_ms 동안 유지되기 전까지 무조건 유지.
    """
    def __init__(self, esp,
                 min_hold_ms=500, deesc_stable_ms=800, actuation_ms=300,
                 emergency_clear_v_kmh=0.5, emergency_clear_stable_ms=1000):
        self.esp = esp
        self.min_hold_ms = min_hold_ms
        self.deesc_stable_ms = deesc_stable_ms
        self.actuation_ms = actuation_ms

        self.last_sent_level = None
        self.last_sent_ts = 0  # ms
        self._deesc_candidate = None
        self._deesc_since = 0  # ms

        # Emergency latch
        self.in_emergency = False
        self.emergency_since_ms = 0
        self.emergency_clear_v_kmh = emergency_clear_v_kmh
        self.emergency_clear_stable_ms = emergency_clear_stable_ms
        self._emer_clear_since = 0  # ms (조건 시작 시각)

    def _now_ms(self):
        return int(time.time() * 1000)

    def _send(self, level: str, now_ms: int):
        try:
            self.esp.send_level(level)
            self.last_sent_level = level
            self.last_sent_ts = now_ms
            # print(f"[HYS] SEND {level}")
        except Exception as e:
            print(f"[ESP32 ERR] {e}")

    def _enter_emergency(self, now_ms: int):
        if self.last_sent_level != "EMERGENCY":
            self._send("EMERGENCY", now_ms)
        self.in_emergency = True
        self.emergency_since_ms = now_ms
        self._emer_clear_since = 0
        self._deesc_candidate = None  # 하향 후보 초기화

    def _maybe_exit_emergency(self, v_kmh: float, now_ms: int) -> bool:
        """
        속도 조건이 충분히 유지되면 EMERGENCY 래치를 해제.
        True를 반환하면 래치 해제됨.
        """
        if v_kmh is None:
            return False
        if v_kmh <= self.emergency_clear_v_kmh:
            if self._emer_clear_since == 0:
                self._emer_clear_since = now_ms
            # 일정 시간 이하 속도가 유지되면 해제
            if (now_ms - self._emer_clear_since) >= self.emergency_clear_stable_ms:
                self.in_emergency = False
                self._emer_clear_since = 0
                return True
        else:
            # 조건 끊기면 타이머 리셋
            self._emer_clear_since = 0
        return False

    def update(self, new_level: str, v_kmh: float):
        now = self._now_ms()

        # 최초 전송
        if self.last_sent_level is None:
            if new_level == "EMERGENCY":
                self._enter_emergency(now)
            else:
                self._send(new_level, now)
            return

        # EMERGENCY 래치 활성 중이면 → 풀 조건 만족 전까지 무조건 EMERGENCY 유지
        if self.in_emergency:
            # 아직 EMERGENCY가 아니라면 다시 고정
            if self.last_sent_level != "EMERGENCY":
                self._send("EMERGENCY", now)
                return
            # 풀 조건 체크 (속도 충분히 낮음이 일정 시간 유지)
            if self._maybe_exit_emergency(v_kmh, now):
                # 래치 해제 직후엔 '새로운 레벨'을 하향 히스테리시스 규칙으로 처리
                # (아래 일반 로직으로 계속 진행)
                pass
            else:
                # 계속 EMERGENCY 유지
                return

        # 여기부터 일반 히스테리시스 규칙
        cur = self.last_sent_level

        # 새로 EMERGENCY 돌입?
        if new_level == "EMERGENCY":
            self._enter_emergency(now)
            return

        # 상향(우선순위 ↑) 즉시 적용
        if LEVEL_PRIO[new_level] > LEVEL_PRIO[cur]:
            self._send(new_level, now)
            self._deesc_candidate = None
            return

        # 동일 레벨이면 아무것도 안 함
        if LEVEL_PRIO[new_level] == LEVEL_PRIO[cur]:
            self._deesc_candidate = None
            return

        # 하향(풀기) 시도 → 보호 조건들
        if now - self.last_sent_ts < self.actuation_ms:
            return
        if now - self.last_sent_ts < self.min_hold_ms:
            return

        if self._deesc_candidate != new_level:
            self._deesc_candidate = new_level
            self._deesc_since = now
            return

        if now - self._deesc_since >= self.deesc_stable_ms:
            self._send(new_level, now)
            self._deesc_candidate = None


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
    
    

    # 네 구조 유지: force_scan 사용
    scan_gen = lidar.force_scan()()

    # -------- Decision Core & ESP32 & Logger --------
    core = DecisionCore()
    esp = ESP32BrakeSerial(port="/dev/ttyACM0", timeout=0.2)
    try:
        esp.connect()
    except Exception as e:
        print(f"[경고] ESP32 연결 실패: {e}")
        esp = None
    
    # ★ 시작 시 서보 테스트 시퀀스 (300 → 100 → 300)
    if esp:
        try:
            print("[INIT] Servo check: 300 → 100 → 300 sequence")
            esp.send_angle(300, force=True)
            time.sleep(0.8)
            esp.send_angle(100, force=True)
            time.sleep(0.8)
            esp.send_angle(300, force=True)
            time.sleep(0.8)
            print("[INIT] Servo movement test completed.")
        except Exception as e:
            print(f"[INIT] Servo test failed: {e}")
    
    # 히스테리시스(+EMERGENCY 래치)
    hys = LevelHysteresis(
        esp,
        min_hold_ms=500,
        deesc_stable_ms=800,
        actuation_ms=300,
        emergency_clear_v_kmh=0.5,
        emergency_clear_stable_ms=1000
    ) if esp else None

    # 각도별 최신 최소 거리(mm) 테이블
    dist_by_deg = [None] * 360

    print("[RUN] 판단 루프 시작")
    interval = 1.0 / LOOP_HZ
    next_t = time.time()
    last_speed_kmh = 0.0

    try:
        while True:
            # ✅ 프레임 시작 시 초기화: 이번 프레임의 최소값만 계산
            dist_by_deg = [None] * 360

            # ---- 라이다 포인트 소비하여 테이블 업데이트 ----
            consumed = 0
            while consumed < 800:  # 프레임 커버리지 넓게(원하면 500~1500로 조절)
                m = next(scan_gen)  # PyRPlidarMeasurement
                dmm = getattr(m, "distance", 0.0)
                ang = getattr(m, "angle", 0.0)

                # 전방 스캔 범위만 사용 (0~80°, 279~359°)
                if not ((0.0 <= ang <= 80.0) or (279.0 <= ang <= 359.9)):
                    consumed += 1
                    continue

                # 거리 유효 범위 필터 (너무 가까운 하우징/바닥 반사 제거)
                if not (80.0 <= dmm <= 8000.0):  # 0.08m ~ 8.0m만 신뢰
                    consumed += 1
                    continue

                a = int(ang) % 360
                prev = dist_by_deg[a]
                if prev is None or dmm < prev:
                    dist_by_deg[a] = dmm
                consumed += 1

            # ---- ESP32 속도 수신 ----
            v_kmh = last_speed_kmh
            if esp:
                line = esp.poll_read()
                if line and line.startswith("V:"):
                    try:
                        v_kmh = float(line.split(":", 1)[1])
                        last_speed_kmh = v_kmh
                    except ValueError:
                        pass
            v_mps = v_kmh / 3.6

            # ---- 의사결정 ----
            level, info = core.decide(dist_by_deg, v_mps)

            # ---- 브레이크 명령(히스테리시스/래치) ----
            if esp and hys:
                hys.update(level, v_kmh)

            # ---- 코너 검출 로그 ----
            if info.get("corner"):
                ang_c, dist_c = info["corner"]
                print(f"코너 검출 (거리: {int(dist_c)}mm, 각도: {int(ang_c)}°) → 감속 준비")

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
        print("[SAFE EXIT]")


if __name__ == "__main__":
    main()