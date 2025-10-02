# -*- coding: utf-8 -*-
import time
from collections import deque
from statistics import median

# ====== 전방 정의 ======
# 라이다 설치 각도 보정: "실제 정면"이 라이다 기준 몇 도인지
FRONT_CENTER_DEG = 0        # 필요 시 90/180 등으로 조정

# 충돌 판단(전방 최소거리/TTC)용 섹터: 정면 좌우 ±20°
COLLISION_HALF_DEG = 20

# 코너 검출용 섹터: 정면 좌우 ±90° (정면 180° 전체)
CORNER_HALF_DEG = 90

# 거리 유효 범위(임시 완화값: 먼저 값 유입 확인 후 0.30~6.0으로 조여도 됨)
DIST_MIN_M = 0.10
DIST_MAX_M = 10.00

# d_min 안정화
ROLL_WIN = 3                # 롤링 미디안 창
HOLD_LAST_DMIN_SEC = 0.30   # 순간 글리치 시 마지막 유효값 유지 시간

# TTC 임계(초)
TTC_EMERGENCY  = 1.2
TTC_DECELERATE = 2.0
TTC_WARNING    = 3.0

# 코너 검출 파라미터
DERIV_THRESH_MM    = 400
MIN_PROMINENCE_MM  = 300
MIN_CORNER_DIST_MM = 300
MAX_CORNER_DIST_MM = 5000
ANGLE_SMOOTH       = 2

def wrap_angle(a):
    a = a % 360
    if a < 0: a += 360
    return a

def _mm_to_m(dmm):
    return max(DIST_MIN_M, min(dmm / 1000.0, DIST_MAX_M))

def _iter_front_range(half_deg):
    """정면 FRONT_CENTER_DEG 기준 ±half_deg 각도 범위를 순회"""
    start = FRONT_CENTER_DEG - half_deg
    end   = FRONT_CENTER_DEG + half_deg
    for ang in range(start, end + 1):
        yield wrap_angle(ang)

def detect_corners_front_180(dist_by_deg):
    """
    정면 180°(±90°) 범위 안에서만 코너 후보를 찾는다.
    반환: [(ang, dist_mm), ...]
    """
    corners = []
    for ang in _iter_front_range(CORNER_HALF_DEG):
        d0 = dist_by_deg[ang]
        if d0 is None or d0 <= 0:
            continue

        aL = wrap_angle(ang - ANGLE_SMOOTH)
        aR = wrap_angle(ang + ANGLE_SMOOTH)
        # 이웃도 정면 180° 안에서만 신뢰
        if aL not in set(_iter_front_range(CORNER_HALF_DEG)) or aR not in set(_iter_front_range(CORNER_HALF_DEG)):
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
    """정면 180°만 활용: d_min/TTC(±20°), 코너(±90°)"""
    def __init__(self):
        self.dist_queue = deque(maxlen=ROLL_WIN)
        self.state = "SAFE"
        self._last_valid_dmin = None
        self._last_valid_time = 0.0

    def _now(self):
        return time.time()

    def update_front_min(self, dist_by_deg):
        """
        충돌 판단용 전방 최소거리(m) 계산:
        - 정면 ±20° 범위(COLLISION_HALF_DEG)만 사용
        - 비었으면 정면 180°(±90°) 전체에서 최소로 폴백
        - 그래도 없으면 마지막 유효값을 잠깐 유지
        """
        samples = []
        for a in _iter_front_range(COLLISION_HALF_DEG):
            dmm = dist_by_deg[a]
            if dmm is None: 
                continue
            samples.append(_mm_to_m(dmm))

        if not samples:
            # 폴백: 정면 180°에서 최소
            fb_vals = []
            for a in _iter_front_range(CORNER_HALF_DEG):
                dmm = dist_by_deg[a]
                if dmm is None: 
                    continue
                fb_vals.append(_mm_to_m(dmm))

            if not fb_vals:
                # 마지막 유효값 잠깐 유지
                if self._last_valid_dmin and (self._now() - self._last_valid_time) <= HOLD_LAST_DMIN_SEC:
                    d_min = self._last_valid_dmin
                else:
                    return None
            else:
                d_min = min(fb_vals)
        else:
            d_min = min(samples)

        # 롤링 미디안
        self.dist_queue.append(d_min)
        d_robust = median(self.dist_queue)
        self._last_valid_dmin = d_robust
        self._last_valid_time = self._now()
        return d_robust

    def decide(self, dist_by_deg, speed_mps):
        """
        입력: 각도별 거리(mm), 속도(m/s)
        출력: (level_str, info_dict)
          - level: "SAFE"/"MILD"/"STRONG"/"EMERGENCY"
          - info:  d_min_m, ttc_s, corner(ang, dist_mm), state
        """
        # 코너: 정면 180° 범위에서만 탐지
        corners = detect_corners_front_180(dist_by_deg)
        corner_flag = False
        corner_info = None
        if corners:
            ang_c, dist_c = min(corners, key=lambda x: x[1])  # 가장 가까운 코너
            corner_flag = True
            corner_info = (ang_c, dist_c)

        # 전방 최소거리(±20°)
        d_min = self.update_front_min(dist_by_deg)  # m
        ttc = None
        if d_min is not None and speed_mps is not None and speed_mps > 0.05:
            ttc = d_min / speed_mps

        # 상태/레벨
        if ttc is not None:
            if ttc < TTC_EMERGENCY:
                level = "EMERGENCY"; self.state = "EMERGENCY_STOP"
            elif ttc < TTC_DECELERATE:
                level = "STRONG";    self.state = "DECELERATE"
            elif ttc < TTC_WARNING:
                level = "MILD";      self.state = "WARNING"
            else:
                if corner_flag:
                    level = "MILD";  self.state = "SLOWDOWN_CORNER"
                else:
                    level = "SAFE";  self.state = "SAFE"
        else:
            # 거리/속도 불확실 → 보수적 감속
            level = "MILD"
            self.state = "WARNING" if not corner_flag else "SLOWDOWN_CORNER"

        info = {
            "d_min_m": d_min,
            "ttc_s": ttc,
            "corner": corner_info,
            "state": self.state,
            "level": level
        }
        return level, info