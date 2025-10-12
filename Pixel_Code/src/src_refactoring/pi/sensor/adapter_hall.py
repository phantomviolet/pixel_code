import re
import threading
import time
from typing import Optional

try:
    import serial  # pyserial
except ImportError:
    serial = None

STAT_RX = re.compile(
    r"STAT\b.*?(?:rpm=(?P<rpm>[-+]?\d+(?:\.\d+)?))?.*?(?:\bv=(?P<v>[-+]?\d+(?:\.\d+)?))?",
    re.IGNORECASE,
)

class HallSpeedAdapter:
    def __init__(
        self,
        ser: "serial.Serial" = None,
        port: Optional[str] = None,
        baud: int = 115200,
        prefer_v_from_esp32: bool = True,
        ema_alpha: float = 0.3,
        read_timeout_s: float = 0.1,
    ):
        if ser is None and serial is None:
            raise RuntimeError("pyserial not available")

        self._own_serial = False
        if ser is not None:
            # 공유 모드: 기존 시리얼 핸들을 그대로 사용
            self.ser = ser
            # timeout이 0이면 busy loop가 되니 약간의 timeout이 있는지 확인
            if getattr(self.ser, "timeout", None) is None or self.ser.timeout == 0:
                try:
                    self.ser.timeout = read_timeout_s
                except Exception:
                    pass
        else:
            # 단독 모드: 새로 연다
            if port is None:
                raise ValueError("Either 'ser' or 'port' must be provided")
            self.ser = serial.Serial(port=port, baudrate=baud, timeout=read_timeout_s)
            self._own_serial = True

        self.prefer_v = prefer_v_from_esp32
        self.alpha = max(0.0, min(1.0, ema_alpha))

        self._v_mps = 0.0
        self._rpm = 0.0
        self._alive = True
        self._lock = threading.Lock()

        self._th = threading.Thread(target=self._rx_loop, daemon=True)
        self._th.start()

    def _ema(self, old, new):
        a = self.alpha
        return (1 - a) * old + a * new

    def _rx_loop(self):
        buf = bytearray()
        while self._alive:
            try:
                chunk = self.ser.read(256)
                if not chunk:
                    continue
                buf.extend(chunk)
                # 라인 단위로 파싱
                while True:
                    nl = buf.find(b"\n")
                    if nl < 0:
                        break
                    line = buf[:nl].decode(errors="ignore").strip()
                    del buf[: nl + 1]

                    m = STAT_RX.search(line)
                    if not m:
                        continue

                    rpm_s = m.group("rpm")
                    v_s = m.group("v")

                    rpm = float(rpm_s) if rpm_s not in (None, "") else None
                    v_mps = float(v_s) if v_s not in (None, "") else None

                    with self._lock:
                        if rpm is not None:
                            self._rpm = self._ema(self._rpm, rpm)
                        # v 우선 사용 또는 rpm로부터 유도 (v 값이 없는 경우)
                        if self.prefer_v and v_mps is not None:
                            self._v_mps = self._ema(self._v_mps, max(0.0, v_mps))
                        elif rpm is not None:
                            # ESP32 펌웨어가 v를 안 보내는 경우 대비: 유도 불가 → v=NA 유지
                            # (필요시 여기서 바퀴 둘레 넣어 유도 가능)
                            pass

            except Exception:
                # 잠깐 쉬고 계속
                time.sleep(0.05)

    def read(self) -> Optional[float]:
        """현재 선속도(m/s). 값이 아직 없다면 마지막 값(초기 0.0)을 반환."""
        with self._lock:
            return self._v_mps

    def last_rpm(self) -> Optional[float]:
        with self._lock:
            return self._rpm

    def stop(self):
        self._alive = False
        # 소유 포트만 닫는다
        if self._own_serial:
            try:
                self.ser.close()
            except Exception:
                pass