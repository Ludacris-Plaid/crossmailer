import imaplib
import email
import re
import threading
import time
from security.crypto import decrypt

class InboxMonitor:
    def __init__(self, smtp_mgr, recipient_mgr):
        self.smtp_mgr = smtp_mgr
        self.recipient_mgr = recipient_mgr
        self.running = False
        self.thread = None

    def start(self, interval=300):
        """Start monitoring in a background thread."""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, args=(interval,), daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False

    def _run(self, interval):
        while self.running:
            try:
                servers = self.smtp_mgr.get_all_servers()
                for server in servers:
                    if not self.running: break
                    if server.get('imap_host'):
                        self._check_inbox(server)
            except Exception as e:
                print(f"InboxMonitor Error: {e}")
            
            # Wait for next interval or stop signal
            for _ in range(interval):
                if not self.running: break
                time.sleep(1)

    def _check_inbox(self, server):
        """Connect to one inbox and scan for bounces/replies."""
        try:
            # Decrypt password
            pwd = decrypt(server["password_encrypted"], self.smtp_mgr.crypto.key).decode()
            
            if server['imap_use_ssl']:
                mail = imaplib.IMAP4_SSL(server['imap_host'], server['imap_port'])
            else:
                mail = imaplib.IMAP4(server['imap_host'], server['imap_port'])
                
            mail.login(server['username'], pwd)
            mail.select("inbox")

            # 1. Check for Bounces (Simplified: search for 'undelivered' or 'failed')
            # In a pro version, we'd use specific RFC headers
            self._scan_for_bounces(mail)

            # 2. Check for Replies (Search for 'Re:')
            self._scan_for_replies(mail)

            mail.logout()
        except Exception as e:
            print(f"IMAP Error for {server['username']}: {e}")

    def _scan_for_bounces(self, mail):
        """Mark recipients as Invalid if we find a bounce notification."""
        status, messages = mail.search(None, '(OR SUBJECT "undelivered" SUBJECT "failed")')
        if status != 'OK': return
        
        for num in messages[0].split():
            _, data = mail.fetch(num, '(RFC822)')
            msg = email.message_from_bytes(data[0][1])
            body = str(msg.get_payload())
            
            # Use regex to find the email that failed
            # This is a heuristic; real bounce parsing is complex
            emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', body)
            for e in emails:
                # If we have this email in our DB, mark it as Failed/Invalid
                self.recipient_mgr.update_status(e, "Bounced")

    def _scan_for_replies(self, mail):
        """Stop sequences if the lead replied."""
        status, messages = mail.search(None, '(SUBJECT "Re:")')
        if status != 'OK': return
        
        for num in messages[0].split():
            _, data = mail.fetch(num, '(RFC822)')
            msg = email.message_from_bytes(data[0][1])
            from_header = msg.get('From')
            
            # Extract email from "Name <email@site.com>"
            match = re.search(r'<([^>]+)>', from_header)
            email_addr = match.group(1) if match else from_header.strip()
            
            # Mark as Replied in DB
            self.recipient_mgr.update_status(email_addr, "Replied")
