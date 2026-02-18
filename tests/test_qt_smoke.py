import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtWidgets


class TestQtSmoke(unittest.TestCase):
    def test_qapplication_creates(self):
        app = QtWidgets.QApplication.instance()
        if not app:
            app = QtWidgets.QApplication(sys.argv)
        w = QtWidgets.QWidget()
        w.setWindowTitle("Smoke")
        w.show()
        self.assertTrue(w.isVisible())


if __name__ == "__main__":
    unittest.main()

