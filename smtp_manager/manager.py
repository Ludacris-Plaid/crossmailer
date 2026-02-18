# -*- coding: utf-8 -*-
"""
SMTP Manager – stores encrypted credentials and selects the best server
based on a simple health‑score heuristic and warm-up schedules.
"""

import os
import sqlite3
import datetime
import time
from security.crypto import encrypt, decrypt

from dbutil import connect

WARMUP_SCHEDULE = {
    1: 20,
    2: 50,
    3: 100,
    4: 200,
    5: 500
}
DEFAULT_LIMIT = 1000  # For servers past stage 5 or warm-up disabled

class SMTPManager:
    """Handles encrypted SMTP credentials and server rotation with warm-up logic."""
    DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "smtp_credentials.db")

    def __init__(self, crypto):
        self.crypto = crypto
        os.makedirs(os.path.dirname(self.DB_PATH), exist_ok=True)
        self._init_db()
        self._migrate_db()

    def _init_db(self):
        """Create the credentials table if it does not exist."""
        conn = connect(self.DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS smtp_credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                host TEXT,
                port INTEGER,
                username TEXT,
                password_encrypted TEXT,
                health_score INTEGER DEFAULT 100,
                last_success INTEGER DEFAULT 0,
                warmup_enabled INTEGER DEFAULT 0,
                warmup_stage INTEGER DEFAULT 1,
                daily_sent INTEGER DEFAULT 0,
                last_usage_date TEXT,
                consecutive_errors INTEGER DEFAULT 0,
                imap_host TEXT,
                imap_port INTEGER,
                imap_use_ssl INTEGER DEFAULT 1
            )
            """
        )
        conn.commit()
        conn.close()

    def _migrate_db(self):
        """Ensure new columns exist for existing databases."""
        conn = connect(self.DB_PATH)
        cur = conn.cursor()
        
        # Define all columns that should exist
        columns = [
            ("warmup_enabled", "INTEGER DEFAULT 0"),
            ("warmup_stage", "INTEGER DEFAULT 1"),
            ("daily_sent", "INTEGER DEFAULT 0"),
            ("last_usage_date", "TEXT"),
            ("consecutive_errors", "INTEGER DEFAULT 0"),
            ("imap_host", "TEXT"),
            ("imap_port", "INTEGER"),
            ("imap_use_ssl", "INTEGER DEFAULT 1")
        ]
        
        for col_name, col_type in columns:
            try:
                cur.execute(f"ALTER TABLE smtp_credentials ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                pass # Column might already exist
        
        conn.commit()
        conn.close()

    def add_server(self, host: str, port: int, username: str, password: str, 
                   warmup_enabled: bool = False, 
                   imap_host: str = None, imap_port: int = None, imap_use_ssl: bool = True) -> None:
        """Add a new SMTP server - password is stored encrypted."""
        enc_pwd = encrypt(password.encode(), self.crypto.key).decode()
        conn = connect(self.DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO smtp_credentials (host, port, username, password_encrypted, warmup_enabled, last_usage_date, imap_host, imap_port, imap_use_ssl)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (host, port, username, enc_pwd, 1 if warmup_enabled else 0, datetime.date.today().isoformat(), imap_host, imap_port, 1 if imap_use_ssl else 0),
        )
        conn.commit()
        conn.close()

    def _get_daily_limit(self, stage: int) -> int:
        return WARMUP_SCHEDULE.get(stage, DEFAULT_LIMIT)

    def _maybe_promote_stage(self, row):
        """Promote warm-up stage if previous day met target."""
        if not row.get('warmup_enabled'):
            return
        if not row.get('last_usage_date'):
            return
        limit = self._get_daily_limit(row['warmup_stage'])
        if row.get('daily_sent', 0) >= limit and row['warmup_stage'] < max(WARMUP_SCHEDULE.keys()):
            conn = connect(self.DB_PATH)
            cur = conn.cursor()
            cur.execute(
                "UPDATE smtp_credentials SET warmup_stage = warmup_stage + 1 WHERE id = ?",
                (row['id'],)
            )
            conn.commit()
            conn.close()

    def get_active_server(self) -> dict:
        """
        Return the healthiest available server.
        Handles daily resets and limit checks.
        """
        conn = connect(self.DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # 1. Reset daily counts if date changed
        today = datetime.date.today().isoformat()
        cur.execute("SELECT * FROM smtp_credentials")
        existing_rows = [dict(r) for r in cur.fetchall()]
        for row in existing_rows:
            if row.get('last_usage_date') and row['last_usage_date'] != today:
                self._maybe_promote_stage(row)
        cur.execute(
            """
            UPDATE smtp_credentials
            SET daily_sent = 0, last_usage_date = ?
            WHERE last_usage_date != ? OR last_usage_date IS NULL
            """,
            (today, today)
        )
        conn.commit()

        # 2. Select candidates
        # Criteria:
        # - Not in cooldown (consecutive_errors < 3) - simplistic logic, or we can check timestamps
        # - Has not exceeded daily limit
        
        cur.execute("SELECT * FROM smtp_credentials WHERE consecutive_errors < 3")
        rows = cur.fetchall()
        
        candidates = []
        for row in rows:
            rec = dict(row)
            limit = self._get_daily_limit(rec['warmup_stage']) if rec['warmup_enabled'] else DEFAULT_LIMIT
            
            if rec['daily_sent'] < limit:
                candidates.append(rec)
        
        conn.close()

        if not candidates:
            # Check if we have servers but they are all capped
            return None 

        # Sort by health_score DESC, then last_success ASC (rotation)
        # We want to use the one waiting the longest
        candidates.sort(key=lambda x: (-x['health_score'], x['last_success']))

        return candidates[0]

    def update_server_status(self, server_id: int, success: bool, error_msg: str = ""):
        """Update server stats after a send attempt."""
        conn = connect(self.DB_PATH)
        cur = conn.cursor()
        
        if success:
            # Logic:
            # - Increment daily_sent
            # - Reset consecutive_errors
            # - Update last_success
            # - Maybe promote stage if end of day? (Promotion usually happens on reset, but we can do it here if we want strictly daily steps)
            # For simplicity: We promote ONLY when resetting daily counts if previous day met target?
            # Actually, easiest is: If daily_sent reaches limit, we are done for today. 
            # Promotion logic: If we hit the limit today, and health is good, tomorrow we promote.
            # We'll implement a simple check: If we just hit the limit, set a flag?
            # Let's stick to: Promotion happens on NEXT day's first access if criteria met.
            # But wait, 'get_active_server' resets counts. It doesn't know if yesterday we finished well.
            # Improved Logic: We won't implement auto-promotion in this step to keep it safe. 
            # Or simpler: If success, increment daily_sent.
            
            cur.execute(
                """
                UPDATE smtp_credentials
                SET daily_sent = daily_sent + 1,
                    last_success = ?,
                    consecutive_errors = 0,
                    health_score = MIN(100, health_score + 1)
                WHERE id = ?
                """,
                (int(time.time()), server_id)
            )
            
            # Check for stage promotion eligibility (simple version: if we hit limit, auto-promote for next time? No, that skips days)
            # We will implement logic in 'get_active_server' or a separate maintenance task for promotion.
            # For this iteration, manual promotion or separate logic is safer. 
            # We will just increment stage if we hit the limit? No, that's too fast.
            # Let's leave stage promotion for a dedicated 'end of day' check or manual.
            
        else:
            # Logic:
            # - Increment consecutive_errors
            # - Decrease health_score
            penalty = 5 if "timeout" in error_msg.lower() else 20
            cur.execute(
                """
                UPDATE smtp_credentials
                SET consecutive_errors = consecutive_errors + 1,
                    health_score = MAX(0, health_score - ?)
                WHERE id = ?
                """,
                (penalty, server_id)
            )

        conn.commit()
        conn.close()

    def disable_server_by_host(self, host: str) -> None:
        """
        Mark a server as disabled so it won't be selected by get_active_server().
        This is used by Sentinel strategy updates.
        """
        conn = connect(self.DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE smtp_credentials
            SET consecutive_errors = 999,
                health_score = 0
            WHERE host = ?
            """,
            (host,),
        )
        conn.commit()
        conn.close()

    def get_all_servers(self):
        """Fetch all servers for the UI."""
        conn = connect(self.DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM smtp_credentials")
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        # Add derived fields for UI
        for r in rows:
            r['daily_limit'] = self._get_daily_limit(r['warmup_stage']) if r['warmup_enabled'] else DEFAULT_LIMIT
        return rows
