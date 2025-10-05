# -*- coding: utf-8 -*-
import time
from collections import deque
from statistics import median

# ====== 전방/섹터 정의 ======
SECTOR_HALF_DEG   = 20   # 충돌판단: 정면 ±20°
FRONT_CENTER_DEG  = 0    # 라이다 좌표계에서 "정면" 보정이 필요하면 수정
CORNER_HALF_DEG   = 80   # 코너 검출: 정면 ±90°(=정면 180°)

def wrap_angle(a: int) -> int:
    a = a % 360
    if a < 0: a += 360
    return a

def _iter_front_range(half_deg: int):
    """정면 FRONT_CENTER_DEG 기준 ±half_deg 범위를 0~359로 순회"""
    start = FRONT_CENTER_DEG - half_deg
    end   = FRONT_CENTER_DEG + half_deg
    for ang in range(start, end + 1):
        yield wrap_angle(ang)

# ====== 거리/필터 파라미터 ======
DIST_MIN_M          = 0.10
DIST_MAX_M          = 10.00
ROLL_WIN            = 3       # d_min 롤링 미디안 창
HOLD_LAST_DMIN_SEC  = 0.30    # 순간 글리치 시 마지막 유효 d_min 유지 시간

def _mm_to_m(dmm: float) -> float:
    return max(DIST_MIN_M, min(dmm / 1000.0, DIST_MAX_M))

# ====== TTC 임계 ======
TTC_EMERGENCY   = 1.2
TTC_DECELERATE  = 2.0
TTC_WARNING     = 3.0

# ====== 속도 기반 즉시 해제 임계 ======
V_SAFE_RELEASE_KMH = 0.5  # 이 이하이면 무조건 SAFE(브레이크 해제)

# ====== 코너 검출/감속 파라미터 ======
DERIV_THRESH_MM    = 400
MIN_PROMINENCE_MM  = 300
MIN_CORNER_DIST_MM = 300
MAX_CORNER_DIST_MM = 5000
ANGLE_SMOOTH       = 2

# 코너 감속 시작 거리(미터)
CORNER_SLOWDOWN_DIST_M = 2.0  # 코너까지 2 m 이내면 감속

def detect_corners_front_180(dist_by_deg):
    """
    정면 180°(±90°) 범위 안에서만 코너 후보를 찾는다.
    반환: [(ang, dist_mm), ...]
    """
    front180 = set(_iter_front_range(CORNER_HALF_DEG))
    corners = []
    for ang in front180:
        d0 = dist_by_deg[ang]
        if d0 is None or d0 <= 0:
            continue

        aL = wrap_angle(ang - ANGLE_SMOOTH)
        aR = wrap_angle(ang + ANGLE_SMOOTH)
        if (aL not in front180) or (aR not in front180):
            continue

        dL = dist_by_deg[aL]
        dR = dist_by_deg[aR]
        if dL is None or dR is None:
            continue

        # 국소 최소 + prominence
        if not (d0 + MIN_PROMINENCE_MM < dL and d0 + MIN_PROMINENCE_MM < dR):
            continue

        # 좌/우 기울기(날카로움)
        left_grad  = dL - d0
        right_grad = dR - d0
        if left_grad < DERIV_THRESH_MM or right_grad < DERIV_THRESH_MM:
            continue

        # 거리 유효 범위
        if not (MIN_CORNER_DIST_MM <= d0 <= MAX_CORNER_DIST_MM):
            continue

        corners.append((ang, d0))
    return corners

