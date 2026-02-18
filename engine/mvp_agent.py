import time
import sqlite3
from PyQt5 import QtCore

from dbutil import connect

class MVPAuditAgent(QtCore.QObject):
    """Background agent that checks MVP readiness and emits status updates."""
    status_updated = QtCore.pyqtSignal(list)

    def __init__(self, recipient_db_path, smtp_mgr, seq_mgr, ai_brain, interval=30):
        super().__init__()
        self.rec_db = recipient_db_path
        self.smtp_mgr = smtp_mgr
        self.seq_mgr = seq_mgr
        self.ai_brain = ai_brain
        self.interval = interval
        self.running = False
        self.thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = QtCore.QThread()
        self.moveToThread(self.thread)
        self.thread.started.connect(self._run)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.quit()
            self.thread.wait()

    def _run(self):
        while self.running:
            try:
                issues = self._collect_issues()
                self.status_updated.emit(issues)
            except Exception as exc:
                self.status_updated.emit([f"MVP agent error: {exc}"])
            for _ in range(self.interval):
                if not self.running:
                    break
                time.sleep(1)

    def _collect_issues(self):
        issues = []
        # SMTP readiness
        servers = self.smtp_mgr.get_all_servers()
        if not servers:
            issues.append("No SMTP servers configured.")
        else:
            unhealthy = [s for s in servers if s['health_score'] <= 0]
            if unhealthy:
                issues.append(f"{len(unhealthy)} SMTP servers unhealthy.")

        # Recipients
        conn = connect(self.rec_db)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM recipients")
        total_recipients = cur.fetchone()[0]
        conn.close()
        if total_recipients == 0:
            issues.append("No recipients imported.")

        # Sequences
        if self.seq_mgr.get_sequence_steps_count(self.seq_mgr.get_or_create_sequence("Default")) == 0:
            issues.append("Default sequence has no steps.")

        # AI availability
        if not self.ai_brain.HAS_LLAMA and not self.ai_brain.model_config.get('ollama_model'):
            issues.append("AI model not configured (Ollama model name missing).")

        return issues
