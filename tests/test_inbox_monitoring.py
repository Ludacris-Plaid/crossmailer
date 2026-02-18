import unittest
import os
import sqlite3
import imaplib
import sys
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.inbox_monitor import InboxMonitor
from engine.recipient_manager import RecipientManager
from smtp_manager.manager import SMTPManager
from security.crypto import CryptoHelper

class TestInboxMonitoring(unittest.TestCase):
    def setUp(self):
        self.db_path = "tests/test_inbox.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

        self._old_salt_path = os.environ.get("CROSSMAILER_SALT_PATH")
        os.environ["CROSSMAILER_SALT_PATH"] = "tests/test_salt_inbox.bin"

        self.crypto = CryptoHelper("secret")

        self._old_smtp_db = SMTPManager.DB_PATH
        SMTPManager.DB_PATH = "tests/test_smtp_inbox.db"
        self.smtp_mgr = SMTPManager(self.crypto)

        self._old_rec_db = RecipientManager.DB_PATH
        RecipientManager.DB_PATH = "tests/test_recipients_inbox.db"
        self.recipient_mgr = RecipientManager()

        self.monitor = InboxMonitor(self.smtp_mgr, self.recipient_mgr)

    def tearDown(self):
        test_smtp_db = SMTPManager.DB_PATH
        test_rec_db = RecipientManager.DB_PATH

        SMTPManager.DB_PATH = self._old_smtp_db
        RecipientManager.DB_PATH = self._old_rec_db
        if self._old_salt_path is None:
            os.environ.pop("CROSSMAILER_SALT_PATH", None)
        else:
            os.environ["CROSSMAILER_SALT_PATH"] = self._old_salt_path

        if os.path.exists(test_rec_db):
            os.remove(test_rec_db)
        if os.path.exists(test_smtp_db):
            os.remove(test_smtp_db)
        if os.path.exists("tests/test_salt_inbox.bin"):
            os.remove("tests/test_salt_inbox.bin")

    @patch('imaplib.IMAP4_SSL')
    def test_scan_for_replies(self, mock_imap):
        # 1. Setup Mock IMAP
        instance = mock_imap.return_value
        instance.select.return_value = ('OK', [b'1'])
        instance.search.return_value = ('OK', [b'1'])
        
        # Mock Email Content
        raw_email = b"""From: John Doe <replier@test.com>
Subject: Re: Hello
To: sender@test.com

I am replying!
"""
        instance.fetch.return_value = ('OK', [(b'1 (RFC822 {80}', raw_email)])
        
        # 2. Add recipient to DB
        self.recipient_mgr.import_txt = MagicMock()
        conn = sqlite3.connect(self.recipient_mgr.DB_PATH)
        conn.execute("INSERT INTO recipients (email, status) VALUES ('replier@test.com', 'Sent')")
        conn.commit()
        conn.close()

        # 3. Scan
        self.monitor._scan_for_replies(instance)
        
        # 4. Verify status changed to 'Replied'
        rows = self.recipient_mgr.get_recipients()
        self.assertEqual(rows[0]['status'], 'Replied')

    @patch('imaplib.IMAP4_SSL')
    def test_scan_for_bounces(self, mock_imap):
        # 1. Setup Mock IMAP
        instance = mock_imap.return_value
        instance.select.return_value = ('OK', [b'1'])
        instance.search.return_value = ('OK', [b'1'])
        
        # Mock Bounce Content
        raw_email = b"""From: postmaster@provider.com
Subject: Undelivered Mail Returned to Sender
To: sender@test.com

The recipient address <bad@test.com> was rejected.
"""
        instance.fetch.return_value = ('OK', [(b'1 (RFC822 {80}', raw_email)])
        
        # 2. Add recipient to DB
        conn = sqlite3.connect(self.recipient_mgr.DB_PATH)
        conn.execute("INSERT INTO recipients (email, status) VALUES ('bad@test.com', 'Sent')")
        conn.commit()
        conn.close()

        # 3. Scan
        self.monitor._scan_for_bounces(instance)
        
        # 4. Verify status changed to 'Bounced'
        rows = self.recipient_mgr.get_recipients()
        self.assertEqual(rows[0]['status'], 'Bounced')

if __name__ == '__main__':
    unittest.main()
