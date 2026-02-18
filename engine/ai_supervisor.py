import json
import threading
import time

from PyQt5 import QtCore

from dbutil import connect
from engine.ai_brain import AIBrain


class AISupervisor(QtCore.QObject):
    """
    Periodically asks the configured LLM for operational recommendations and emits
    validated actions back to the UI.

    This is intentionally constrained to a small action set.
    """

    action_emitted = QtCore.pyqtSignal(str, dict)  # action_type, params
    note_emitted = QtCore.pyqtSignal(str)

    def __init__(self, recipient_db_path: str, smtp_mgr, model_config=None, *, action_cb=None, note_cb=None):
        super().__init__()
        self.rec_db = recipient_db_path
        self.smtp_mgr = smtp_mgr
        self.brain = AIBrain(model_config)
        self._action_cb = action_cb
        self._note_cb = note_cb
        self.running = False
        self.thread = None

    def start(self, interval=90):
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
                stats = self._collect_stats()
                self._ask_and_emit(stats)
            except Exception as e:
                self._emit_note(f"[AI] Supervisor error: {e}")

            for _ in range(interval):
                if not self.running:
                    break
                time.sleep(1)

    def _collect_stats(self) -> dict:
        conn = connect(self.rec_db)
        cur = conn.cursor()
        cur.execute("SELECT status, COUNT(*) FROM recipients GROUP BY status")
        counts = dict(cur.fetchall())
        # Engagement (best effort, could be null on older schemas)
        try:
            cur.execute("SELECT SUM(CASE WHEN open_count > 0 THEN 1 ELSE 0 END) FROM recipients")
            opened_unique = cur.fetchone()[0] or 0
        except Exception:
            opened_unique = 0
        conn.close()

        servers = self.smtp_mgr.get_all_servers()
        return {
            "recipient_counts": counts,
            "opened_unique": opened_unique,
            "smtp_servers": [
                {
                    "host": s.get("host"),
                    "health_score": s.get("health_score"),
                    "consecutive_errors": s.get("consecutive_errors"),
                    "daily_sent": s.get("daily_sent"),
                    "daily_limit": s.get("daily_limit"),
                    "warmup_enabled": s.get("warmup_enabled"),
                    "warmup_stage": s.get("warmup_stage"),
                }
                for s in servers
            ],
        }

    def _ask_and_emit(self, stats: dict) -> None:
        prompt = (
            "You are operating the CrossMailer desktop application for a legitimate opt-in email campaign.\n"
            "Given the current stats, output STRICT JSON ONLY with this schema:\n"
            '{ "actions": [ { "type": "emergency_stop", "reason": "..." } |'
            ' { "type": "disable_server", "host": "..." } |'
            ' { "type": "set_rate", "emails_per_hr": 100 } ], "notes": "..." }\n'
            "Constraints:\n"
            "- Only emit actions when necessary.\n"
            "- emails_per_hr must be an integer between 10 and 10000.\n"
            "- Do not propose illegal or deceptive behavior.\n\n"
            f"STATS:\n{json.dumps(stats)}"
        )

        # Use the chat interface to reuse the currently-configured model backend.
        text = self.brain.chat(prompt)
        try:
            match = None
            # Tolerate incidental wrappers, but require a JSON object inside.
            for i, ch in enumerate(text):
                if ch == "{":
                    match = text[i:]
                    break
            if match is None:
                raise ValueError("No JSON object found in model output.")

            payload = json.loads(match)
        except Exception as e:
            self._emit_note(f"[AI] Bad response (ignored): {e}")
            return

        notes = payload.get("notes")
        if isinstance(notes, str) and notes.strip():
            self._emit_note(f"[AI] {notes.strip()}")

        actions = payload.get("actions", [])
        if not isinstance(actions, list):
            return

        for act in actions:
            if not isinstance(act, dict):
                continue
            t = act.get("type")
            if t == "emergency_stop":
                reason = act.get("reason") or "AI requested stop"
                self._emit_action("emergency_stop", {"reason": str(reason)})
            elif t == "disable_server":
                host = act.get("host")
                if host:
                    self._emit_action("disable_server", {"host": str(host)})
            elif t == "set_rate":
                rate = act.get("emails_per_hr")
                try:
                    rate_i = int(rate)
                except Exception:
                    continue
                if 10 <= rate_i <= 10000:
                    self._emit_action("set_rate", {"emails_per_hr": rate_i})

    def _emit_note(self, message: str) -> None:
        if self._note_cb is not None:
            try:
                self._note_cb(message)
            except Exception:
                pass
        self.note_emitted.emit(message)

    def _emit_action(self, action: str, params: dict) -> None:
        if self._action_cb is not None:
            try:
                self._action_cb(action, params)
            except Exception:
                pass
        self.action_emitted.emit(action, params)
