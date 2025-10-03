# -*- coding: utf-8 -*-
import time
from collections import deque
from statistics import median

# ====== 전방 정의 / 섹터 ======
SECTOR_HALF_DEG = 20                 # (참조용) 정면 ±20도
FRONT_CENTER_DEG = 0                 # 라이다 설치 각도 보정(필요시 90/180로 수정)

# 충돌 판단(전방 최소거리/TTC)용 섹터: 정면 좌우 ±20°
COLLISION_HALF_DEG = 20
# 코너 검출용 섹터: 정면 좌우 ±90° (정면 180° 전체)
CORNER_HALF_DEG = 90

# 거리 유효 범위(실험 중 임시 완화)
DIST_MIN_M = 0.10
DIST_MAX_M = 10.00

# d_min 안정화
ROLL_WIN = 3
HOLD_LAST_DMIN_SEC = 0.30

# TTC 임계(초) — 장애물 대응
TTC_EMERGENCY  = 1.2
TTC_DECELERATE = 2.0
TTC_WARNING    = 3.0

# 속도 임계
V_ZERO_EPS = 0.05              # m/s (≈0.18 km/h) : 사실상 정지
V_SAFE_CLEAR_MPS = 1.0 / 3.6   # m/s (1 km/h)     : 안전 속도 → Emergency 즉시 해제

# 코너 검출 파라미터
DERIV_THRESH_MM    = 400
MIN_PROMINENCE_MM  = 300
MIN_CORNER_DIST_MM = 300
MAX_CORNER_DIST_MM = 5000
ANGLE_SMOOTH       = 2

# Emergency Mode 해제 대기(위험 없음 유지 시간)
EMERGENCY_CLEAR_SEC = 1.0

# ===== 코너 ‘접근’ 판정 파라미터 =====
# 코너가 보이더라도 ‘접근’ 조건을 만족해야 감속/무장
CORNER_ACT_MIN_SPEED_MPS = 2.0 / 3.6   # 이 속도 이상일 때만 코너 감속/무장 시작 (≈ 2 km/h)
CORNER_SLOW_DIST_M       = 6.0         # 코너까지 이 거리 이내면 감속 시작(MILD)
CORNER_STRONG_DIST_M     = 3.0         # 이 거리 이내면 감속 STRONG
CORNER_TTC_SLOW_S        = 3.0         # 코너-TTC 3초 이내면 감속 시작
CORNER_APPROACH_GAIN_MM  = 150.0       # 직전 프레임 대비 이만큼(mm) 가까워지면 접근으로 인정
CORNER_HOLD_OFF_S        = 0.3         # 코너 접근 판정 히스테리시스(플러터 방지)

def wrap_angle(a: int) -> int:
    return a % 360

def _mm_to_m(dmm: float) -> float:
    return max(DIST_MIN_M, min(dmm / 1000.0, DIST_MAX_M))

def _iter_front_range(half_deg: int):
    start = FRONT_CENTER_DEG - half_deg
    end   = FRONT_CENTER_DEG + half_deg
    for ang in range(start, end + 1):
        yield wrap_angle(int(ang))

