# -*- coding: utf-8 -*-
import asyncio, email.message
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
            raw = raw.replace(f"{{{k}}}", v)

        msg = email.message.EmailMessage()
        msg["Subject"] = placeholders.get("subject", "No subject")
        msg["From"]    = placeholders.get("from")
        msg["To"]      = placeholders.get("to")
        msg["Message-ID"] = f"<{asyncio.get_running_loop().time()}@{placeholders.get('domain')}>"

        if fmt == "html":
            msg.add_alternative(raw, subtype="html")
        else:
            msg.set_content(raw)
        return msg

    async def send_one(self, tmpl_path, placeholders, fmt):
        try:
            server = self.smtp_mgr.get_active_server()
            pwd = decrypt(server["password_encrypted"], self.crypto.key)
            msg = await self._build_message(tmpl_path, placeholders, fmt)
            await send(message=msg,
                       hostname=server["host"],
                       port=server["port"],
                       username=server["username"],
                       password=pwd,
                       start_tls=True,
                       timeout=15)
            self.stats_cb.email_sent(success=True)
            return True
        except Exception as exc:
            self.stats_cb.email_sent(success=False, error=str(exc))
            return False
