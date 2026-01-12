# UI/upload_window.py

import sys
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton,
    QFileDialog, QVBoxLayout, QTextEdit, QMessageBox
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt


class UploadWindow(QWidget):
    def __init__(self, username=""):
        super().__init__()
        self.setWindowTitle("Nieuw dossier maken")
        self.setGeometry(200, 200, 600, 300)

        layout = QVBoxLayout()

        # Привітання з ім’ям
        title = QLabel(f"Welkom {username}")
        title.setFont(QFont("Arial", 24))
        layout.addWidget(title)

        # Інструкція
        instructions = QLabel(
            "Hieronder staan je dossiers – selecteer om daarmee verder te gaan.\n"
            "Of maak een nieuw leeg dossier aan (waarna je bestanden één voor één kunt toevoegen als ZIP-documenten)."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet("color: gray;")
        layout.addWidget(instructions)

        # Кнопка завантаження
        self.upload_button = QPushButton("📂 Nieuw dossier maken")
        self.upload_button.setStyleSheet("""
    QPushButton {
        background-color: #4e6ef2;
        color: white;
        padding: 8px;
        font-weight: bold;
        border-radius: 4px;
    }
    QPushButton:hover {
        background-color: #3b53c9;  /* темніший синій при наведенні */
    }
     """)
        self.upload_button.clicked.connect(self.select_zip)
        layout.addWidget(self.upload_button)

        # Вивід повідомлень
        self.output_area = QTextEdit()
        self.output_area.setReadOnly(True)
        layout.addWidget(self.output_area)

        self.setLayout(layout)

    def select_zip(self):
        zip_path, _ = QFileDialog.getOpenFileName(self, "Selecteer ZIP-bestand", "", "ZIP bestanden (*.zip)")
        if zip_path:
            self.output_area.append(f"✅ Geselecteerd bestand: {zip_path}")
            QMessageBox.information(self, "Upload  voltooid", "Bestand succesvol geselecteerd en klaar voor verwerking.")


# Якщо хочеш окремо запускати:
# if __name__ == "__main__":
#     app = QApplication(sys.argv)
#     window = UploadWindow("Daan")
#     window.show()
#     sys.exit(app.exec_())
