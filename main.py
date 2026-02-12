# main.py

import sys
from PyQt5.QtWidgets import QApplication

from UI.login_window import LoginWindow

def main():
    app = QApplication(sys.argv)

    # Cleanup decrypted runtime files (best-effort).
    try:
        from backend.model_manager import cleanup_runtime_files
        cleanup_runtime_files(max_age_hours=24)
        app.aboutToQuit.connect(lambda: cleanup_runtime_files(max_age_hours=0))
    except Exception:
        pass

    window = LoginWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
