import threading
import time
import sqlite3
from PyQt5 import QtCore

from dbutil import connect

class LogSentinel(QtCore.QObject):
    """
    Autonomous monitoring agent that reads logs/DB and signals strategy adjustments.
    """
    strategy_update = QtCore.pyqtSignal(str, dict) # action_type, params
    
    def __init__(self, recipient_db_path, smtp_mgr):
        super().__init__()
        self.rec_db = recipient_db_path
        self.smtp_mgr = smtp_mgr
        self.running = False
        self.thread = None

    def start(self, interval=60):
        if self.running: return
        self.running = True
        self.thread = threading.Thread(target=self._run, args=(interval,), daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False

    def _run(self, interval):
        while self.running:
            try:
                self._analyze_health()
            except Exception as e:
                print(f"[Sentinel] Error: {e}")
            
            for _ in range(interval):
                if not self.running: break
                time.sleep(1)

    def _analyze_health(self):
        # 1. Check Global Bounce Rate (Last 1 hour)
        # We need to query recipients updated in last hour? 
        # For simplicity, we check total status ratio for now.
        conn = connect(self.rec_db)
        cur = conn.cursor()
        
        cur.execute("SELECT status, COUNT(*) FROM recipients GROUP BY status")
        counts = dict(cur.fetchall())
        conn.close()
        
        total_sent = counts.get('Sent', 0) + counts.get('Bounced', 0) + counts.get('Replied', 0)
        bounced = counts.get('Bounced', 0)
        
        if total_sent > 50:
            bounce_rate = (bounced / total_sent) * 100
            if bounce_rate > 5:
                print(f"[Sentinel] HIGH BOUNCE RATE: {bounce_rate:.2f}%. Signaling emergency brake.")
                self.strategy_update.emit("emergency_stop", {"reason": "High Bounce Rate"})
                return

        # 2. Check SMTP Health
        servers = self.smtp_mgr.get_all_servers()
        for s in servers:
            if s['consecutive_errors'] >= 3 and s['health_score'] > 0:
                print(f"[Sentinel] Server {s['host']} is failing consistently. Disabling.")
                # We can't disable directly via manager easily without a specific method, 
                # but we can update DB manually or add a method to manager.
                # Ideally, emit a signal for the main thread to handle.
                self.strategy_update.emit("disable_server", {"host": s['host']})

        # 3. Check for Good Performance (Open Rate)
        # If open rate > 30%, maybe increase speed?
        # NOTE: engagement is tracked via open_count/click_count, not status strings.
        # If you want real open rate, query SUM(open_count>0)/sent, etc.
        opens = counts.get('Opened', 0)
        # Simpler check:
        # self.strategy_update.emit("boost_rate", {})
