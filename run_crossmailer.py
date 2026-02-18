import sys, os
from PyQt5 import QtWidgets

if __name__ == "__main__":
    print("Starting QApplication...")
    app = QtWidgets.QApplication(sys.argv)
    
    print("Initializing MainWindow...")
    from ui.main_window import MainWindow
    try:
        win = MainWindow()
        print("Showing window...")
        win.show()
        print("Entering main loop...")
        exit_code = app.exec_()
        print(f"Application exited with code: {exit_code}")
        with open("startup_out.log", "a") as f:
             f.write(f"\nApplication exited with code: {exit_code}\n")
        sys.exit(exit_code)
    except Exception as e:
        print(f"Caught exception: {e}")
        import traceback
        with open("startup_err.log", "w") as f:
            traceback.print_exc(file=f)
        traceback.print_exc()
