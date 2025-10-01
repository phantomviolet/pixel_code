# comm.py
import serial, time

class Comm:
    def __init__(self, port="/dev/ttyACM0", baud=115200, timeout=0.2):
        self.ser = serial.Serial(port, baud, timeout=timeout)
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

    def _send_line(self, s: str):
        if not s.endswith("\n"):
            s += "\n"
        self.ser.write(s.encode())

    # ---- 공개 API ----
    def send_mode(self, mode: str):       # "NORMAL" | "CORNER"
        self._send_line(f"MODE {mode}")

    def send_cmd(self, cmd: str):         # "SAFE" | "SLOW" | "BRAKE"
        self._send_line(f"CMD {cmd}")

    def send_speed_cap(self, kmh: int):   # 코너 상한 속도
        self._send_line(f"SPD_CAP {int(kmh)}")

    def send_hb(self):                    # Heartbeat
        self._send_line("HB")

    def poll_events(self, duration_s=0.2, max_lines=50):
        """duration_s 동안 라인 수집 후 리스트로 반환"""
        out = []
        end = time.time() + duration_s
        while time.time() < end and len(out) < max_lines:
            line = self.ser.readline().decode(errors="ignore").strip()
            if line:
                out.append(line)
        return out

    def close(self):
        try: self.ser.close()
        except: pass