# esp32_comm.py
# 사용법:
#   esp = ESP32BrakeSerial() ; esp.connect()
#   esp.send_level("MILD")  # SAFE/MILD/STRONG/EMERGENCY
#   esp.close()

import time, glob
import serial

LEVEL_TO_ANGLE = {
    "SAFE":       300,  # 브레이크 풀림
    "MILD":       150,  # 감속
    "STRONG":     100,  # 강한 감속
    "EMERGENCY":  100,    # 풀 브레이크
}

CANDIDATE_PORTS = [
    "/dev/ttyACM0", "/dev/ttyACM1", "/dev/ttyACM2",
    "/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyUSB2",
]

class ESP32BrakeSerial:
    def __init__(self, port=None, baud=115200, timeout=0.05):
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.ser = None
        self._last_sent = None
        self._last_send_ts = 0.0
        self._min_interval = 0.05  # 너무 자주 보내지 않도록 (20Hz)

    def _auto_pick_port(self):
        if self.port:
            return self.port
        # 후보 + glob로 자동 탐색
        cands = list(CANDIDATE_PORTS)
        cands += glob.glob("/dev/ttyACM*")
        cands += glob.glob("/dev/ttyUSB*")
        # 중복 제거 / 정렬
        seen = set()
        ordered = []
        for p in cands:
            if p not in seen:
                seen.add(p)
                ordered.append(p)
        if not ordered:
            raise RuntimeError("ESP32 포트 자동 탐색 실패")
        return ordered[0]

    def connect(self):
        if self.ser and self.ser.is_open:
            return
        port = self._auto_pick_port()
        self.ser = serial.Serial(port, self.baud, timeout=self.timeout)
        time.sleep(1.0)  # 보드 리셋 대기
        self.ser.reset_input_buffer()
        self.port = port
        # 시작 시 현재 맵 요청(선택)
        self._write_line("GET MAP")
        print(f"[ESP32] connected on {self.port}")

    def _write_line(self, line: str):
        if not self.ser or not self.ser.is_open:
            return
        s = (line.strip().upper() + "\n").encode()
        self.ser.write(s)
        self.ser.flush()

    def send_angle(self, angle: int, force=False):
        """A:<angle> 전송. force=False면 같은 값 연속 전송 억제."""
        now = time.time()
        if not force and self._last_sent == ("ANGLE", angle) and (now - self._last_send_ts) < self._min_interval:
            return
        self._write_line(f"A:{int(angle)}")
        self._last_sent = ("ANGLE", int(angle))
        self._last_send_ts = now

    def send_level(self, level: str, force=False):
        """레벨 문자열을 ESP32 각도로 맵핑해 전송."""
        level = level.upper()
        if level not in LEVEL_TO_ANGLE:
            # 알 수 없는 레벨이면 무시
            return
        self.send_angle(LEVEL_TO_ANGLE[level], force=force)

    def poll_read(self):
        """ESP32의 한 줄 수신(없으면 빈 문자열). 필요시 로그 출력용."""
        if not self.ser or not self.ser.is_open:
            return ""
        try:
            line = self.ser.readline().decode(errors="ignore").strip()
            return line
        except Exception:
            return ""

    def close(self):
        try:
            if self.ser:
                self.ser.close()
        except Exception:
            pass
        self.ser = None