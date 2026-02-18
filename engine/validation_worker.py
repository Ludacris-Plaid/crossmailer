from PyQt5 import QtCore
from engine.recipient_manager import RecipientManager

class ValidationWorker(QtCore.QThread):
    progress = QtCore.pyqtSignal(int, int) # current, total
    finished = QtCore.pyqtSignal()
    
    def __init__(self, recipient_manager):
        super().__init__()
        self.mgr = recipient_manager
        self.running = False

    def stop(self):
        self.running = False

    def run(self):
        self.running = True
        recipients = self.mgr.get_recipients() # Fetch all
        total = len(recipients)
        
        for idx, row in enumerate(recipients):
            if not self.running:
                break
                
            email = row['email']
            # 1. Syntax Check
            if not self.mgr.validate_syntax(email):
                self.mgr.update_status(email, "Invalid Syntax")
            else:
                # 2. MX Check (Can be slow, so maybe optional? We'll include it for now)
                if self.mgr.validate_mx(email):
                    self.mgr.update_status(email, "Valid")
                else:
                    self.mgr.update_status(email, "Invalid Domain")
            
            self.progress.emit(idx + 1, total)
            
        self.finished.emit()
