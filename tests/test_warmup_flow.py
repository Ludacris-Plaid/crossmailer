import unittest
import os
import sqlite3
import shutil
import asyncio
from unittest.mock import MagicMock, AsyncMock
import time

# Add project root to path
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from smtp_manager.manager import SMTPManager, WARMUP_SCHEDULE
from engine.worker import CampaignWorker
from security.crypto import CryptoHelper
from engine.recipient_manager import RecipientManager

class TestWarmupFlow(unittest.TestCase):
    def setUp(self):
        # Use a fresh temp DB for each test
        self.test_db_path = "tests/test_smtp.db"
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)
            
        # Patch SMTPManager DB_PATH
        self.original_db_path = SMTPManager.DB_PATH
        SMTPManager.DB_PATH = self.test_db_path
        
        self.crypto = CryptoHelper("secret")
        self.mgr = SMTPManager(self.crypto)

    def tearDown(self):
        SMTPManager.DB_PATH = self.original_db_path
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)

    def test_schema_migration(self):
        """Verify new columns exist."""
        conn = sqlite3.connect(self.test_db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(smtp_credentials)")
        columns = [row[1] for row in cur.fetchall()]
        self.assertIn("warmup_enabled", columns)
        self.assertIn("daily_sent", columns)
        conn.close()

    def test_add_server_warmup(self):
        """Verify warm-up flag storage."""
        self.mgr.add_server("host", 25, "user", "pass", warmup_enabled=True)
        row = self.mgr.get_active_server()
        self.assertEqual(row['warmup_enabled'], 1)
        self.assertEqual(row['warmup_stage'], 1)

    def test_daily_limit_enforcement(self):
        """Test that server is skipped if limit reached."""
        self.mgr.add_server("host1", 25, "user1", "pass", warmup_enabled=True)
        
        # Manually max out the server
        conn = sqlite3.connect(self.test_db_path)
        limit = WARMUP_SCHEDULE[1]
        conn.execute("UPDATE smtp_credentials SET daily_sent = ?", (limit,))
        conn.commit()
        conn.close()
        
        server = self.mgr.get_active_server()
        self.assertIsNone(server, "Should return None if all servers capped")

    def test_rotation_logic(self):
        """Test simple rotation between 2 available servers."""
        self.mgr.add_server("s1", 25, "u1", "p", warmup_enabled=False)
        self.mgr.add_server("s2", 25, "u2", "p", warmup_enabled=False)
        
        s1 = self.mgr.get_active_server()
        self.mgr.update_server_status(s1['id'], True) # s1 used recently
        time.sleep(0.01) # Ensure timestamp diff
        
        s2 = self.mgr.get_active_server()
        self.assertNotEqual(s1['id'], s2['id'], "Should rotate to s2")

    def test_worker_loop(self):
        """Test worker sends at least one message in blast mode."""
        mailer = MagicMock()
        mailer.send_one = AsyncMock(return_value=True)

        rec_db = "tests/test_recipients_worker.db"
        if os.path.exists(rec_db):
            os.remove(rec_db)
        original_rec_db = RecipientManager.DB_PATH
        RecipientManager.DB_PATH = rec_db
        try:
            rec_mgr = RecipientManager()
            conn = sqlite3.connect(rec_db)
            conn.execute("INSERT INTO recipients (email, status) VALUES ('a@test.com', 'Pending')")
            conn.execute("INSERT INTO recipients (email, status) VALUES ('b@test.com', 'Pending')")
            conn.commit()
            conn.close()

            worker = CampaignWorker(
                mailer,
                rec_mgr,
                MagicMock(),
                template_path="tmpl1.html",
                placeholders={},
                fmt="html",
            )
            worker.set_rate(100000)
            worker.running = True
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            worker._loop = loop
            loop.run_until_complete(worker._process_once())
            loop.close()

            self.assertTrue(mailer.send_one.called, "Worker should call send_one")
        finally:
            RecipientManager.DB_PATH = original_rec_db
            if os.path.exists(rec_db):
                os.remove(rec_db)

if __name__ == '__main__':
    unittest.main()
