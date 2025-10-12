# -*- coding: utf-8 -*-
import os
import csv
import time
import yaml
import argparse
from datetime import datetime

from pi.decision import DecisionFSM, FsmParams, CornerDetector, CornerParams
from pi.sensor.adapter_rplidar import RPLidarAdapter
from pi.sensor.hall_thread import HallThread
from pi.control.esp32_link import open_from_config


# -------- 유틸 --------
def load_cfg(path="pi/config.yaml"):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def fmt_mm(v):
    return f"{v:.0f}mm" if isinstance(v, (int, float)) else "NA"

def fmt_s(v):
    return f"{v:.2f}s" if isinstance(v, (int, float)) else "NA"


# -------- 엔트리 --------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="pi/config.yaml")
    ap.add_argument("--period", type=float, default=None, help="메인 루프 주기(초)")
    ap.add_argument("--use-hall", action="store_true", help="ESP32 Hall 속도 스레드 사용")
    ap.add_argument("--no-servo", action="store_true", help="ESP32 서보 제어 비활성화")  # ★ 수정
    args = ap.parse_args()

    cfg = load_cfg(args.config)

    # ---- LIDAR 어댑터 ----
    L = cfg.get("lidar", {})
    sensor = RPLidarAdapter(
        port=L.get("port", "/dev/ttyUSB0"),
        baud=L.get("baud", 460800),
        pwm=L.get("pwm", 650),
        max_dist_mm=L.get("max_dist_mm", 4000),
    )

    # ---- FSM & Corner ----
    FC = cfg.get("fsm", {}) or {}
    fsm = DecisionFSM(FsmParams(**FC))
    corner = CornerDetector(CornerParams())

    # ---- Hall 스레드 ----
    hall = None
    if args.use_hall:
        hall = HallThread(cfg_path=args.config, poll_ms=50, stale_s=0.5)
        hall.start()
        print("[HALL] thread started (poll=50ms, stale=0.5s)")

    # ---- Servo 연결 ----
    link = None
    if not args.no_servo:
        try:
            link = open_from_config(args.config)
            print("[SERVO] connected")
        except Exception as e:
            print("[WARN] servo link failed:", e)

    # ---- 주기/로그 ----
    A = cfg.get("app", {}) or {}
    period = args.period if args.period is not None else A.get("period", 0.1)
    log_dir = A.get("log_dir", "pi/logs")
    os.makedirs(log_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(log_dir, f"{A.get('session_prefix','run')}_{stamp}.csv")
    f = open(csv_path, "w", newline="")
    w = csv.writer(f)
    w.writerow(["ts", "state", "d_min_mm", "v_mps", "ttc_s"])

    print(f"[RUN] period={period}s  log={csv_path}")

    try:
        last_pwm = None
        last_flush = time.time()
        while True:
            d_min_mm = sensor.read()
            v_mps = hall.get_speed() if hall else fsm.p.v_est_mps
            out = fsm.update(d_min_mm, v_mps=v_mps)

            # 코너 감지 (추가)
            d_front, d_left, d_right, _ = sensor.read_triplet()
            corner_info = corner.update(d_front, d_left, d_right, v_mps)
            if corner_info["active"]:
                out["state"] = "CORNER"
                out["target_deg"] = fsm.p.warn_deg  # 필요 시 별도 값 설정 가능

            # 상태 기반 PWM 결정
            pwm_map = {
                "SAFE": 2500,
                "WARN": 1600,
                "FAILSAFE": 2500,
                "CORNER": 2000,
                "BRAKE": 1500,
            }
            pwm_us = pwm_map.get(out["state"], 2500)

            # 출력
            print(f"[{out['state']}] d_min={fmt_mm(out['d_min_mm'])} "
                  f"v={v_mps if isinstance(v_mps, (int, float)) else 'NA'}m/s "
                  f"ttc={fmt_s(out['ttc'])}")

            # 서보 제어
            if (not args.no_servo) and link is not None and pwm_us != last_pwm:
                try:
                    link.set_us(pwm_us)
                    last_pwm = pwm_us
                except Exception as e:
                    print("[SERVO ERR]", e)

            w.writerow([f"{time.time():.3f}", out["state"], out["d_min_mm"], v_mps, out["ttc"]])
            if time.time() - last_flush >= 1.0:
                f.flush()
                last_flush = time.time()

            time.sleep(period)

    except KeyboardInterrupt:
        print("\n[APP] stopped by user.")
    except Exception as e:
        print("[APP ERR]", e)
    finally:
        try:
            sensor.stop()
        except Exception:
            pass
        if hall:
            hall.stop()
        try:
            f.close()
        except Exception:
            pass
        print("[LOG] saved:", csv_path)


if __name__ == "__main__":
    main()