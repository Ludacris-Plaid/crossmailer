import sqlite3
import os
import re
import csv
import dns.resolver

from dbutil import connect

class RecipientManager:
    DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "recipients.db")

    def __init__(self):
        self._init_db()

    def _init_db(self):
        """Initialize the recipients database."""
        os.makedirs(os.path.dirname(self.DB_PATH), exist_ok=True)
        conn = connect(self.DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS recipients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE,
                provider TEXT,
                status TEXT DEFAULT 'Pending', -- Pending, Valid, Invalid, Sent, Failed, Replied, Bounced
                open_count INTEGER DEFAULT 0,
                click_count INTEGER DEFAULT 0,
                last_open TEXT,
                last_click TEXT,
                current_step INTEGER DEFAULT 0,
                next_send_time INTEGER DEFAULT 0,
                sequence_id INTEGER DEFAULT 0
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sequences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sequence_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sequence_id INTEGER,
                step_number INTEGER,
                template_path TEXT,
                delay_hours INTEGER,
                subject TEXT,
                FOREIGN KEY(sequence_id) REFERENCES sequences(id)
            )
        """)
        
        conn.commit()
        conn.close()
        self._migrate_schema()

    def _migrate_schema(self):
        """Ensure all columns exist."""
        conn = connect(self.DB_PATH)
        cur = conn.cursor()
        cols = [
            ("open_count", "INTEGER DEFAULT 0"),
            ("click_count", "INTEGER DEFAULT 0"),
            ("last_open", "TEXT"),
            ("last_click", "TEXT"),
            ("current_step", "INTEGER DEFAULT 0"),
            ("next_send_time", "INTEGER DEFAULT 0"),
            ("sequence_id", "INTEGER DEFAULT 0")
        ]
        
        for col, dtype in cols:
            try:
                cur.execute(f"ALTER TABLE recipients ADD COLUMN {col} {dtype}")
            except sqlite3.OperationalError:
                pass
        
        conn.commit()
        conn.close()

    def _extract_provider(self, email):
        """Extracts 'gmail', 'outlook', etc. from email."""
        try:
            domain = email.split('@')[1]
            # Simple heuristic: 'gmail.com' -> 'Gmail', 'yahoo.co.uk' -> 'Yahoo'
            provider = domain.split('.')[0].capitalize()
            return provider
        except IndexError:
            return "Unknown"

    def import_txt(self, file_path, default_sequence_id=None):
        """Bulk import emails from a txt file (one per line)."""
        count = 0
        conn = connect(self.DB_PATH)
        cur = conn.cursor()
        
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                email = line.strip()
                if not email:
                    continue
                
                # Basic cleanup
                provider = self._extract_provider(email)
                
                try:
                    if default_sequence_id:
                        cur.execute(
                            "INSERT OR IGNORE INTO recipients (email, provider, sequence_id, next_send_time) VALUES (?, ?, ?, 0)",
                            (email, provider, default_sequence_id)
                        )
                    else:
                        cur.execute(
                            "INSERT OR IGNORE INTO recipients (email, provider) VALUES (?, ?)",
                            (email, provider)
                        )
                    if cur.rowcount > 0:
                        count += 1
                except sqlite3.Error:
                    pass

        conn.commit()
        conn.close()
        return count

    def import_csv(self, file_path, default_sequence_id=None, email_column="email"):
        """
        Bulk import from CSV.
        - If a header exists and contains `email_column`, use it.
        - Otherwise, use the first column.
        """
        count = 0
        conn = connect(self.DB_PATH)
        cur = conn.cursor()

        with open(file_path, "r", encoding="utf-8", errors="ignore", newline="") as f:
            # Try DictReader first (headered CSV).
            peek = f.read(4096)
            f.seek(0)
            has_header = csv.Sniffer().has_header(peek) if peek else False

            if has_header:
                reader = csv.DictReader(f)
                for row in reader:
                    email = (row.get(email_column) or "").strip()
                    if not email:
                        continue
                    provider = self._extract_provider(email)
                    try:
                        if default_sequence_id:
                            cur.execute(
                                "INSERT OR IGNORE INTO recipients (email, provider, sequence_id, next_send_time) VALUES (?, ?, ?, 0)",
                                (email, provider, default_sequence_id),
                            )
                        else:
                            cur.execute(
                                "INSERT OR IGNORE INTO recipients (email, provider) VALUES (?, ?)",
                                (email, provider),
                            )
                        if cur.rowcount > 0:
                            count += 1
                    except sqlite3.Error:
                        pass
            else:
                reader = csv.reader(f)
                for row in reader:
                    if not row:
                        continue
                    email = (row[0] or "").strip()
                    if not email:
                        continue
                    provider = self._extract_provider(email)
                    try:
                        if default_sequence_id:
                            cur.execute(
                                "INSERT OR IGNORE INTO recipients (email, provider, sequence_id, next_send_time) VALUES (?, ?, ?, 0)",
                                (email, provider, default_sequence_id),
                            )
                        else:
                            cur.execute(
                                "INSERT OR IGNORE INTO recipients (email, provider) VALUES (?, ?)",
                                (email, provider),
                            )
                        if cur.rowcount > 0:
                            count += 1
                    except sqlite3.Error:
                        pass

        conn.commit()
        conn.close()
        return count

    def import_any(self, file_path, default_sequence_id=None):
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".csv":
            return self.import_csv(file_path, default_sequence_id=default_sequence_id)
        return self.import_txt(file_path, default_sequence_id=default_sequence_id)

    def get_recipients(self, provider_filter=None):
        """Fetch recipients, optionally filtered by provider."""
        conn = connect(self.DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        if provider_filter and provider_filter != "All":
            cur.execute("SELECT * FROM recipients WHERE provider = ?", (provider_filter,))
        else:
            cur.execute("SELECT * FROM recipients")
            
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    def get_providers(self):
        """Get list of unique providers for the dropdown."""
        conn = connect(self.DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT provider FROM recipients ORDER BY provider")
        providers = [row[0] for row in cur.fetchall()]
        conn.close()
        return providers

    def clear_all(self):
        """Delete all recipients."""
        conn = connect(self.DB_PATH)
        conn.execute("DELETE FROM recipients")
        conn.commit()
        conn.close()

    def validate_syntax(self, email):
        """Regex validation."""
        pattern = r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"
        return re.match(pattern, email) is not None

    def validate_mx(self, email):
        """Check if domain has MX records."""
        try:
            domain = email.split('@')[1]
            dns.resolver.resolve(domain, 'MX')
            return True
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers, IndexError):
            return False
        except Exception:
            return False

    def update_status(self, email, status):
        """Update status for a specific email."""
        conn = connect(self.DB_PATH)
        conn.execute("UPDATE recipients SET status = ? WHERE email = ?", (status, email))
        conn.commit()
        conn.close()

    def get_stats(self):
        """Return counts by status."""
        conn = connect(self.DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT status, COUNT(*) FROM recipients GROUP BY status")
        stats = dict(cur.fetchall())
        conn.close()
        return stats

    def get_ready_recipients(self, now_ts):
        """Fetch recipients ready for the next step based on scheduled time."""
        conn = connect(self.DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        # Status must be Valid, Pending, or Sent (for followups)
        # Exclude Replied, Bounced, Invalid
        cur.execute("""
            SELECT * FROM recipients 
            WHERE status IN ('Pending', 'Valid', 'Sent') 
            AND next_send_time <= ?
            AND sequence_id > 0
        """, (now_ts,))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    def get_blast_recipients(self, limit=500):
        """
        Recipients for a simple one-off blast (no sequence).
        This is mainly for backwards-compat behavior and tests.
        """
        conn = connect(self.DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """
            SELECT * FROM recipients
            WHERE status IN ('Pending', 'Valid')
              AND (sequence_id IS NULL OR sequence_id = 0)
            LIMIT ?
            """,
            (int(limit),),
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    def promote_recipient(self, email, next_step, delay_hours, status="Sent"):
        """Advance recipient to next step and schedule it."""
        import time
        next_ts = int(time.time()) + (delay_hours * 3600)
        conn = connect(self.DB_PATH)
        conn.execute("""
            UPDATE recipients 
            SET current_step = ?, next_send_time = ?, status = ?
            WHERE email = ?
        """, (next_step, next_ts, status, email))
        conn.commit()
        conn.close()
