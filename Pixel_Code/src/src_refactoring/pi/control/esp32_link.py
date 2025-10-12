# pi/control/esp32_link.py
# -*- coding: utf-8 -*-
import time
import yaml
import serial

class Esp32Link:
    """
    ESP32와의 직렬 통신 래퍼
    - 짧은 타임아웃/논블로킹 읽기
    - GET_STAT 입력버퍼 purge 후 즉시 응답 대기
    - 마지막 정상 응답을 캐시하여 끊김 시 반환
    """
    def __init__(self, port, baud=115200, timeout=0.1, write_timeout=0.1):
        self.ser = serial.Serial(
            port=port,
            baudrate=baud,
            timeout=timeout,
            write_timeout=write_timeout
        )
        self._last_stat = ""  # 마지막 STAT 라인 캐시

    # ---------- 내부 유틸 ----------
    def _write_line(self, s: str):
        self.ser.write((s + "\n").encode("ascii"))

    def _read_line(self, timeout=0.15):
        """
        최대 timeout 동안 '\n'까지 비차단식으로 읽어 한 줄 반환.
        없으면 빈 문자열 반환.
        """
        t0 = time.time()
        buf = bytearray()
        while time.time() - t0 < timeout:
            b = self.ser.read(1)
            if not b:
                continue
            if b == b'\n':
                break
            buf.extend(b)
        return buf.decode("ascii", errors="ignore").strip()

    # ---------- 공개 API ----------
    def ping(self, timeout=0.2):
        try:
            self.ser.reset_input_buffer()
            self._write_line("PING")
            line = self._read_line(timeout)
            return line or ""
        except Exception as e:
            return f"ERR {e}"

    def quiet(self, on: bool = True, timeout=0.2):
        """
        ESP32가 주기적으로 STAT를 푸시하는 모드가 있다면 끄고(quiet=1),
        폴링(GET_STAT)만 하도록 전환.
        """
        try:
            self.ser.reset_input_buffer()
            self._write_line(f"QUIET {1 if on else 0}")
            line = self._read_line(timeout)
            return line or ""
        except Exception as e:
            return f"ERR {e}"

    def set_deg(self, deg: int, timeout=0.2):
        try:
            self._write_line(f"SET_DEG {int(deg)}")
            line = self._read_line(timeout)
            return line or ""
        except Exception as e:
            return f"ERR {e}"

    def set_us(self, us: int, timeout=0.2):
        """
        서보 펄스폭(마이크로초) 직접 설정.
        CLI의 --us가 이 메서드를 호출함.
        """
        try:
            # (선택) 범위 체크: 보통 500~2500us
            # if not (500 <= int(us) <= 2500):
            #     return "ERR out_of_range"
            self._write_line(f"SET_US {int(us)}")
            line = self._read_line(timeout)
            return line or ""
        except Exception as e:
            return f"ERR {e}"

    def get_stat(self, timeout=0.15, retries=1, purge=True):
        """
        빠른 왕복 STAT
        - purge=True면 요청 전 input buffer 비움
        - 응답이 없으면 짧게 재시도 후 마지막 캐시 반환(루프 블록 방지)
        """
        try:
            if purge:
                self.ser.reset_input_buffer()
            self._write_line("GET_STAT")
            line = self._read_line(timeout)
            if (not line) and retries > 0:
                self._write_line("GET_STAT")
                line = self._read_line(timeout)
            if line:
                self._last_stat = line
            return self._last_stat
        except Exception:
            # 예외 시에도 캐시 반환
            return self._last_stat or ""

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass


def open_from_config(cfg_path: str):
    """
    config.yaml 의 comm 섹션을 읽어 Esp32Link 생성
    예)
    comm:
      port: /dev/serial/by-id/usb-...
      baud: 115200
      timeout: 0.1
      write_timeout: 0.1
    """
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    c = (cfg.get("comm") or {})
    port = c.get("port", "/dev/ttyACM0")
    baud = int(c.get("baud", 115200))
    timeout = float(c.get("timeout", 0.1))
    wtimeout = float(c.get("write_timeout", 0.1))
    return Esp32Link(port=port, baud=baud, timeout=timeout, write_timeout=wtimeout)