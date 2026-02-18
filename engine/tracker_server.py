from flask import Flask, request, redirect, send_file
import sqlite3
import datetime
import os
import threading
import io
from werkzeug.serving import make_server

from dbutil import connect

class TrackingServer:
    def __init__(self, db_path, host=None, port=None):
        self.app = Flask(__name__)
        self.db_path = db_path
        self.host = host or os.environ.get("CROSSMAILER_TRACK_HOST", "127.0.0.1")
        self.port = int(port or os.environ.get("CROSSMAILER_TRACK_PORT", "5000"))
        self.thread = None
        self._httpd = None
        self._setup_routes()

    def _setup_routes(self):
        @self.app.route('/open/<int:recipient_id>')
        def track_open(recipient_id):
            if not self._authorized(request):
                return ("forbidden", 403)
            self._log_event(recipient_id, "opened")
            # Return a 1x1 transparent pixel
            pixel = b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b'
            return send_file(io.BytesIO(pixel), mimetype='image/gif')

        @self.app.route('/click/<int:recipient_id>')
        def track_click(recipient_id):
            if not self._authorized(request):
                return ("forbidden", 403)
            target = request.args.get('target', 'https://example.com')
            self._log_event(recipient_id, "clicked")
            # Ensure target has schema
            if not target.startswith(('http://', 'https://')):
                target = 'http://' + target
            return redirect(target)

    def _authorized(self, req) -> bool:
        """
        Optional shared-secret token to prevent arbitrary third parties from
        mutating recipient metrics when the tracker is exposed.
        """
        token = os.environ.get("CROSSMAILER_TRACK_TOKEN")
        if not token:
            return True
        return req.args.get("t") == token

    def _log_event(self, recipient_id, event_type):
        """Update DB with event."""
        try:
            conn = connect(self.db_path)
            cur = conn.cursor()
            now = datetime.datetime.now().isoformat()
            
            if event_type == "opened":
                cur.execute(
                    "UPDATE recipients SET open_count = open_count + 1, last_open = ? WHERE id = ?",
                    (now, recipient_id)
                )
            elif event_type == "clicked":
                cur.execute(
                    "UPDATE recipients SET click_count = click_count + 1, last_click = ? WHERE id = ?",
                    (now, recipient_id)
                )
            conn.commit()
            conn.close()
            print(f"[{now}] Tracked {event_type} for ID {recipient_id}")
        except Exception as e:
            print(f"Tracking Error: {e}")

    def start(self):
        """Run HTTP server in a daemon thread."""
        if self.thread and self.thread.is_alive():
            return

        def _serve():
            try:
                self._httpd = make_server(self.host, self.port, self.app, threaded=True)
                self._httpd.serve_forever()
            except Exception as exc:
                # In some sandboxed environments binding a port is forbidden.
                print(f"[TrackingServer] Failed to start: {exc}")

        self.thread = threading.Thread(target=_serve, daemon=True)
        self.thread.start()

    def stop(self):
        if self._httpd:
            try:
                self._httpd.shutdown()
            except Exception:
                pass
            self._httpd = None
