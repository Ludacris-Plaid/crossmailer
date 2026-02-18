# -*- coding: utf-8 -*-
import sys
from PyQt5 import QtWidgets, QtCore

class StatusPanel(QtWidgets.QGroupBox):
    """Reusable live-status widget (Hush Circuits inspired)."""
    def __init__(self, parent=None):
        super().__init__("Live Status", parent)
        self._build_ui()
        self._style_defaults()

    def _build_ui(self):
        layout = QtWidgets.QGridLayout(self)

        self.health_lbl   = QtWidgets.QLabel("Health: ⛔ Stopped")
        self.rate_lbl     = QtWidgets.QLabel("Rate: 0 emails / min")
        self.server_lbl   = QtWidgets.QLabel("SMTP: -")
        self.warmup_lbl   = QtWidgets.QLabel("Warm-Up: -")
        self.log_box      = QtWidgets.QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumHeight(80)

        layout.addWidget(self.health_lbl, 0, 0)
        layout.addWidget(self.rate_lbl,   0, 1)
        layout.addWidget(self.server_lbl, 1, 0)
        layout.addWidget(self.warmup_lbl, 1, 1)
        layout.addWidget(self.log_box,    2, 0, 1, 2)

    def _style_defaults(self):
        self.health_lbl.setStyleSheet("color: gray;")
        self.rate_lbl.setStyleSheet("color: gray;")
        self.server_lbl.setStyleSheet("color: gray;")
        self.warmup_lbl.setStyleSheet("color: gray;")

    @QtCore.pyqtSlot(bool)
    def set_running(self, running: bool):
        if running:
            self.health_lbl.setText("Health: ✅ Running")
            self.health_lbl.setStyleSheet("color: green;")
        else:
            self.health_lbl.setText("Health: ⛔ Stopped")
            self.health_lbl.setStyleSheet("color: red;")

    @QtCore.pyqtSlot(int)
    def set_rate(self, msgs_per_min: int):
        self.rate_lbl.setText(f"Rate: {msgs_per_min} emails / min")
        self.rate_lbl.setStyleSheet("color: teal;")

    @QtCore.pyqtSlot(str, int)
    def set_server(self, host: str, health: int):
        self.server_lbl.setText(f"SMTP: {host} ({health}% OK)")
        self.server_lbl.setStyleSheet("color: teal;")

    @QtCore.pyqtSlot(int, int, int)
    def set_warmup(self, stage: int, total: int, target: int):
        self.warmup_lbl.setText(
            f"Warm-Up: Stage {stage}/{total} - Target {target} emails / hr"
        )
        self.warmup_lbl.setStyleSheet("color: teal;")

    @QtCore.pyqtSlot(str)
    def log(self, message: str):
        ts = QtCore.QDateTime.currentDateTime().toString("HH:mm:ss")
        self.log_box.append(f"[{ts}] {message}")
        lines = self.log_box.toPlainText().splitlines()
        if len(lines) > 5:
            self.log_box.setPlainText("\n".join(lines[-5:]))
