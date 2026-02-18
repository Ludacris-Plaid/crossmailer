import unittest
import os
import sqlite3
import time
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.tracker_server import TrackingServer
from engine.recipient_manager import RecipientManager

class TestTrackingSystem(unittest.TestCase):
    def setUp(self):
        self.db_path = "tests/test_tracking.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
            
        # Init DB and Recipient
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "CREATE TABLE recipients (id INTEGER PRIMARY KEY, email TEXT, open_count INTEGER DEFAULT 0, last_open TEXT, click_count INTEGER DEFAULT 0, last_click TEXT)"
        )
        conn.execute("INSERT INTO recipients (email) VALUES ('trackme@test.com')")
        conn.commit()
        conn.close()
        
        # Use Flask test client (no real network bind required).
        self.server = TrackingServer(self.db_path, host="127.0.0.1", port=5001)
        self.client = self.server.app.test_client()

    def tearDown(self):
        # Server thread is daemon, will die with process. 
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_open_tracking(self):
        # 1. Simulate Open
        resp = self.client.get("/open/1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["Content-Type"], "image/gif")
        
        # 2. Verify DB
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT open_count, last_open FROM recipients WHERE id=1").fetchone()
        conn.close()
        
        self.assertEqual(row[0], 1)
        self.assertIsNotNone(row[1])

    def test_click_tracking(self):
        # 1. Simulate Click
        target = "http://example.com"
        resp = self.client.get(f"/click/1?target={target}", follow_redirects=False)
        
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.headers["Location"], target)
        
        # 2. Verify DB
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT click_count, last_click FROM recipients WHERE id=1").fetchone()
        conn.close()
        
        self.assertEqual(row[0], 1)
        self.assertIsNotNone(row[1])

if __name__ == '__main__':
    unittest.main()
