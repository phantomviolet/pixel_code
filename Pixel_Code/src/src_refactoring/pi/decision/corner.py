# -*- coding: utf-8 -*-
import time
import math

class CornerParams:
    """
    코너 감속기 설정값
    """
    def __init__(self,
                 enter_dist_mm=1000,         # 좌/우 거리 차이가 커지고 진입 거리 짧을 때 진입
                 leave_dist_mm=1500,         # 충분히 멀어지면 해제
                 side_imbalance_mm=1200,      # 좌/우 거리 차이로 코너 판단 기준
                 front_drop_mmps=200,        # 정면 거리 감소율로 접근 판단
                 rec_speed_kmh=10.0):        # 감속 목표속도(km/h)
        self.enter_dist_mm = enter_dist_mm
        self.leave_dist_mm = leave_dist_mm
        self.side_imbalance_mm = side_imbalance_mm
        self.front_drop_mmps = front_drop_mmps
        self.rec_speed_mps = rec_speed_kmh / 3.6


class CornerDetector:
    """
    코너 감속 판정기
    - LIDAR 섹터 거리 기반으로 코너 접근 감지
    - FSM 충돌방지와 독립 동작 (state 오버라이드용)
    """

    def __init__(self, p: CornerParams):
        self.p = p
        self.active = False
        self.last_side_diff = 0.0
        self.last_update_t = 0.0

    def update(self, d_front, d_left, d_right, v_mps):
        """
        코너 감속 판정 업데이트
        returns dict:
            {
                "active": bool,
                "rec_speed_mps": float,
                "score": float,
                "reason": str
            }
        """
        now = time.time()
        dt = now - self.last_update_t if self.last_update_t else 0.1
        self.last_update_t = now

        if any(v is None for v in [d_front, d_left, d_right]):
            return {"active": self.active, "rec_speed_mps": self.p.rec_speed_mps, "score": 0.0, "reason": "no_data"}

        side_diff = abs(d_left - d_right)
        side_bias = "left" if d_left < d_right else "right"

        # 기본 점수 계산
        imbalance_score = side_diff / max(1.0, self.p.side_imbalance_mm)
        approach_score = 0.0
        if d_front < self.p.enter_dist_mm:
            approach_score += 1.0
        if abs(self.last_side_diff - side_diff) / max(1, dt) > 100:
            approach_score += 0.5

        total_score = imbalance_score + approach_score

        # 진입/해제 조건
        reason = ""
        if not self.active:
            if (d_front < self.p.enter_dist_mm and side_diff > self.p.side_imbalance_mm):
                self.active = True
                reason = f"corner_enter_{side_bias}"
        else:
            if (d_front > self.p.leave_dist_mm or side_diff < self.p.side_imbalance_mm * 0.6):
                self.active = False
                reason = "corner_leave"
            else:
                reason = "corner_hold"

        self.last_side_diff = side_diff

        return {
            "active": self.active,
            "rec_speed_mps": self.p.rec_speed_mps,
            "score": total_score,
            "reason": reason
        }