import html
from PyQt5 import QtWidgets, QtCore, QtGui

class ChatWidget(QtWidgets.QWidget):
    message_sent = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        # Chat History
        self.history = QtWidgets.QTextBrowser()
        self.history.setOpenExternalLinks(True)
        self.history.setStyleSheet("font-size: 14px; padding: 10px;")
        layout.addWidget(self.history)

        # Input Area
        input_layout = QtWidgets.QHBoxLayout()
        self.input_field = QtWidgets.QLineEdit()
        self.input_field.setPlaceholderText("Chat with assistant...")
        self.input_field.returnPressed.connect(self._send_message)
        
        self.send_btn = QtWidgets.QPushButton("Send")
        self.send_btn.clicked.connect(self._send_message)
        
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_btn)
        layout.addLayout(input_layout)

    def _send_message(self):
        msg = self.input_field.text().strip()
        if not msg:
            return
        
        self._append_message("You", msg, "blue")
        self.input_field.clear()
        self.message_sent.emit(msg)

    def append_response(self, text):
        self._append_message("Assistant", text, "red")

    def _append_message(self, sender, text, color):
        sender_esc = html.escape(str(sender))
        text_esc = html.escape(str(text))
        formatted = f"<div style='margin-bottom: 5px;'><b style='color:{color};'>{sender_esc}:</b> {text_esc}</div>"
        self.history.append(formatted)
