import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio
import os
import sqlite3
import tempfile
import shutil
from engine.mailer import Mailer
from engine.recipient_manager import RecipientManager
from smtp_manager.manager import SMTPManager
from security.crypto import CryptoHelper, encrypt, decrypt

class TestEndpoints(unittest.TestCase):
    
    def setUp(self):
        # Create a temp dir for DBs
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_recipients.db")

        # Isolate crypto salt so tests don't depend on local state.
        self._old_salt_path = os.environ.get("CROSSMAILER_SALT_PATH")
        os.environ["CROSSMAILER_SALT_PATH"] = os.path.join(self.test_dir, "salt.bin")
        
        # Setup Crypto
        self.crypto = CryptoHelper("testpass")
        
        # Setup RecipientManager
        self._old_rec_db = RecipientManager.DB_PATH
        RecipientManager.DB_PATH = self.db_path
        self.recipient_mgr = RecipientManager()
        
        # Setup SMTPManager
        self.smtp_db_path = os.path.join(self.test_dir, "test_smtp.db")
        self._old_smtp_db = SMTPManager.DB_PATH
        SMTPManager.DB_PATH = self.smtp_db_path
        self.smtp_mgr = SMTPManager(self.crypto)

    def tearDown(self):
        RecipientManager.DB_PATH = self._old_rec_db
        SMTPManager.DB_PATH = self._old_smtp_db
        if self._old_salt_path is None:
            os.environ.pop("CROSSMAILER_SALT_PATH", None)
        else:
            os.environ["CROSSMAILER_SALT_PATH"] = self._old_salt_path
        shutil.rmtree(self.test_dir)

    def test_crypto(self):
        """Test encryption and decryption endpoint"""
        data = b"secret_smtp_password"
        encrypted = encrypt(data, self.crypto.key)
        decrypted = decrypt(encrypted.decode('utf-8'), self.crypto.key)
        self.assertEqual(data, decrypted)

    def test_recipient_manager_import(self):
        """Test importing recipients"""
        txt_path = os.path.join(self.test_dir, "emails.txt")
        with open(txt_path, "w") as f:
            f.write("test1@gmail.com\ntest2@yahoo.com\ninvalid-email")
        
        count = self.recipient_mgr.import_txt(txt_path)
        self.assertEqual(count, 3) # Import doesn't validate in this path.
        
        rows = self.recipient_mgr.get_recipients()
        self.assertEqual(len(rows), 3)
        
        # Verify provider detection
        r1 = next(r for r in rows if r['email'] == 'test1@gmail.com')
        self.assertEqual(r1['provider'], 'Gmail')

    def test_smtp_manager_rotation(self):
        """Test SMTP server rotation logic"""
        # Add 2 servers
        self.smtp_mgr.add_server("host1", 587, "user1", "pass1")
        self.smtp_mgr.add_server("host2", 587, "user2", "pass2")
        
        # Get first server
        s1 = self.smtp_mgr.get_active_server()
        self.assertIsNotNone(s1)
        
        # Simulate send success
        self.smtp_mgr.update_server_status(s1['id'], success=True)
        
        # Get next (should be same or rotated depending on implementation, 
        # but logic often picks highest health / lowest usage)
        s2 = self.smtp_mgr.get_active_server()
        self.assertIsNotNone(s2)

    @patch("engine.mailer.send", new_callable=AsyncMock)
    def test_mailer_send(self, mock_send):
        """Test Mailer sending logic (mocking network)"""
        # Create dummy template
        tmpl_path = os.path.join(self.test_dir, "template.html")
        with open(tmpl_path, "w") as f:
            f.write("<html><body>Hello {first_name}</body></html>")
            
        # Add a server
        self.smtp_mgr.add_server("smtp.test.com", 587, "user", "pass")
        
        stats_mock = MagicMock()
        mailer = Mailer(self.crypto, self.smtp_mgr, stats_mock)
        
        placeholders = {
            "to": "victim@example.com",
            "from": "hacker@example.com",
            "subject": "Test",
            "domain": "example.com",
            "first_name": "John"
        }
        
        # Run async test
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(mailer.send_one(tmpl_path, placeholders, "html"))
        loop.close()
        
        self.assertTrue(result)
        mock_send.assert_called_once()
        stats_mock.email_sent.assert_called_with(success=True)

    def test_ai_integration_mock(self):
        """Test AI Worker integration with mocked brain"""
        from engine.ai_worker import AIWorker
        
        with patch("engine.ai_worker.AIBrain") as MockBrain:
            mock_brain_instance = MockBrain.return_value
            mock_brain_instance.generate_email_campaign.return_value = {"subject": "S", "body": "B"}
            mock_brain_instance.is_model_downloaded.return_value = True
            
            worker = AIWorker({})
            
            # Use a slot to capture the signal
            results = []
            def capture(res):
                results.append(res)
            
            worker.generation_finished.connect(capture)
            
            # Trigger generate directly (skipping thread start for unit test simplicity if possible,
            # but QThread needs event loop. We can just call run() directly for logic test)
            worker.params = {"topic": "t", "audience": "a", "tone": "x"}
            worker.action = "generate"
            worker.run()
            
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0], {"subject": "S", "body": "B"})

if __name__ == '__main__':
    unittest.main()
