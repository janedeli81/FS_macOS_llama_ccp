# main.py (оновлений під повний UI flow)

import sys
from PyQt5.QtWidgets import QApplication

from UI.login_window import LoginWindow

# Якщо в майбутньому буде передача стану між вікнами,
# можна буде створити клас AppController або ContextManager

def main():
    app = QApplication(sys.argv)
    window = LoginWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
