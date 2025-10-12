# pi/sensor/adapter_sim.py
import time, math, random

class SimulatedSensor:
    """
    전방 거리(d_min_mm)를 가짜로 생성하는 시뮬레이터.
    시나리오:
      - A: 항상 SAFE
      - B: 장애물이 접근(WARN→BRAKE)
      - C: 센서 장애 (랜덤 dropout)
    """
    def __init__(self, scenario="B"):
        self.scenario = scenario
        self.t0 = time.time()

    def read(self):
        t = time.time() - self.t0
        if self.scenario == "A":
            d = 2000 + 200*math.sin(t/5)
        elif self.scenario == "B":
            # 3초 동안 2m → 0.3m로 접근
            if t < 3:
                d = 2000 - 600*t
            else:
                d = 300 + 100*math.sin(t*2)
        elif self.scenario == "C":
            if random.random() < 0.2:
                return None  # dropout
            d = 1000 + 500*math.sin(t)
        else:
            d = 2000
        return max(100, d)  # mm