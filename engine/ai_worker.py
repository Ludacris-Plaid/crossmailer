from PyQt5 import QtCore
import threading
from engine.ai_brain import AIBrain

class AIWorker(QtCore.QThread):
    """
    Background worker for AI tasks to keep UI responsive.
    """
    download_finished = QtCore.pyqtSignal(bool)
    generation_finished = QtCore.pyqtSignal(dict)
    chat_finished = QtCore.pyqtSignal(str)
    error_occurred = QtCore.pyqtSignal(str)
    
    def __init__(self, model_config=None):
        super().__init__()
        self.brain = AIBrain(model_config)
        self.action = None
        self.params = {}

    def download_model(self):
        self.action = "download"
        self.start()

    def generate(self, topic, audience, tone):
        self.action = "generate"
        self.params = {"topic": topic, "audience": audience, "tone": tone}
        self.start()

    def chat(self, message):
        self.action = "chat"
        self.params = {"message": message}
        self.start()

    def run(self):
        try:
            if self.action == "download":
                success = self.brain.download_model()
                self.download_finished.emit(success)
            
            elif self.action == "generate":
                if not self.brain.is_model_downloaded():
                    self.error_occurred.emit("Model file not found. Please download/select it first.")
                    return
                    
                result = self.brain.generate_email_campaign(
                    self.params["topic"],
                    self.params["audience"],
                    self.params["tone"]
                )
                self.generation_finished.emit(result)

            elif self.action == "chat":
                # Ensure model is loaded/ready (logic inside chat() handles it)
                reply = self.brain.chat(self.params["message"])
                self.chat_finished.emit(reply)
                
        except Exception as e:
            self.error_occurred.emit(str(e))
