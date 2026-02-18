import argparse
import os
import signal
import sys
import threading
import time

from engine.ai_supervisor import AISupervisor
from engine.inbox_monitor import InboxMonitor
from engine.mailer import Mailer
from engine.proxy_harvester import ProxyHarvester
from engine.recipient_manager import RecipientManager
from engine.sentinel import LogSentinel
from engine.sequence_manager import SequenceManager
from engine.tracker_server import TrackingServer
from engine.worker import CampaignWorker
from scheduler.warmup import WarmupScheduler
from security.crypto import CryptoHelper
from smtp_manager.manager import SMTPManager


def main() -> int:
    # If this is running on a headless server, avoid Qt trying to load xcb.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    ap = argparse.ArgumentParser(description="CrossMailer headless runner (server mode).")
    ap.add_argument("--template", help="Template path for blast mode (no sequence).")
    ap.add_argument("--rate", type=int, default=int(os.environ.get("CROSSMAILER_RATE", "200")), help="Emails per hour.")
    ap.add_argument("--from", dest="from_addr", default=os.environ.get("CROSSMAILER_FROM", ""), help="From address.")
    ap.add_argument("--domain", default=os.environ.get("CROSSMAILER_DOMAIN", ""), help="Domain for Message-ID.")
    ap.add_argument("--subject", default=os.environ.get("CROSSMAILER_SUBJECT", ""), help="Default subject.")
    ap.add_argument("--tracking-base", default=os.environ.get("CROSSMAILER_TRACKING_BASE", "http://127.0.0.1:5000"))
    ap.add_argument("--warmup", action="store_true", help="Enable warm-up scheduler ramp.")
    ap.add_argument("--ai-autopilot", action="store_true", help="Enable AI supervisor control loop.")
    args = ap.parse_args()

    passphrase = os.environ.get("CROSSMAILER_PASS")
    if not passphrase:
        print("Missing CROSSMAILER_PASS environment variable.", file=sys.stderr)
        return 2

    crypto = CryptoHelper(passphrase)
    smtp_mgr = SMTPManager(crypto)
    recipient_mgr = RecipientManager()
    seq_mgr = SequenceManager(recipient_mgr.DB_PATH)

    mailer = Mailer(crypto, smtp_mgr, stats_callback=_NullStats())

    tracker = TrackingServer(RecipientManager.DB_PATH)
    monitor = InboxMonitor(smtp_mgr, recipient_mgr)
    sentinel = LogSentinel(recipient_mgr.DB_PATH, smtp_mgr)
    proxy_harvester = ProxyHarvester()
    warmup = WarmupScheduler()

    worker = CampaignWorker(
        mailer,
        recipient_mgr,
        seq_mgr,
        template_path=args.template,
        placeholders={
            "from": args.from_addr,
            "subject": args.subject,
            "domain": args.domain,
            "tracking_base_url": args.tracking_base,
        },
        fmt="html" if (args.template or "").endswith(".html") else "text",
    )
    worker.set_rate(max(10, min(10000, args.rate)))

    controller = _Controller(worker=worker, warmup=warmup, smtp_mgr=smtp_mgr)
    ai = AISupervisor(
        recipient_mgr.DB_PATH,
        smtp_mgr,
        model_config={
            "source": "Ollama",
            "ollama_model": os.environ.get("CROSSMAILER_OLLAMA_MODEL", "spamqueen:latest"),
        },
        action_cb=controller.handle_action,
        note_cb=lambda m: print(m, flush=True),
    )

    should_stop = threading.Event()

    def _stop(*_):
        should_stop.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    tracker.start()
    monitor.start()
    sentinel.start()

    if args.warmup:
        warmup.configure(worker.rate)
        warmup.stage_changed.connect(lambda _s, _t, r: worker.set_rate(r))
        warmup.start()

    if args.ai_autopilot:
        ai.start()

    # Run the QThread's run() in a normal Python thread (no GUI needed).
    t = threading.Thread(target=worker.run, daemon=True)
    t.start()

    print(f"[CrossMailer] Headless running. rate={worker.rate} emails/hr", flush=True)
    if args.ai_autopilot:
        print("[CrossMailer] AI autopilot enabled.", flush=True)
    print("[CrossMailer] Ctrl+C to stop.", flush=True)

    while not should_stop.is_set():
        time.sleep(0.5)

    print("[CrossMailer] Stopping...", flush=True)
    try:
        worker.stop()
    except Exception:
        pass
    try:
        warmup.stop()
    except Exception:
        pass
    try:
        ai.stop()
    except Exception:
        pass
    try:
        monitor.stop()
        sentinel.stop()
        proxy_harvester.stop()
    except Exception:
        pass
    try:
        tracker.stop()
    except Exception:
        pass

    t.join(timeout=10)
    print("[CrossMailer] Stopped.", flush=True)
    return 0


class _NullStats:
    def email_sent(self, success: bool, error: str = ""):
        # Headless mode doesn't have UI signals; keep stdout concise.
        if not success:
            print(f"[Mailer] Failed: {error}", flush=True)


class _Controller:
    def __init__(self, *, worker: CampaignWorker, warmup: WarmupScheduler, smtp_mgr: SMTPManager):
        self.worker = worker
        self.warmup = warmup
        self.smtp_mgr = smtp_mgr

    def handle_action(self, action: str, params: dict):
        if action == "emergency_stop":
            reason = params.get("reason", "AI requested stop")
            print(f"[AI] emergency_stop: {reason}", flush=True)
            self.worker.stop()
            try:
                self.warmup.stop()
            except Exception:
                pass
        elif action == "disable_server":
            host = params.get("host")
            if host:
                print(f"[AI] disable_server: {host}", flush=True)
                self.smtp_mgr.disable_server_by_host(host)
        elif action == "set_rate":
            rate = params.get("emails_per_hr")
            try:
                rate = int(rate)
            except Exception:
                return
            rate = max(10, min(10000, rate))
            print(f"[AI] set_rate: {rate} emails/hr", flush=True)
            try:
                self.warmup.stop()
            except Exception:
                pass
            self.worker.set_rate(rate)


if __name__ == "__main__":
    raise SystemExit(main())
