import threading, time
from PyQt5 import QtCore

class WarmupScheduler(QtCore.QObject):
    """Emits stage_changed(stage, total, target_rate) as the warm‑up progresses."""
    stage_changed = QtCore.pyqtSignal(int, int, int)

    def __init__(self):
        super().__init__()
        self._target_rate = 1000
        self._running = False
        self._thread = None
        self._stages = [50,100,200,400,800]   # simple exponential ramp

    def configure(self, target_rate):
        self._target_rate = target_rate
        self._full_stages = self._stages + [target_rate]

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join()

    def _run(self):
        total = len(self._full_stages)
        for idx, rate in enumerate(self._full_stages, start=1):
            if not self._running:
                break
            self.stage_changed.emit(idx, total, rate)
            # Demo uses 5 seconds per stage; replace 5 with 7200 for a real 2‑hour stage
            wait_seconds = 5
            elapsed = 0
            while elapsed < wait_seconds and self._running:
                time.sleep(1)
                elapsed += 1
