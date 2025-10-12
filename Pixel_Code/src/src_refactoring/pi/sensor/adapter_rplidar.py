# pi/sensor/adapter_rplidar.py
# -*- coding: utf-8 -*-
import time
from collections import deque
from statistics import median
from pyrplidar import PyRPlidar

class RPLidarAdapter:
    """
    config.yaml(lidar) 키 지원:
      - port, baud, pwm
      - near_cutoff_mm, max_dist_mm
      - angle_offset_deg
      - frame_ms
      - min_inliers
      - smooth_window
      - front_gate_deg (옵션, 없으면 20)
      - quantile (옵션, 없으면 0.20)
    """
    def __init__(
        self,
        port="/dev/ttyUSB0",
        baud=460800,
        pwm=650,
        near_cutoff_mm=120,
        max_dist_mm=4000,
        angle_offset_deg=0.0,
        frame_ms=100,
        min_inliers=12,
        smooth_window=3,
        front_gate_deg=20,
        quantile=0.20
    ):
        self.port = port
        self.baud = baud
        self.pwm = pwm

        self.near_cutoff_mm = int(near_cutoff_mm)
        self.max_dist_mm = int(max_dist_mm)
        self.angle_offset_deg = float(angle_offset_deg) % 360.0
        self.frame_ms = int(frame_ms)
        self.min_inliers = int(min_inliers)
        self.smooth_window = max(1, int(smooth_window))
        self.front_gate_deg = int(front_gate_deg)
        self.quantile = float(quantile)

        self.lidar = PyRPlidar()
        self._connect()

        # 최근 프레임(코너 보조/디버그)
        self.last_angles = []
        self.last_dists = []

        # 시간/변화율 추적
        self._front_t = None
        self._front_d = None

        # 출력 평활화(롤링 미디안)
        self._dq_hist = deque(maxlen=self.smooth_window)

    # ---------------- Core I/O ----------------
    def _connect(self):
        print(f"[LIDAR] connecting {self.port} @ {self.baud}")
        self.lidar.connect(port=self.port, baudrate=self.baud, timeout=3)
        self.lidar.set_motor_pwm(self.pwm)
        time.sleep(2.0)
        # force_scan은 callble generator를 리턴함
        self._scan_iter_factory = self.lidar.force_scan()
        print("[LIDAR] connected & force_scan ready.")

    def _reconnect(self):
        try:
            self.lidar.stop()
            self.lidar.set_motor_pwm(0)
            self.lidar.disconnect()
        except Exception:
            pass
        time.sleep(0.4)
        self._connect()

    # ---------------- Utils ----------------
    @staticmethod
    def _in_gate(a, lo, hi):
        """각도 게이트(랩어라운드 지원)"""
        if lo <= hi:
            return lo <= a <= hi
        return (a >= lo) or (a <= hi)

    @staticmethod
    def _quantile(vals, q):
        if not vals:
            return None
        vals = sorted(vals)
        i = max(0, min(len(vals) - 1, int(q * (len(vals) - 1))))
        return vals[i]

    def _apply_angle_offset(self, a):
        a = (a + self.angle_offset_deg) % 360.0
        return a

    # ---------------- Public API ----------------
    def read(self, frame_points=720):
        """
        - 스캔 포인트를 모아 정면 게이트(±front_gate_deg)로 제한
        - 거리 inlier 범위(near_cutoff_mm ~ max_dist_mm) 필터
        - inlier 분위수(quantile)로 대표 거리 계산
        - inlier 부족 시 전체 inlier로 폴백(여전히 분위수)
        - smooth_window>1이면 롤링 미디안으로 시간 평활화
        반환: 대표거리(mm) 또는 None
        """
        pts = []
        t0 = time.time()
        try:
            it = self._scan_iter_factory()
            # frame_ms 내에서 frame_points 근사치 수집
            while len(pts) < frame_points:
                scan = next(it)
                a = getattr(scan, "angle", None)
                d = getattr(scan, "distance", None)
                if a is None or d is None:
                    if (time.time() - t0) * 1000.0 > self.frame_ms:
                        break
                    continue

                # 일부 드라이버는 비정상 큰 단위로 올 수 있어 상한 60,000mm 가드
                if d <= 0 or d >= 60000:
                    if (time.time() - t0) * 1000.0 > self.frame_ms:
                        break
                    continue

                a = self._apply_angle_offset(float(a))
                pts.append((a, float(d)))

                if (time.time() - t0) * 1000.0 > self.frame_ms:
                    break

        except StopIteration:
            print("[LIDAR] generator exhausted → reconnect")
            self._reconnect()
            return None
        except Exception as e:
            print("[LIDAR] read exception:", e)
            return None

        if not pts:
            return None

        # 프레임 저장(코너/디버그용)
        self.last_angles = [a for a, _ in pts]
        self.last_dists  = [d for _, d in pts]

        # 정면 게이트(예: 340~360 or 0~20)
        fg = self.front_gate_deg
        front_vals = []
        for a, d in pts:
            if not (self.near_cutoff_mm <= d <= self.max_dist_mm):
                continue
            if self._in_gate(a, 360 - fg, 360) or self._in_gate(a, 0, fg):
                front_vals.append(d)

        # inlier 부족 시 전체로 폴백(여전히 분위수 사용)
        inliers = front_vals if len(front_vals) >= self.min_inliers else [
            d for _, d in pts if self.near_cutoff_mm <= d <= self.max_dist_mm
        ]
        if not inliers:
            return None

        d_q = self._quantile(inliers, self.quantile)  # mm

        # 시간 평활화(롤링 미디안)
        self._dq_hist.append(d_q)
        d_out = median(self._dq_hist) if self.smooth_window > 1 else d_q
        return float(d_out)

    # ---- 코너/보조 ----
    def _sector_min(self, angles_deg, dists_mm, lo, hi):
        vals = []
        for a, d in zip(angles_deg, dists_mm):
            if d <= 0 or d > self.max_dist_mm:
                continue
            if lo <= hi:
                if lo <= a <= hi: vals.append(d)
            else:
                if (a >= lo) or (a <= hi): vals.append(d)
        return min(vals) if vals else None

    def read_triplet(self):
        """
        마지막 read() 프레임 기준:
          - d_front: -25~+25°
          - d_left : 45~90°
          - d_right: 270~315°
          - drop   : 정면 거리의 초당 감소량(mm/s, 양수=다가옴)
        """
        if not self.last_angles or not self.last_dists:
            return None, None, None, 0.0

        angles = self.last_angles
        dists  = self.last_dists

        d_front = self._sector_min(angles, dists, 335, 25)
        d_left  = self._sector_min(angles, dists, 45, 90)
        d_right = self._sector_min(angles, dists, 270, 315)

        now = time.time()
        drop = 0.0
        if self._front_t is not None and self._front_d is not None and d_front is not None:
            dt = max(1e-3, now - self._front_t)
            drop = (self._front_d - d_front) / dt
        self._front_t = now
        self._front_d = d_front

        return d_front, d_left, d_right, drop

    # ---------------- Teardown ----------------
    def stop(self):
        try:
            self.lidar.stop()
            self.lidar.set_motor_pwm(0)
            self.lidar.disconnect()
            print("[LIDAR] stopped.")
        except Exception:
            pass