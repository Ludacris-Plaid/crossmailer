# -*- coding: utf-8 -*-
import sys
import os
import sqlite3
from PyQt5 import QtWidgets, QtCore, QtGui
from .status_panel import StatusPanel
from .recipient_tab import RecipientTab
from .ai_tab import AITab
from engine.mailer import Mailer
from engine.worker import CampaignWorker
from engine.recipient_manager import RecipientManager
from engine.tracker_server import TrackingServer
from engine.inbox_monitor import InboxMonitor
from engine.proxy_harvester import ProxyHarvester
from engine.sentinel import LogSentinel
from engine.mvp_agent import MVPAuditAgent
from engine.ai_supervisor import AISupervisor
from smtp_manager.manager import SMTPManager
from scheduler.warmup import WarmupScheduler
from security.crypto import CryptoHelper
from engine.sequence_manager import SequenceManager
from dbutil import connect


class MainWindow(QtWidgets.QMainWindow):
    # ------------------------------------------------------------------
    # Signals emitted by background threads
    # ------------------------------------------------------------------
    emailSent    = QtCore.pyqtSignal(bool, str)
    rateUpdated  = QtCore.pyqtSignal(int)
    serverChanged= QtCore.pyqtSignal(str, int)
    warmupStage  = QtCore.pyqtSignal(int, int, int)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("CrossMailer Control Panel")
        self.resize(1200, 800)
        
        try:
            self._apply_style()
            print("[DEBUG] Style applied.")
        except Exception as e:
            print(f"[ERROR] Error applying style: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

        try:
            self._setup_helpers()
            print("[DEBUG] Helpers setup completed.")
        except Exception as e:
            print(f"[ERROR] Error during helper setup: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

        try:
            self._build_ui()
            print("[DEBUG] UI built.")
        except Exception as e:
            print(f"[ERROR] Error building UI: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

        try:
            self._connect_signals()
            print("[DEBUG] Signals connected.")
        except Exception as e:
            print(f"[ERROR] Error connecting signals: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        
        # Start background services
        print("[DEBUG] Starting background services...")
        try:
            self.tracker.start()
            self.monitor.start()
            self.sentinel.start()
            print("[DEBUG] Background services started.")
        except Exception as e:
            print(f"[ERROR] Error starting background services: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        
        self.worker = None # Reference to the background worker

        # Menu bar (import is accessible even if the user doesn't open the Recipients tab)
        try:
            self._init_menu()
        except Exception as e:
            print(f"[ERROR] Error building menu: {e}")

    # ------------------------------------------------------------------
    # Load stylesheet + tiny drop‑shadow (visual polish)
    # ------------------------------------------------------------------
    def _apply_style(self):
        base_dir   = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        style_path = os.path.join(base_dir, "resources", "style.qss")
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        else:
            print("⚠️ Style file not found – using default Qt look.")
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
        passphrase = os.environ.get("CROSSMAILER_PASS")
        if not passphrase:
            print("[DEBUG] Showing passphrase dialog...")
            passphrase, ok = QtWidgets.QInputDialog.getText(
                self,
                "Master Passphrase",
                "Enter the secret key:",
                QtWidgets.QLineEdit.Password,
            )
            if not ok:
                print("[DEBUG] Passphrase dialog cancelled. Exiting.")
                sys.exit(0)
        else:
            print("[DEBUG] Using passphrase from environment.")

        print("[DEBUG] Initializing CryptoHelper...")
        self.crypto   = CryptoHelper(passphrase)
        
        print("[DEBUG] Initializing SMTPManager...")
        self.smtp_mgr = SMTPManager(self.crypto)
        
        print("[DEBUG] Initializing RecipientManager...")
        self.recipient_mgr = RecipientManager()
        
        print("[DEBUG] Initializing SequenceManager...")
        self.seq_mgr = SequenceManager(self.recipient_mgr.DB_PATH)
        self.default_sequence_id = self.seq_mgr.get_or_create_sequence("Default")
        
        print("[DEBUG] Initializing WarmupScheduler...")
        self.warmup   = WarmupScheduler()
        
        print("[DEBUG] Initializing Mailer...")
        self.mailer   = Mailer(self.crypto, self.smtp_mgr, stats_callback=self)
        
        print("[DEBUG] Initializing TrackingServer...")
        self.tracker = TrackingServer(RecipientManager.DB_PATH)
        
        print("[DEBUG] Initializing InboxMonitor...")
        self.monitor = InboxMonitor(self.smtp_mgr, self.recipient_mgr)
        
        print("[DEBUG] Initializing ProxyHarvester...")
        self.proxy_harvester = ProxyHarvester()
        
        print("[DEBUG] Initializing LogSentinel...")
        self.sentinel = LogSentinel(self.recipient_mgr.DB_PATH, self.smtp_mgr)

        # Constructed lazily so we can use current AI tab configuration.
        self.ai_supervisor = None

        self.templates = []
        print("[DEBUG] Helpers setup complete.")

    # ------------------------------------------------------------------
    # Build the whole UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        
        # Main Horizontal Layout
        self.outer_layout = QtWidgets.QHBoxLayout(central)
        self.outer_layout.setContentsMargins(10, 10, 10, 10)
        self.outer_layout.setSpacing(15)

        # --- Sidebar (Left) ---
        self.sidebar = QtWidgets.QWidget()
        self.sidebar.setFixedWidth(300) # Fixed width for sidebar
        self.sidebar_layout = QtWidgets.QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(0, 0, 0, 0)

        # Controls Group
        self.ctrl_group = QtWidgets.QGroupBox("Campaign Controls")
        self.ctrl_layout = QtWidgets.QVBoxLayout(self.ctrl_group)
        
        self.start_btn = QtWidgets.QPushButton("▶ Start Campaign")
        self.start_btn.setMinimumHeight(40)
        self.stop_btn  = QtWidgets.QPushButton("⏹ Stop Campaign")
        self.stop_btn.setMinimumHeight(40)
        
        self.rate_spin = QtWidgets.QSpinBox()
        self.rate_spin.setRange(10, 10000)
        self.rate_spin.setSuffix(" emails / hr")
        self.rate_spin.setMinimumHeight(30)

        self.ctrl_layout.addWidget(self.start_btn)
        self.ctrl_layout.addWidget(self.stop_btn)
        self.ctrl_layout.addWidget(QtWidgets.QLabel("Target Rate:"))
        self.ctrl_layout.addWidget(self.rate_spin)

        self.ai_autopilot = QtWidgets.QCheckBox("AI Autopilot (LLM)")
        self.ctrl_layout.addWidget(self.ai_autopilot)
        
        self.sidebar_layout.addWidget(self.ctrl_group)

        # Status Panel in Sidebar
        self.status_panel = StatusPanel()
        self.status_panel.setGraphicsEffect(self._status_shadow)
        self.sidebar_layout.addWidget(self.status_panel)
        self.sidebar_layout.addStretch() # Push everything up

        # --- Main Area (Right) ---
        self.main_area = QtWidgets.QWidget()
        self.main_layout = QtWidgets.QVBoxLayout(self.main_area)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        
        self.ai_tab = AITab()
        self.tabs.addTab(self.ai_tab, "AI Lab")
        
        self.recipient_tab = RecipientTab()
        self.recipient_tab.mgr = self.recipient_mgr
        self.recipient_tab.default_sequence_id = self.default_sequence_id
        self.tabs.addTab(self.recipient_tab, "Recipients")
        
        self._init_smtp_tab()
        self._init_template_tab()
        self._init_message_settings_tab()
        self._init_proxy_tab()

        self.main_layout.addWidget(self.tabs)

        # Add Sidebar and Main Area to Outer Layout
        self.outer_layout.addWidget(self.sidebar)
        self.outer_layout.addWidget(self.main_area)

    def _init_menu(self):
        menu = self.menuBar()

        file_menu = menu.addMenu("&File")

        act_import_recip = QtWidgets.QAction("Import Recipients...", self)
        act_import_recip.setShortcut("Ctrl+I")
        act_import_recip.triggered.connect(lambda: self.recipient_tab._import_file())

        act_import_tpl = QtWidgets.QAction("Import Templates...", self)
        act_import_tpl.setShortcut("Ctrl+T")
        act_import_tpl.triggered.connect(self._add_template)

        act_quit = QtWidgets.QAction("Quit", self)
        act_quit.setShortcut("Ctrl+Q")
        act_quit.triggered.connect(self.close)

        file_menu.addAction(act_import_recip)
        file_menu.addAction(act_import_tpl)
        file_menu.addSeparator()
        file_menu.addAction(act_quit)

    def _init_smtp_tab(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        form = QtWidgets.QFormLayout()
        self._smtp_host = QtWidgets.QLineEdit()
        self._smtp_port = QtWidgets.QSpinBox()
        self._smtp_port.setRange(1, 65535)
        self._smtp_port.setValue(587)
        self._smtp_user = QtWidgets.QLineEdit()
        self._smtp_pass = QtWidgets.QLineEdit()
        self._smtp_pass.setEchoMode(QtWidgets.QLineEdit.Password)
        self._smtp_warmup = QtWidgets.QCheckBox("Enable Warm-up Mode")
        self._imap_host = QtWidgets.QLineEdit()
        self._imap_port = QtWidgets.QSpinBox()
        self._imap_port.setRange(1, 65535)
        self._imap_port.setValue(993)

        form.addRow("SMTP Host:", self._smtp_host)
        form.addRow("SMTP Port:", self._smtp_port)
        form.addRow("SMTP User:", self._smtp_user)
        form.addRow("SMTP Pass:", self._smtp_pass)
        form.addRow("IMAP Host:", self._imap_host)
        form.addRow("IMAP Port:", self._imap_port)
        form.addRow("", self._smtp_warmup)

        self._add_smtp_btn = QtWidgets.QPushButton("Add SMTP Server")
        self._add_smtp_btn.clicked.connect(self._add_smtp_server)

        self._smtp_table = QtWidgets.QTableWidget(0, 7)
        self._smtp_table.setHorizontalHeaderLabels(["Host", "Port", "User", "Health %", "Stage", "Sent", "Limit"])
        self._smtp_table.horizontalHeader().setStretchLastSection(True)
        self._refresh_smtp_btn = QtWidgets.QPushButton("Refresh List")
        self._refresh_smtp_btn.clicked.connect(self._refresh_smtp_table)

        layout.addLayout(form)
        layout.addWidget(self._add_smtp_btn)
        layout.addWidget(self._refresh_smtp_btn)
        layout.addWidget(self._smtp_table)
        self._refresh_smtp_table()
        self.tabs.addTab(tab, "SMTP Pool")

    def _init_template_tab(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        self._template_list = QtWidgets.QListWidget()
        layout.addWidget(self._template_list)
        btn_layout = QtWidgets.QHBoxLayout()
        self._add_template_btn = QtWidgets.QPushButton("Add Template")
        self._remove_template_btn = QtWidgets.QPushButton("Remove Selected")
        btn_layout.addWidget(self._add_template_btn)
        btn_layout.addWidget(self._remove_template_btn)
        layout.addLayout(btn_layout)
        self._add_template_btn.clicked.connect(self._add_template)
        self._remove_template_btn.clicked.connect(self._remove_selected_template)
        self.tabs.addTab(tab, "Template Library")

    def _init_message_settings_tab(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(tab)
        self._msg_to = QtWidgets.QLineEdit()
        self._msg_from = QtWidgets.QLineEdit()
        self._msg_subject = QtWidgets.QLineEdit()
        self._msg_domain = QtWidgets.QLineEdit()
        self._tracking_base = QtWidgets.QLineEdit()
        self._tracking_base.setPlaceholderText("http://127.0.0.1:5000")
        self._placeholder_first = QtWidgets.QLineEdit()
        self._placeholder_last = QtWidgets.QLineEdit()
        layout.addRow("To (Test Single):", self._msg_to)
        layout.addRow("From address:", self._msg_from)
        layout.addRow("Default subject:", self._msg_subject)
        layout.addRow("Domain:", self._msg_domain)
        layout.addRow("Tracking Base URL:", self._tracking_base)
        layout.addRow("First Name:", self._placeholder_first)
        layout.addRow("Last Name:", self._placeholder_last)
        self.tabs.addTab(tab, "Message Settings")

    def _init_proxy_tab(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        self._proxy_table = QtWidgets.QTableWidget(0, 3)
        self._proxy_table.setHorizontalHeaderLabels(["Address", "Latency (ms)", "Status"])
        layout.addWidget(self._proxy_table)
        btn_layout = QtWidgets.QHBoxLayout()
        btn_refresh = QtWidgets.QPushButton("Refresh Proxy List")
        btn_refresh.clicked.connect(self._refresh_proxy_table)
        btn_harvest = QtWidgets.QPushButton("Run Harvester Now")
        btn_harvest.clicked.connect(lambda: self.proxy_harvester.start_harvesting())
        btn_layout.addWidget(btn_refresh)
        btn_layout.addWidget(btn_harvest)
        layout.addLayout(btn_layout)
        self.tabs.addTab(tab, "Proxies")

    # ------------------------------------------------------------------
    # Actions & Slots
    # ------------------------------------------------------------------
    def _connect_signals(self):
        self.start_btn.clicked.connect(self.start_campaign)
        self.stop_btn.clicked.connect(self.stop_campaign)
        self.emailSent.connect(self._handle_email_result)
        self.rateUpdated.connect(self.status_panel.set_rate)
        self.serverChanged.connect(self.status_panel.set_server)
        self.warmupStage.connect(self.status_panel.set_warmup)
        self.sentinel.strategy_update.connect(self._handle_strategy_update)
        self.ai_autopilot.toggled.connect(self._toggle_ai_autopilot)
        # ai_supervisor signals are connected when enabled.

    def _add_smtp_server(self):
        host = self._smtp_host.text().strip()
        port = self._smtp_port.value()
        user = self._smtp_user.text().strip()
        pwd  = self._smtp_pass.text()
        warmup = self._smtp_warmup.isChecked()
        imap_h = self._imap_host.text().strip()
        imap_p = self._imap_port.value()
        if not host or not user or not pwd: return
        try:
            self.smtp_mgr.add_server(host, port, user, pwd, warmup_enabled=warmup, imap_host=imap_h, imap_port=imap_p)
            self._refresh_smtp_table()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", str(e))

    def _refresh_smtp_table(self):
        rows = self.smtp_mgr.get_all_servers()
        self._smtp_table.setRowCount(0)
        for row in rows:
            r = self._smtp_table.rowCount()
            self._smtp_table.insertRow(r)
            vals = [row['host'], row['port'], row['username'], f"{row['health_score']}%", row['warmup_stage'] if row['warmup_enabled'] else "-", row['daily_sent'], row['daily_limit']]
            for c, v in enumerate(vals): self._smtp_table.setItem(r, c, QtWidgets.QTableWidgetItem(str(v)))

    def _refresh_proxy_table(self):
        conn = connect(self.proxy_harvester.DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT address, latency, status FROM proxies ORDER BY latency ASC")
        rows = cur.fetchall()
        conn.close()
        self._proxy_table.setRowCount(0)
        for row in rows:
            r = self._proxy_table.rowCount()
            self._proxy_table.insertRow(r)
            for c, v in enumerate(row): self._proxy_table.setItem(r, c, QtWidgets.QTableWidgetItem(str(v)))

    def _add_template(self):
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Select Templates", "", "Text Files (*.txt *.html)")
        for f in files:
            if f not in self.templates:
                self.templates.append(f)
                self._template_list.addItem(f)

    def _remove_selected_template(self):
        for item in self._template_list.selectedItems():
            idx = self._template_list.row(item)
            self._template_list.takeItem(idx)
            del self.templates[idx]

    def start_campaign(self):
        if not self.templates:
            QtWidgets.QMessageBox.warning(self, "Missing Template", "Please add at least one template.")
            return
        if not self._msg_from.text().strip() or not self._msg_domain.text().strip():
            QtWidgets.QMessageBox.warning(self, "Missing Info", "From address and Domain are required.")
            return

        target_rate = self.rate_spin.value()
        placeholders = {
            "to": self._msg_to.text(),
            "from": self._msg_from.text(),
            "subject": self._msg_subject.text(),
            "domain": self._msg_domain.text(),
            "first_name": self._placeholder_first.text(),
            "last_name": self._placeholder_last.text(),
            "tracking_base_url": self._tracking_base.text().strip() or "http://127.0.0.1:5000"
        }

        tmpl = self.templates[0]
        if self.seq_mgr.get_sequence_steps_count(self.default_sequence_id) == 0:
            self.seq_mgr.add_step(self.default_sequence_id, 1, tmpl, delay_hours=0, subject=self._msg_subject.text())

        self.warmup.configure(target_rate)
        self.warmup.stage_changed.connect(self.warmupStage.emit)
        self.worker = CampaignWorker(self.mailer, self.recipient_tab.mgr, self.seq_mgr, tmpl, placeholders)
        self.warmup.stage_changed.connect(lambda s, t, r: self.worker.set_rate(r))
        self.warmup.start()
        self.worker.start()
        self.status_panel.set_running(True)

    def stop_campaign(self):
        if self.worker: self.worker.stop()
        self.warmup.stop()
        self.status_panel.set_running(False)

    @QtCore.pyqtSlot(str, dict)
    def _handle_strategy_update(self, action, params):
        if action == "emergency_stop":
            self.stop_campaign()
            self.status_panel.log(f"⚠️ SENTINEL: STOP - {params.get('reason')}")
        elif action == "disable_server":
            host = params.get("host")
            if host:
                self.smtp_mgr.disable_server_by_host(host)
            self.status_panel.log(f"⚠️ SENTINEL: Disabled server {host}")
            self._refresh_smtp_table()
        elif action == "set_rate":
            # AI wants direct rate control; stop warmup to avoid fighting signals.
            rate = params.get("emails_per_hr")
            try:
                rate = int(rate)
            except Exception:
                return
            rate = max(10, min(10000, rate))
            self.rate_spin.setValue(rate)
            try:
                self.warmup.stop()
            except Exception:
                pass
            if self.worker:
                self.worker.set_rate(rate)
            self.status_panel.set_rate(rate)

    @QtCore.pyqtSlot(bool, str)
    def _handle_email_result(self, success: bool, error: str = ""):
        if success: self.status_panel.log("✅ Email sent")
        else: self.status_panel.log(f"❌ Failed - {error}")
        self.recipient_tab._refresh_table()

    def email_sent(self, success: bool, error: str = ""): self.emailSent.emit(success, error)
    def update_rate(self, r): self.rateUpdated.emit(r)
    def server_updated(self, h, hl): self.serverChanged.emit(h, hl)

    def _toggle_ai_autopilot(self, enabled: bool):
        if enabled:
            self.status_panel.log("[AI] Autopilot enabled.")
            try:
                model_config = self.ai_tab._get_current_model_config()
            except Exception:
                model_config = None

            # Recreate to ensure it uses the current model config.
            try:
                if self.ai_supervisor:
                    self.ai_supervisor.stop()
            except Exception:
                pass

            self.ai_supervisor = AISupervisor(self.recipient_mgr.DB_PATH, self.smtp_mgr, model_config=model_config)
            self.ai_supervisor.action_emitted.connect(self._handle_strategy_update)
            self.ai_supervisor.note_emitted.connect(self.status_panel.log)
            self.ai_supervisor.start()
        else:
            self.status_panel.log("[AI] Autopilot disabled.")
            if self.ai_supervisor:
                self.ai_supervisor.stop()

    def closeEvent(self, event):
        # Best-effort shutdown to avoid leaving threads running after the window closes.
        try:
            self.stop_campaign()
            if self.worker:
                self.worker.wait(2000)
        except Exception:
            pass

        for svc in ("monitor", "sentinel", "proxy_harvester", "ai_supervisor"):
            try:
                inst = getattr(self, svc, None)
                if inst:
                    inst.stop()
            except Exception:
                pass

        try:
            if getattr(self, "tracker", None):
                self.tracker.stop()
        except Exception:
            pass

        event.accept()
