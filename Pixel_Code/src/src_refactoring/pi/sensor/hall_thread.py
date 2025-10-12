# -*- coding: utf-8 -*-
import re, time, threading
from pi.control.esp32_link import open_from_config

STAT_RX = re.compile(r"\brpm=(?P<rpm>[-+]?\d+(?:\.\d+)?)\b.*?\bv=(?P<v>[-+]?\d+(?:\.\d+)?)\b", re.I)

class HallThread(threading.Thread):
    def __init__(self, cfg_path="pi/config.yaml", poll_ms=50, stale_s=0.5):
        super().__init__(daemon=True)
        self._stop = threading.Event()
        self._v_mps = None
        self._ts = 0.0
        self._poll_ms = poll_ms
        self._stale_s = stale_s
        self.link = open_from_config(cfg_path)

    def run(self):
        # (선택) QUIET 모드로 전환
        try: self.link.quiet(True)
        except: pass
        while not self._stop.is_set():
            try:
                line = self.link.get_stat(timeout=0.12, retries=1, purge=True)
                m = STAT_RX.search(line or "")
                if m:
                    self._v_mps = float(m.group("v"))
                    self._ts = time.time()
            except:
                pass
            self._stop.wait(self._poll_ms / 1000.0)

    def get_speed(self):
        """신선한 값만 반환, 오래되면 None"""
        if self._v_mps is None: return None
        if (time.time() - self._ts) > self._stale_s: return None
        return self._v_mps

    def stop(self):
        self._stop.set()
        try: self.link.close()
        except: pass