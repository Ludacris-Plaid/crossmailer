import unittest
import os
import sqlite3
import time
import asyncio
from unittest.mock import MagicMock, AsyncMock

# Add project root to path
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.recipient_manager import RecipientManager
from engine.sequence_manager import SequenceManager
from engine.worker import CampaignWorker

class TestDripSequences(unittest.TestCase):
    def setUp(self):
        self.db_path = "tests/test_sequences.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
            
        self.original_db_path = RecipientManager.DB_PATH
        RecipientManager.DB_PATH = self.db_path
        
        self.rec_mgr = RecipientManager()
        self.seq_mgr = SequenceManager(self.db_path)

    def tearDown(self):
        RecipientManager.DB_PATH = self.original_db_path
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_sequence_progression(self):
        # 1. Create Sequence: Step 1 (0 delay), Step 2 (2 hours delay)
        seq_id = self.seq_mgr.create_sequence("Test Campaign")
        self.seq_mgr.add_step(seq_id, 1, "tmpl1.txt", 2, "Subject 1")
        self.seq_mgr.add_step(seq_id, 2, "tmpl2.txt", 24, "Subject 2")
        
        # 2. Add Recipient
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO recipients (email, sequence_id, current_step, next_send_time) 
            VALUES ('lead@test.com', ?, 0, 0)
        """, (seq_id,))
        conn.commit()
        conn.close()

        # 3. Mock Mailer
        mailer = MagicMock()
        mailer.send_one = AsyncMock(return_value=True)

        # 4. Run Worker (Step 1)
        worker = CampaignWorker(mailer, self.rec_mgr, self.seq_mgr)
        worker.set_rate(1000)
        worker.running = True
        worker._loop = asyncio.new_event_loop()
        
        asyncio.set_event_loop(worker._loop)
        worker._loop.run_until_complete(worker._process_once())
        worker._loop.close()
        
        # 5. Verify Step 1 Sent
        self.assertEqual(mailer.send_one.call_count, 1)
        # Verify call used Step 1 template
        args = mailer.send_one.call_args[0]
        self.assertEqual(args[0], "tmpl1.txt")
        
        # 6. Verify Scheduled for Step 2
        rows = self.rec_mgr.get_recipients()
        lead = rows[0]
        self.assertEqual(lead['current_step'], 1)
        # Should be scheduled ~2 hours from now
        self.assertGreater(lead['next_send_time'], time.time() + 7100)

if __name__ == '__main__':
    unittest.main()
