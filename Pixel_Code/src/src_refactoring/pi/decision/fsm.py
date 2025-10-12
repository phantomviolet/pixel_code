# -*- coding: utf-8 -*-
from dataclasses import dataclass
import math
import time
from typing import Optional, Dict, Any

@dataclass
class FsmParams:
    # 주행 임계값(초/거리)
    warn_ttc_s: float = 1.7
    brake_ttc_s: float = 1.2
    brake_dist_mm: int = 600
    brake_release_dist_mm: int = 1000

    # 정지 전용 경고 임계값(거리) — (현재 로직에선 미사용/호환용으로만 보관)
    stop_warn_dist_mm: int = 300  # d < 이 값이면 WARN, 아니면 SAFE (※ 패치 후 미사용)

    # 기본 속도 추정치 (v_mps 미제공 시)
    v_est_mps: float = 0.5

    # FAILSAFE 히스테리시스(연속 프레임 수)
    lost_frames_to_fail: int = 3
    ok_frames_to_recover: int = 2

    # BRAKE 해제 히스테리시스(연속 프레임 수)
    brake_exit_frames: int = 2

    # 로그/디버그
    verbose: bool = False

    # 서보 각도 매핑
    safe_deg: int = 0
    warn_deg: int = 100
    brake_deg: int = 140
    failsafe_deg: int = 140

    # 보호/안정화 파라미터
    v_zero_threshold_mps: float = 0.05   # 이하면 '정지/극저속'
    ttc_cap_s: float = 6.0               # TTC 상한
    dmin_floor_mm: int = 1               # 0 또는 음수 거리 보호

