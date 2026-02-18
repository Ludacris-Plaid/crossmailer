import unittest
import os
import sqlite3
import asyncio
from unittest.mock import MagicMock, AsyncMock

# Add project root to path
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.recipient_manager import RecipientManager
from engine.worker import CampaignWorker
from engine.validation_worker import ValidationWorker

class TestRecipientFeatures(unittest.TestCase):
    def setUp(self):
        self.test_db = "tests/test_recipients.db"
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
            
        self.original_db_path = RecipientManager.DB_PATH
        RecipientManager.DB_PATH = self.test_db
        self.mgr = RecipientManager()

    def tearDown(self):
        RecipientManager.DB_PATH = self.original_db_path
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    def test_import_and_dedupe(self):
        # Create a dummy file
        with open("tests/dummy_emails.txt", "w") as f:
            f.write("test1@gmail.com\n")
            f.write("test2@yahoo.com\n")
            f.write("test1@gmail.com\n") # Duplicate
            
        count = self.mgr.import_txt("tests/dummy_emails.txt")
        self.assertEqual(count, 2, "Should import 2 unique emails")
        
        rows = self.mgr.get_recipients()
        self.assertEqual(len(rows), 2)
        os.remove("tests/dummy_emails.txt")

    def test_provider_extraction(self):
        self.assertEqual(self.mgr._extract_provider("user@gmail.com"), "Gmail")
        self.assertEqual(self.mgr._extract_provider("user@outlook.co.uk"), "Outlook")

    def test_syntax_validation(self):
        self.assertTrue(self.mgr.validate_syntax("valid@example.com"))
        self.assertFalse(self.mgr.validate_syntax("invalid-email"))
        self.assertFalse(self.mgr.validate_syntax("@no-user.com"))

    def test_worker_iteration(self):
        """Test that CampaignWorker iterates through recipients."""
        # 1. Add recipients
        conn = sqlite3.connect(self.test_db)
        conn.execute("INSERT INTO recipients (email, status) VALUES ('a@test.com', 'Pending')")
        conn.execute("INSERT INTO recipients (email, status) VALUES ('b@test.com', 'Pending')")
        conn.commit()
        conn.close()

        # 2. Mock Mailer
        mailer = MagicMock()
        mailer.send_one = AsyncMock(return_value=True)

        # 3. Run Worker
        worker = CampaignWorker(
            mailer,
            self.mgr,
            MagicMock(),
            template_path="tmpl.txt",
            placeholders={},
            fmt="text",
        )
        worker.set_rate(10000)
        worker.running = True

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        worker._loop = loop
        loop.run_until_complete(worker._process_once())
        loop.close()
        
        # 4. Verify
        self.assertEqual(mailer.send_one.call_count, 2)
        
        # Check DB status
        rows = self.mgr.get_recipients()
        for r in rows:
            self.assertEqual(r['status'], 'Sent')

if __name__ == '__main__':
    unittest.main()
