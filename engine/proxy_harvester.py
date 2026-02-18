import requests
import re
import threading
import time
import sqlite3
import os
from concurrent.futures import ThreadPoolExecutor

from dbutil import connect

class ProxyHarvester:
    DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "proxies.db")
    SOURCES = [
        "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&timeout=10000&country=all",
        "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
        "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt"
    ]

    def __init__(self):
        self._init_db()
        self.running = False
        self.thread = None

    def _init_db(self):
        os.makedirs(os.path.dirname(self.DB_PATH), exist_ok=True)
        conn = connect(self.DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS proxies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT UNIQUE, -- ip:port
                protocol TEXT DEFAULT 'socks5',
                latency INTEGER, -- ms
                last_checked TEXT,
                status TEXT DEFAULT 'Good' -- Good, Dead
            )
        """)
        conn.commit()
        conn.close()

    def start_harvesting(self):
        if self.running: return
        self.running = True
        self.thread = threading.Thread(target=self._harvest_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False

    def _harvest_loop(self):
        while self.running:
            print("[ProxyHarvester] Fetching new proxies...")
            raw_proxies = set()
            
            # 1. Fetch
            for url in self.SOURCES:
                try:
                    resp = requests.get(url, timeout=10)
                    if resp.status_code == 200:
                        # Find ip:port pattern
                        matches = re.findall(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{2,5}", resp.text)
                        raw_proxies.update(matches)
                except Exception as e:
                    print(f"Failed source {url}: {e}")

            print(f"[ProxyHarvester] Found {len(raw_proxies)} candidates. Validating...")
            
            # 2. Validate in Parallel
            valid_proxies = []
            with ThreadPoolExecutor(max_workers=20) as executor:
                results = executor.map(self._check_proxy, raw_proxies)
                valid_proxies = [p for p in results if p]

            # 3. Save
            self._save_proxies(valid_proxies)
            print(f"[ProxyHarvester] Saved {len(valid_proxies)} valid proxies.")

            # Sleep 1 hour
            for _ in range(3600):
                if not self.running: break
                time.sleep(1)

    def _check_proxy(self, proxy_addr):
        """Verify proxy works by hitting a lightweight target."""
        if not self.running: return None
        proxies = {
            'http': f'socks5://{proxy_addr}',
            'https': f'socks5://{proxy_addr}'
        }
        try:
            start = time.time()
            # Use a reliable target that returns small data
            requests.get("http://www.google.com/generate_204", proxies=proxies, timeout=5)
            latency = int((time.time() - start) * 1000)
            return (proxy_addr, latency)
        except:
            return None

    def _save_proxies(self, proxy_list):
        conn = connect(self.DB_PATH)
        cur = conn.cursor()
        
        # Mark all old as potentially stale? Or just upsert.
        # We will Upsert.
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        
        for addr, latency in proxy_list:
            try:
                cur.execute("""
                    INSERT INTO proxies (address, latency, last_checked, status)
                    VALUES (?, ?, ?, 'Good')
                    ON CONFLICT(address) DO UPDATE SET
                    latency=excluded.latency,
                    last_checked=excluded.last_checked,
                    status='Good'
                """, (addr, latency, timestamp))
            except sqlite3.OperationalError:
                # Fallback for older sqlite versions without upsert
                cur.execute("INSERT OR REPLACE INTO proxies (address, protocol, latency, last_checked, status) VALUES (?, 'socks5', ?, ?, 'Good')", (addr, latency, timestamp))
        
        conn.commit()
        conn.close()

    def get_best_proxy(self):
        """Get a random good proxy."""
        conn = connect(self.DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT address FROM proxies WHERE status='Good' ORDER BY latency ASC LIMIT 1")
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None