class DecisionFSM:
    def __init__(self, params: Optional[FsmParams] = None):
        self.p = params or FsmParams()
        self.state: str = "SAFE"
        self.last_change: float = time.time()

        # 센서 유효/무효 카운터
        self._lost_cnt: int = 0
        self._ok_cnt: int = 0

        # BRAKE 해제 카운터
        self._brake_exit_ok_cnt: int = 0

        # 최근 측정
        self.last_d_min_mm: Optional[float] = None
        self.last_ttc_s: Optional[float] = None

    # ---------- 내부 유틸 ----------
    def _set_state(self, s: str, reason: str):
        if s != self.state:
            if self.p.verbose:
                print(f"[FSM] {self.state} → {s}  ({reason})")
            self.state = s
            self.last_change = time.time()
            if s != "BRAKE":
                self._brake_exit_ok_cnt = 0

    def _target_for(self, state: str) -> int:
        return {
            "SAFE": self.p.safe_deg,
            "WARN": self.p.warn_deg,
            "BRAKE": self.p.brake_deg,
            "FAILSAFE": self.p.failsafe_deg,
        }.get(state, self.p.safe_deg)

    def _ttc_from_dist(self, d_min_mm: Optional[float], v_mps: Optional[float]) -> Optional[float]:
        """
        TTC 계산:
        - d <= floor → 0.0 (충돌 직전 보호)
        - v is None → TTC 미사용(None)
        - v <= threshold(정지/극저속) → TTC=0.0 (정지)
        - 정상 주행 → TTC = min(d/v, cap)
        """
        if d_min_mm is None:
            return None
        if d_min_mm <= self.p.dmin_floor_mm:
            return 0.0

        if v_mps is None:
            return None

        v = v_mps
        if v <= self.p.v_zero_threshold_mps:
            return 0.0  # 정지/극저속

        ttc = (d_min_mm / 1000.0) / v
        if not math.isfinite(ttc) or ttc < 0:
            return 0.0
        return min(ttc, self.p.ttc_cap_s)

    # ---------- 외부 API ----------
    def reset(self):
        self.__init__(self.p)

    def update(self, d_min_mm: Optional[float], v_mps: Optional[float] = None) -> Dict[str, Any]:
        # 유효/무효 카운팅
        if d_min_mm is None or d_min_mm <= 0:
            self._lost_cnt += 1
            self._ok_cnt = 0
        else:
            self._ok_cnt += 1
            self._lost_cnt = 0

        # FAILSAFE 진입/복귀
        if self.state != "FAILSAFE" and self._lost_cnt >= self.p.lost_frames_to_fail:
            self._set_state("FAILSAFE", "sensor_lost_frames")
        elif self.state == "FAILSAFE" and self._ok_cnt >= self.p.ok_frames_to_recover:
            self._set_state("SAFE", "sensor_recovered")

        if self.state == "FAILSAFE":
            return {
                "state": "FAILSAFE",
                "target_deg": self._target_for("FAILSAFE"),
                "d_min_mm": d_min_mm,
                "v_mps": v_mps,
                "ttc": None,
                "reason": "sensor_lost",
            }

        # TTC 계산
        ttc = self._ttc_from_dist(d_min_mm, v_mps)
        self.last_d_min_mm = d_min_mm
        self.last_ttc_s = ttc

        new_state = self.state
        reason = "tick"
        target = self._target_for(self.state)

        if d_min_mm is not None:
            # ===== 정지/극저속: 항상 SAFE =====
            if ttc == 0.0:
                new_state, target, reason = "SAFE", self.p.safe_deg, "stop_mode_always_safe"

            # ===== TTC 미계산(None): 거리-only (필요시 WARN/BRAKE) =====
            elif ttc is None:
                if d_min_mm < self.p.brake_dist_mm:
                    # 센서 v 결측인데 거리가 매우 가깝다 → 안전 상 BRAKE 유지
                    new_state, target, reason = "BRAKE", self.p.brake_deg, "dist_only_brake_no_ttc"
                elif self.state == "BRAKE":
                    if d_min_mm > self.p.brake_release_dist_mm:
                        self._brake_exit_ok_cnt += 1
                        if self._brake_exit_ok_cnt >= self.p.brake_exit_frames:
                            new_state, target, reason = "SAFE", self.p.safe_deg, "dist_only_release_no_ttc"
                    else:
                        self._brake_exit_ok_cnt = 0
                    target = self.p.brake_deg
                elif d_min_mm < self.p.brake_release_dist_mm:
                    new_state, target, reason = "WARN", self.p.warn_deg, "dist_only_warn_no_ttc"
                else:
                    new_state, target, reason = "SAFE", self.p.safe_deg, "dist_only_safe_no_ttc"

            # ===== 정상 주행: TTC + 거리 =====
            else:
                if d_min_mm < self.p.brake_dist_mm or ttc <= self.p.brake_ttc_s:
                    if self.state != "BRAKE":
                        self._brake_exit_ok_cnt = 0
                    new_state, target, reason = "BRAKE", self.p.brake_deg, "dist_or_ttc_below_brake"
                elif self.state == "BRAKE":
                    cond1 = d_min_mm > self.p.brake_release_dist_mm
                    cond2 = ttc > self.p.warn_ttc_s * 1.1
                    if cond1 or cond2:
                        self._brake_exit_ok_cnt += 1
                        if self._brake_exit_ok_cnt >= self.p.brake_exit_frames:
                            new_state, target, reason = "SAFE", self.p.safe_deg, "brake_release_ok"
                    else:
                        self._brake_exit_ok_cnt = 0
                    target = self.p.brake_deg
                elif ttc <= self.p.warn_ttc_s:
                    new_state, target, reason = "WARN", self.p.warn_deg, "ttc_below_warn"
                else:
                    new_state, target, reason = "SAFE", self.p.safe_deg, "normal_safe"

        self._set_state(new_state, reason)

        return {
            "state": self.state,
            "target_deg": self._target_for(self.state),
            "d_min_mm": d_min_mm,
            "v_mps": v_mps,
            "ttc": None if ttc is None else round(ttc, 2),
            "reason": reason,
        }