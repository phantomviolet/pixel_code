# -*- coding: utf-8 -*-
# 서보 모터 도착 전: 스텁(프린트만). 도착 후 내부만 교체하면 됨.

class BrakeLevel:
    SAFE = "SAFE"          # 해제
    MILD = "MILD"          # 약감속
    STRONG = "STRONG"      # 강감속
    EMERGENCY = "EMERGENCY" # 긴급정지

class BrakeController:
    def __init__(self):
        pass

    def set_level(self, level: str):
        print(f"[서보 작동] 브레이크 레벨 = {level}")
        return True

    def set_angle(self, angle_deg: int):
        print(f"[서보 작동] 각도 = {angle_deg}°")
        return True

    def release(self):
        print("[서보 작동] 브레이크 해제")
        return True