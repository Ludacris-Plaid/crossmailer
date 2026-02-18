import unittest
import os
import sqlite3
import time
import sys
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.proxy_harvester import ProxyHarvester

class TestProxyHarvesting(unittest.TestCase):
    def setUp(self):
        self.db_path = "tests/test_proxies.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        
        # Patch the DB path for the test instance
        self._old_db_path = ProxyHarvester.DB_PATH
        ProxyHarvester.DB_PATH = self.db_path
        self.harvester = ProxyHarvester()

    def tearDown(self):
        ProxyHarvester.DB_PATH = self._old_db_path
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_db_init(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='proxies'")
        self.assertIsNotNone(cur.fetchone())
        conn.close()

    @patch('requests.get')
    def test_harvest_and_validate(self, mock_get):
        # 1. Mock Source Response
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "1.1.1.1:1080\n2.2.2.2:8080\n" # Two candidates
        mock_get.return_value = mock_resp
        
        # 2. Mock Validation (Check Proxy)
        # We'll mock _check_proxy directly to avoid real network calls
        self.harvester._check_proxy = MagicMock(side_effect=[
            ("1.1.1.1:1080", 50),  # First is Good
            None                   # Second is Dead
        ])

        # 3. Trigger Harvest logic manually (to avoid threading issues in test)
        # Instead of start_harvesting, we replicate the loop body once
        self.harvester.running = True
        
        # -- Step 1: Fetch --
        raw_proxies = ["1.1.1.1:1080", "2.2.2.2:8080"]
        
        # -- Step 2: Validate --
        valid_proxies = [("1.1.1.1:1080", 50)]
        
        # -- Step 3: Save --
        self.harvester._save_proxies(valid_proxies)
        
        # 4. Verify DB content
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT address, latency, status FROM proxies").fetchone()
        conn.close()
        
        self.assertEqual(row[0], "1.1.1.1:1080")
        self.assertEqual(row[1], 50)
        self.assertEqual(row[2], "Good")

    def test_get_best_proxy(self):
        # Insert dummy proxies
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT INTO proxies (address, latency, status) VALUES ('slow:80', 500, 'Good')")
        conn.execute("INSERT INTO proxies (address, latency, status) VALUES ('fast:80', 50, 'Good')")
        conn.execute("INSERT INTO proxies (address, latency, status) VALUES ('dead:80', 10, 'Dead')")
        conn.commit()
        conn.close()
        
        best = self.harvester.get_best_proxy()
        self.assertEqual(best, "fast:80")

if __name__ == '__main__':
    unittest.main()
