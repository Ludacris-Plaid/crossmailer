import asyncio
import email.message
import os
import urllib.parse
from aiosmtplib import send
from security.crypto import decrypt

class Mailer:
    """Creates and sends a single email inside a sandboxed process."""
    def __init__(self, crypto, smtp_mgr, stats_callback):
        self.crypto = crypto
        self.smtp_mgr = smtp_mgr
        self.stats_cb = stats_callback   # UI object exposing .email_sent()

    async def _build_message(self, tmpl_path, placeholders, fmt):
        with open(tmpl_path, "r", encoding="utf-8") as f:
            raw = f.read()
        for k, v in placeholders.items():
            raw = raw.replace(f"{{{k}}}", "" if v is None else str(v))

        # Inject Tracking Pixel if HTML and recipient_id is present
        if fmt == "html" and "recipient_id" in placeholders:
            tracking_base = placeholders.get("tracking_base_url", "http://127.0.0.1:5000").rstrip("/")
            token = os.environ.get("CROSSMAILER_TRACK_TOKEN")
            qs = ""
            if token:
                qs = "?" + urllib.parse.urlencode({"t": token})
            pixel = f'<img src="{tracking_base}/open/{placeholders["recipient_id"]}{qs}" width="1" height="1" style="display:none;">'
            # Try to insert before </body>
            if "</body>" in raw:
                raw = raw.replace("</body>", f"{pixel}</body>")
            else:
                raw += pixel

        msg = email.message.EmailMessage()
        msg["Subject"] = placeholders.get("subject", "No subject")
        msg["From"] = placeholders.get("from") or ""
        msg["To"] = placeholders.get("to") or ""

        domain = placeholders.get("domain")
        if not domain and "@" in (msg["From"] or ""):
            domain = (msg["From"].split("@", 1)[1] or "").strip()
        domain = domain or "local"
        msg["Message-ID"] = f"<{asyncio.get_running_loop().time()}@{domain}>"

        if fmt == "html":
            msg.add_alternative(raw, subtype="html")
        else:
            msg.set_content(raw)
        return msg

    async def send_one(self, tmpl_path, placeholders, fmt):
        server = None
        try:
            server = self.smtp_mgr.get_active_server()
            if not server:
                raise RuntimeError("No available SMTP servers (limits reached or empty).")

            pwd = decrypt(server["password_encrypted"], self.crypto.key).decode()
            msg = await self._build_message(tmpl_path, placeholders, fmt)
            
            await send(message=msg,
                       hostname=server["host"],
                       port=server["port"],
                       username=server["username"],
                       password=pwd,
                       start_tls=True,
                       timeout=15)
            
            self.smtp_mgr.update_server_status(server["id"], True)
            self.stats_cb.email_sent(success=True)
            return True

        except Exception as exc:
            if server:
                self.smtp_mgr.update_server_status(server["id"], False, str(exc))
            self.stats_cb.email_sent(success=False, error=str(exc))
            return False
