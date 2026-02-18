import os
import sys
import unittest

# Headless-friendly Qt backend
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtWidgets, QtCore
from PyQt5.QtTest import QTest

# Ensure one QApplication exists
app = QtWidgets.QApplication.instance()
if not app:
    app = QtWidgets.QApplication(sys.argv)

from ui.chat_widget import ChatWidget
from ui.ai_tab import AITab

class TestUIInteractions(unittest.TestCase):
    
    def test_chat_widget(self):
        """Test sending messages in ChatWidget"""
        widget = ChatWidget()
        
        # Test signal emission
        received_msgs = []
        widget.message_sent.connect(received_msgs.append)
        
        # Simulate typing and clicking
        widget.input_field.setText("Hello AI")
        QTest.mouseClick(widget.send_btn, QtCore.Qt.LeftButton)
        
        self.assertEqual(received_msgs, ["Hello AI"])
        self.assertEqual(widget.input_field.text(), "") # Should clear
        
        # Test appending response
        widget.append_response("Hello User")
        self.assertIn("Hello User", widget.history.toHtml())

    def test_ai_tab_mode_switching(self):
        """Test switching between Generator and Chat in AITab"""
        tab = AITab()
        
        # Check tabs exist
        self.assertEqual(tab.mode_tabs.count(), 2)
        self.assertEqual(tab.mode_tabs.tabText(0), "Campaign Generator")
        self.assertEqual(tab.mode_tabs.tabText(1), "Chat")
        
        # Switch to chat
        tab.mode_tabs.setCurrentIndex(1)
        self.assertEqual(tab.mode_tabs.currentIndex(), 1)

if __name__ == '__main__':
    unittest.main()