def detect_corners_front_180(dist_by_deg):
    """정면 180°(±90°) 범위에서 코너 후보 탐지"""
    corners = []
    front_set = set(_iter_front_range(CORNER_HALF_DEG))

    for ang in front_set:
        d0 = dist_by_deg[ang]
        if d0 is None or d0 <= 0:
            continue

        aL = wrap_angle(ang - ANGLE_SMOOTH)
        aR = wrap_angle(ang + ANGLE_SMOOTH)
        if aL not in front_set or aR not in front_set:
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
    """정면 180°: d_min/TTC(±20°), 코너(±90°) + Emergency Mode(무장/해제) + 코너 ‘접근’ 기반 감속"""
    def __init__(self):
        self.dist_queue = deque(maxlen=ROLL_WIN)
        self.state = "SAFE"
        self._last_valid_dmin = None
        self._last_valid_time = 0.0

        # Emergency Mode 상태
        self.emergency_mode = False
        self._risk_low_since = None

        # 코너 접근 히스토리
        self._prev_corner_dist_m = None
        self._corner_active_until = 0.0  # 접근 판정 유지 히스테리시스

    def _now(self):
        return time.time()

    def update_front_min(self, dist_by_deg):
        """충돌 판단용 전방 최소거리(m): ±20°, 폴백=정면 180°, 마지막 유효값 유지"""
        samples = []
        for a in _iter_front_range(COLLISION_HALF_DEG):
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

        self.dist_queue.append(d_min)
        d_robust = median(self.dist_queue)
        self._last_valid_dmin = d_robust
        self._last_valid_time = self._now()
        return d_robust

    def _corner_approach_decision(self, corner_mm, speed_mps):
        """
        코너 ‘접근’ 여부/강도 판단.
        반환: (corner_active(bool), corner_level_str['MILD'|'STRONG'|None], corner_ttc_s or None, corner_dist_m or None)
        """
        if corner_mm is None:
            self._prev_corner_dist_m = None
            return False, None, None, None

        dist_m = _mm_to_m(corner_mm)
        now = self._now()

        # 코너 TTC
        corner_ttc = None
        if speed_mps is not None and speed_mps > V_ZERO_EPS:
            corner_ttc = dist_m / speed_mps

        # ‘접근’ 조건: (속도 조건 AND (거리 또는 코너-TTC 조건)) OR (직전 대비 충분히 접근)
        v_ok   = (speed_mps is not None and speed_mps >= CORNER_ACT_MIN_SPEED_MPS)
        d_ok   = (dist_m <= CORNER_SLOW_DIST_M)
        ttc_ok = (corner_ttc is not None and corner_ttc <= CORNER_TTC_SLOW_S)

        approaching = False
        if self._prev_corner_dist_m is not None:
            if (self._prev_corner_dist_m - dist_m) * 1000.0 >= CORNER_APPROACH_GAIN_MM:
                approaching = True

        corner_active = v_ok and (d_ok or ttc_ok or approaching)

        # 히스테리시스: 한번 활성되면 짧게 유지(플러터 방지)
        if corner_active:
            self._corner_active_until = now + CORNER_HOLD_OFF_S
        else:
            if now < self._corner_active_until:
                corner_active = True  # 유지

        # 강도: 거리 기반
        corner_level = None
        if corner_active:
            if dist_m <= CORNER_STRONG_DIST_M:
                corner_level = "STRONG"
            else:
                corner_level = "MILD"

        # 업데이트
        self._prev_corner_dist_m = dist_m
        return corner_active, corner_level, corner_ttc, dist_m

    def decide(self, dist_by_deg, speed_mps):
        """
        입력: 각도별 거리(mm), 속도(m/s)
        출력: (level_str, info_dict)
        """
        # --- 코너 검출 (정면 180°) ---
        corners = detect_corners_front_180(dist_by_deg)
        corner_flag = False
        corner_info = None
        corner_mm = None
        if corners:
            ang_c, dist_c = min(corners, key=lambda x: x[1])  # 가장 가까운 코너
            corner_flag = True
            corner_info = (ang_c, dist_c)
            corner_mm = dist_c

        # --- 전방 최소거리 & 장애물 TTC ---
        d_min = self.update_front_min(dist_by_deg)  # m
        ttc = None
        v_is_zero = (speed_mps is not None and speed_mps <= V_ZERO_EPS)
        if (not v_is_zero) and d_min is not None and speed_mps is not None and speed_mps > V_ZERO_EPS:
            ttc = d_min / speed_mps

        # ⭐ 속도가 1 km/h 이하이면 Emergency Mode 즉시 해제
        if self.emergency_mode and (speed_mps is not None and speed_mps <= V_SAFE_CLEAR_MPS):
            self.emergency_mode = False
            self._risk_low_since = None

        # --- 코너 ‘접근’ 판정 (거리/코너-TTC/접근 추세) ---
        corner_active, corner_level, corner_ttc, corner_dist_m = self._corner_approach_decision(corner_mm, speed_mps)

        # --- Emergency Mode 진입/유지/해제 로직 ---
        now = self._now()

        # 1) 코너 ‘접근’일 때만 Emergency 무장(진입)
        if corner_active and not self.emergency_mode:
            self.emergency_mode = True
            self._risk_low_since = None  # 타이머 초기화

        # 2) 위험 수준 판단(장애물용)
        danger_now = (ttc is not None and ttc < TTC_EMERGENCY)  # 즉시 위험
        risk_low = (v_is_zero or (ttc is None) or (ttc >= TTC_WARNING and not corner_active))

        # 3) 모드 해제 타이머
        if self.emergency_mode:
            if risk_low:
                if self._risk_low_since is None:
                    self._risk_low_since = now
                elif (now - self._risk_low_since) >= EMERGENCY_CLEAR_SEC:
                    self.emergency_mode = False
                    self._risk_low_since = None
            else:
                self._risk_low_since = None

        # --- 출력 레벨 결정 ---
        if v_is_zero:
            level = "SAFE"; self.state = "SAFE"
        else:
            if self.emergency_mode:
                # 무장 중: 장애물 위험이면 즉시 EMERGENCY
                if danger_now:
                    level = "EMERGENCY"; self.state = "EMERGENCY_STOP"
                else:
                    # 코너 감속 우선(접근 상태면 corner_level 사용)
                    if corner_active and corner_level:
                        level = corner_level
                        self.state = "SLOWDOWN_CORNER"
                    else:
                        # TTC 기반 일반 감속
                        if ttc is not None:
                            if ttc < TTC_DECELERATE:
                                level = "STRONG";    self.state = "DECELERATE"
                            elif ttc < TTC_WARNING:
                                level = "MILD";      self.state = "WARNING"
                            else:
                                level = "SAFE";      self.state = "SAFE"
                        else:
                            level = "MILD"; self.state = "WARNING"
            else:
                # 일반 주행(모드 OFF): EMERGENCY 금지, 코너 ‘접근’이면 코너 감속만 수행
                if corner_active and corner_level:
                    level = corner_level
                    self.state = "SLOWDOWN_CORNER"
                else:
                    if ttc is not None:
                        if ttc < TTC_DECELERATE:
                            level = "STRONG";    self.state = "DECELERATE"
                        elif ttc < TTC_WARNING:
                            level = "MILD";      self.state = "WARNING"
                        else:
                            level = "SAFE";      self.state = "SAFE"
                    else:
                        level = "MILD"; self.state = "WARNING"

        info = {
            "d_min_m": d_min,
            "ttc_s": ttc,
            "corner": corner_info,
            "corner_active": corner_active,
            "corner_ttc_s": corner_ttc,
            "corner_dist_m": corner_dist_m,
            "state": self.state,
            "level": level,
            "emergency_mode": self.emergency_mode,
            "risk_low_since": self._risk_low_since
        }
        return level, info