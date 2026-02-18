import asyncio
import time
from PyQt5 import QtCore

class CampaignWorker(QtCore.QThread):
    """
    Background worker that runs the email sending loop.
    Supports single blasts and multi-step sequences.
    """
    finished_signal = QtCore.pyqtSignal()
    progress_signal = QtCore.pyqtSignal(int, int) # sent, total

    def __init__(self, mailer, recipient_manager, sequence_manager, template_path=None, placeholders=None, fmt="text"):
        super().__init__()
        self.mailer = mailer
        self.mgr = recipient_manager
        self.seq_mgr = sequence_manager
        self.template_path = template_path # Fallback for single blast
        self.placeholders = placeholders or {}
        self.fmt = fmt
        self.running = False
        self.rate = 100 
        self._loop = None

    def set_rate(self, rate):
        self.rate = max(1, rate)

    def stop(self):
        self.running = False

    def run(self):
        self.running = True
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._process())
        finally:
            self._loop.close()
        self.finished_signal.emit()

    async def _process(self):
        """The sequence-aware sending loop."""
        while self.running:
            did_work = await self._process_once()
            if not did_work:
                await asyncio.sleep(2)

    async def _process_once(self) -> bool:
        """
        Process one batch of sends.
        Returns True if at least one recipient was attempted.
        """
        now = int(time.time())

        # 1) Sequence sends
        recipients = self.mgr.get_ready_recipients(now)
        if recipients:
            for row in recipients:
                if not self.running:
                    break

                seq_id = row["sequence_id"]
                current_step_num = row["current_step"]
                next_step_num = current_step_num + 1

                steps = self.seq_mgr.get_sequence_steps(seq_id)
                current_step_data = next((s for s in steps if s["step_number"] == next_step_num), None)
                if not current_step_data:
                    self.mgr.update_status(row["email"], "Completed")
                    continue

                interval = 3600.0 / self.rate
                start_time = self._loop.time()

                current_placeholders = self.placeholders.copy()
                current_placeholders["to"] = row["email"]
                current_placeholders["email"] = row["email"]
                current_placeholders["recipient_id"] = row.get("id")
                if current_step_data.get("subject"):
                    current_placeholders["subject"] = current_step_data["subject"]

                success = await self.mailer.send_one(
                    current_step_data["template_path"],
                    current_placeholders,
                    "html" if current_step_data["template_path"].endswith(".html") else "text",
                )

                if success:
                    future_step = next((s for s in steps if s["step_number"] == next_step_num + 1), None)
                    if future_step:
                        self.mgr.promote_recipient(row["email"], next_step_num, current_step_data["delay_hours"])
                    else:
                        self.mgr.update_status(row["email"], "Completed")
                else:
                    self.mgr.update_status(row["email"], f"Failed Step {next_step_num}")

                elapsed = self._loop.time() - start_time
                sleep_time = interval - elapsed
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

            return True

        # 2) Backwards-compat blast mode (no sequence assigned)
        if self.template_path:
            blast = self.mgr.get_blast_recipients()
            if blast:
                interval = 3600.0 / self.rate
                for row in blast:
                    if not self.running:
                        break
                    start_time = self._loop.time()

                    current_placeholders = self.placeholders.copy()
                    current_placeholders["to"] = row["email"]
                    current_placeholders["email"] = row["email"]
                    current_placeholders["recipient_id"] = row.get("id")

                    success = await self.mailer.send_one(
                        self.template_path,
                        current_placeholders,
                        self.fmt,
                    )
                    self.mgr.update_status(row["email"], "Sent" if success else "Failed")

                    elapsed = self._loop.time() - start_time
                    sleep_time = interval - elapsed
                    if sleep_time > 0:
                        await asyncio.sleep(sleep_time)
                return True

        return False