class DecisionCore:
    """
    정면 180°만 활용:
      - 충돌 판단(d_min/TTC): 정면 ±20°
      - 코너 검출: 정면 ±90°
      - v_kmh <= V_SAFE_RELEASE_KMH 이면 무조건 SAFE(브레이크 해제)
      - 코너 감속: 코너까지의 거리가 CORNER_SLOWDOWN_DIST_M 이내일 때만 MILD
    """
    def __init__(self):
        self.dist_queue = deque(maxlen=ROLL_WIN)
        self.state = "SAFE"
        self._last_valid_dmin = None
        self._last_valid_time = 0.0

        # (선택적 상태표시용) 비상 대기/해제 타임스탬프
        self.emergency_mode = False
        self.emergency_clear_since = 0.0

    def _now(self) -> float:
        return time.time()

    def update_front_min(self, dist_by_deg):
        """
        충돌 판단용 전방 최소거리(m) 계산:
          - 정면 ±20°만 사용
          - 비었으면 정면 180°(±90°)에서 최소로 폴백
          - 그래도 없으면 마지막 유효값을 잠깐 유지
        """
        samples = []
        for a in _iter_front_range(SECTOR_HALF_DEG):
            dmm = dist_by_deg[a]
            if dmm is None:
                continue
            samples.append(_mm_to_m(dmm))

        if not samples:
            fb_vals = []
            for a in _iter_front_range(CORNER_HALF_DEG):
                dmm = dist_by_deg[a]
                if dmm is None:
                    continue
                fb_vals.append(_mm_to_m(dmm))

            if not fb_vals:
                if self._last_valid_dmin and (self._now() - self._last_valid_time) <= HOLD_LAST_DMIN_SEC:
                    d_min = self._last_valid_dmin
                else:
                    return None
            else:
                d_min = min(fb_vals)
        else:
            d_min = min(samples)

        # 롤링 미디안으로 안정화
        self.dist_queue.append(d_min)
        d_robust = median(self.dist_queue)
        self._last_valid_dmin = d_robust
        self._last_valid_time = self._now()
        return d_robust

    def decide(self, dist_by_deg, speed_mps):
        """
        입력: dist_by_deg[0..359] = 각도별 최소거리(mm), speed_mps = m/s
        출력: (level, info)
          - level: "SAFE" | "MILD" | "STRONG" | "EMERGENCY"
          - info : { d_min_m, ttc_s, corner:(ang,dist_mm)|None, emergency_ready:bool, state, level }
        """
        # --- 0) 속도 기반 즉시 해제 ---
        v_kmh = speed_mps * 3.6 if (speed_mps is not None) else None
        if v_kmh is not None and v_kmh <= V_SAFE_RELEASE_KMH:
            self.state = "SAFE"
            self.emergency_mode = False
            self.emergency_clear_since = 0.0
            info = {
                "d_min_m": self.update_front_min(dist_by_deg),
                "ttc_s": None,      # v≈0이면 TTC 무의미
                "corner": None,     # 정지 상태에선 코너 감속 불필요
                "emergency_ready": False,
                "state": self.state,
                "level": "SAFE",
            }
            return "SAFE", info

        # --- 1) 코너 검출 (정면 180°) ---
        corners = detect_corners_front_180(dist_by_deg)
        corner_info = None
        corner_near = False
        if corners:
            corner_info = min(corners, key=lambda x: x[1])  # (ang, dist_mm)
            ang_c, dist_c_mm = corner_info
            if _mm_to_m(dist_c_mm) <= CORNER_SLOWDOWN_DIST_M:
                corner_near = True

        # --- 2) d_min/TTC 계산 ---
        d_min = self.update_front_min(dist_by_deg)  # m
        ttc = None
        if d_min is not None and speed_mps is not None and speed_mps > 0.05:
            ttc = d_min / speed_mps

        # --- 3) 상태/레벨 결정 ---
        if ttc is not None:
            if ttc < TTC_EMERGENCY:
                level = "EMERGENCY"; self.state = "EMERGENCY_STOP"; self.emergency_mode = True
            elif ttc < TTC_DECELERATE:
                level = "STRONG";    self.state = "DECELERATE"
            elif ttc < TTC_WARNING:
                level = "MILD";      self.state = "WARNING"
            else:
                if corner_near:
                    level = "MILD";  self.state = "SLOWDOWN_CORNER"
                else:
                    level = "SAFE";  self.state = "SAFE"
        else:
            # 거리/속도 불확실 → 보수적 감속
            level = "MILD"
            self.state = "SLOWDOWN_CORNER" if corner_near else "WARNING"

        info = {
            "d_min_m": d_min,
            "ttc_s": ttc,
            "corner": corner_info,          # (ang, dist_mm) 또는 None
            "emergency_ready": bool(corner_near),  # 코너 2m 이내면 비상 대기 (브레이크 미작동)
            "state": self.state,
            "level": level,
        }
        return level, info