# -*- coding: utf-8 -*-
import csv, time, math, os

class ReplaySensor:
    def __init__(self, csv_path, rate_hz=10.0,
                 gap_fill=True,             # 🔹 NA 보정 켜기
                 max_gap_frames=5,          # 🔹 연속 NA ≤5프레임까지만 보정
                 end_policy="stop",         # 🔹 "stop"|"hold"|"loop"
                 hold_seconds=2.0):         # end_policy="hold"일 때 유지 시간
        assert os.path.exists(csv_path), f"no file: {csv_path}"
        self.rows = []
        with open(csv_path, "r") as f:
            r = csv.DictReader(f)
            for row in r:
                self.rows.append(row)
        self.dt = 1.0 / max(1e-3, rate_hz)
        self.i = 0
        self.gap_fill = gap_fill
        self.max_gap = max_gap_frames
        self.end_policy = end_policy
        self.hold_frames = int(hold_seconds / self.dt)
        self._last_valid = None
        self._hold_left = 0

    def _parse_mm(self, v):
        try:
            return float(v) if v not in (None, "", "NA") else None
        except:
            return None

    def read(self):
        # 파일 끝 처리
        if self.i >= len(self.rows):
            if self.end_policy == "loop":
                self.i = 0
            elif self.end_policy == "hold" and self._last_valid is not None:
                if self._hold_left <= 0:
                    self._hold_left = self.hold_frames
                self._hold_left -= 1
                time.sleep(self.dt)
                return self._last_valid
            else:  # stop(default)
                time.sleep(self.dt)
                return None

        # 현재 프레임
        row = self.rows[self.i]; self.i += 1
        d = self._parse_mm(row.get("d_min_mm"))

        # 🔹 갭-필: 최근값 홀드(최대 max_gap 프레임)
        if d is None and self.gap_fill and self._last_valid is not None:
            # 앞으로도 연속 NA인지 살짝 엿봄
            gap = 1
            j = self.i
            while gap < self.max_gap and j < len(self.rows):
                dpeek = self._parse_mm(self.rows[j].get("d_min_mm"))
                if dpeek is not None:
                    break
                gap += 1; j += 1
            d = self._last_valid  # 홀드

        if d is not None:
            self._last_valid = d

        time.sleep(self.dt)
        return d

    def stop(self): pass