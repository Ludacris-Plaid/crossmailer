# -*- coding: utf-8 -*-
import sys
import os
from PyQt5 import QtWidgets, QtCore, QtGui
from .status_panel import StatusPanel
from engine.mailer import Mailer
from smtp_manager.manager import SMTPManager
from scheduler.warmup import WarmupScheduler
from security.crypto import CryptoHelper

class MainWindow(QtWidgets.QMainWindow):
    emailSent    = QtCore.pyqtSignal(bool, str)
    rateUpdated  = QtCore.pyqtSignal(int)
    serverChanged= QtCore.pyqtSignal(str, int)
    warmupStage  = QtCore.pyqtSignal(int, int, int)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("CrossMailer Control Panel")
        self._apply_style()
        self._setup_helpers()
        self._build_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # Load stylesheet and add a tiny shadow
    # ------------------------------------------------------------------
    def _apply_style(self):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        style_path = os.path.join(base_dir, "resources", "style.qss")
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        else:
            print("⚠️ Style file not found - using default Qt look.")
        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(8)
        shadow.setXOffset(0)
        shadow.setYOffset(2)
        shadow.setColor(QtGui.QColor(0, 0, 0, 30))
        self._status_shadow = shadow

    # ------------------------------------------------------------------
    # Initialise helper objects
    # ------------------------------------------------------------------
    def _setup_helpers(self):
        passphrase, ok = QtWidgets.QInputDialog.getText(
            self, "Master Passphrase", "Enter the secret key:",
            QtWidgets.QLineEdit.Password
        )
        if not ok:
            sys.exit(0)

        self.crypto   = CryptoHelper(passphrase)
        self.smtp_mgr = SMTPManager(self.crypto)
        self.warmup   = WarmupScheduler()
        self.mailer   = Mailer(self.crypto, self.smtp_mgr, stats_callback=self)

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_layout = QtWidgets.QVBoxLayout(central)

        ctrl_bar = QtWidgets.QHBoxLayout()
        self.start_btn = QtWidgets.QPushButton("Start Campaign")
        self.stop_btn  = QtWidgets.QPushButton("Stop Campaign")
        self.rate_spin = QtWidgets.QSpinBox()
        self.rate_spin.setRange(10, 10000)
        self.rate_spin.setSuffix(" emails / hr")
        ctrl_bar.addWidget(self.start_btn)
        ctrl_bar.addWidget(self.stop_btn)
        ctrl_bar.addWidget(self.rate_spin)

        self.status_panel = StatusPanel()
        self.status_panel.setGraphicsEffect(self._status_shadow)

        self.tabs = QtWidgets.QTabWidget()
        placeholder = QtWidgets.QLabel("Tabs will appear here")
        placeholder.setAlignment(QtCore.Qt.AlignCenter)
        self.tabs.addTab(placeholder, "Dashboard")

        main_layout.addLayout(ctrl_bar)
        main_layout.addWidget(self.status_panel)
        main_layout.addWidget(self.tabs)

    # ------------------------------------------------------------------
    # Connect signals
    # ------------------------------------------------------------------
    def _connect_signals(self):
        self.start_btn.clicked.connect(self.start_campaign)
        self.stop_btn.clicked .clicked.connect(self.stop_campaign)

        self.emailSent.connect(self._handle_email_result)
        self.rateUpdated.connect(self.status_panel.set_rate)
        self.serverChanged.connect(self.status_panel.set_server)
        self.warmupStage.connect(self.status_panel.set_warmup)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------
    @QtCore.pyqtSlot(bool, str)
    def _handle_email_result(self, success: bool, error: str = ""):
        if success:
            self.status_panel.log("✅ Email sent")
        else:
            self.status_panel.log(f"❌ Send failed - {error}")

    def start_campaign(self):
        target_rate = self.rate_spin.value()
        self.warmup.configure(target_rate)
        self.warmup.stage_changed.connect(self.warmupStage.emit)
        self.warmup.start()
        self.status_panel.set_running(True)

    def stop_campaign(self):
        self.warmup.stop()
        self.status_panel.set_running(False)

    # ------------------------------------------------------------------
    # Callbacks used by Mailer
    # ------------------------------------------------------------------
    def email_sent(self, success: bool, error: str = ""):
        self.emailSent.emit(success, error)

    def update_rate(self, msgs_per_min: int):
        self.rateUpdated.emit(msgs_per_min)

    def server_updated(self, host: str, health: int):
        self.serverChanged.emit(host, health)
