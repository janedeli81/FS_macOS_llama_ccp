import sys
import json
from pathlib import Path
from backend.config import OUTPUT_DIR

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton,
    QVBoxLayout, QFormLayout, QLineEdit, QHBoxLayout, QMessageBox
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import QDate


class DossierDetailWindow(QWidget):
    def __init__(self, documents=None):
        super().__init__()
        self.setWindowTitle("Dossier Details")
        self.setGeometry(200, 200, 700, 500)

        self.documents = documents or []

        layout = QVBoxLayout()

        title = QLabel("Dossier Details")
        title.setFont(QFont("Arial", 20))
        layout.addWidget(title)

        dossier_name = f"Dossier_{QDate.currentDate().toString('yyyyMMdd')}"
        self.name_label = QLabel(f"Naam dossier: {dossier_name}")
        self.date_label = QLabel(f"Aangemaakt op: {QDate.currentDate().toString('dd-MM-yyyy')}")
        self.status_label = QLabel("Status: Aangemaakt")
        self.count_label = QLabel(f"Aantal documenten: {len(self.documents)}")

        layout.addWidget(self.name_label)
        layout.addWidget(self.date_label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.count_label)

        self.details_layout = QFormLayout()
        self.fields = {}

        # Стартові значення (пусті)
        fields_data = {
            "Verdachte": "",
            "Geboortedatum": "",
            "Delict": "",
            "Advies": "",
            "Risico": ""
        }

        # Спроба заповнити з meta JSON (першого документа)
        meta = self.extract_meta_from_first_json()

        for key in fields_data:
            value = meta.get(key.lower(), "")
            line_edit = QLineEdit(value)
            line_edit.setReadOnly(True)
            self.fields[key] = line_edit
            self.details_layout.addRow(QLabel(key + ":"), line_edit)

        layout.addLayout(self.details_layout)


        button_layout = QHBoxLayout()

        self.edit_btn = QPushButton("Details handmatig aanpassen")
        self.edit_btn.clicked.connect(self.toggle_edit)

        self.extract_btn = QPushButton("Details uit bestand lezen (Beta)")
        self.extract_btn.clicked.connect(self.open_documents_window)

        self.delete_btn = QPushButton("Dossier verwijderen")
        self.delete_btn.clicked.connect(self.confirm_delete)

        for btn in [self.edit_btn, self.extract_btn, self.delete_btn]:
            self.style_button(btn)
            button_layout.addWidget(btn)

        layout.addLayout(button_layout)
        self.setLayout(layout)
        self.edit_mode = False

    def extract_meta_from_first_json(self):
        """
        Повертає словник meta з першого summary.json
        """

        if not self.documents:
            return {}

        first_filename = self.documents[0]["filename"]
        stem = Path(first_filename).stem.replace("_summary", "")
        json_path = OUTPUT_DIR / f"{stem}_summary.json"

        if json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("meta", {})
            except Exception as e:
                print(f"❌ Kan meta niet laden uit {json_path.name}: {e}")
        return {}

    def style_button(self, button):
        button.setStyleSheet("""
            QPushButton {
                background-color: #4e6ef2;
                color: white;
                font-weight: bold;
                padding: 8px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #3b53c9;
            }
        """)

    def toggle_edit(self):
        self.edit_mode = not self.edit_mode
        for field in self.fields.values():
            field.setReadOnly(not self.edit_mode)

        if self.edit_mode:
            self.edit_btn.setText("✅ Opslaan")
        else:
            self.edit_btn.setText("Details handmatig aanpassen")
            QMessageBox.information(self, "Opgeslagen", "Wijzigingen zijn opgeslagen.")

    def open_documents_window(self):
        from UI.dossier_documents_window import DossierDocumentsWindow
        self.docs_window = DossierDocumentsWindow(documents=self.documents)
        self.docs_window.show()
        self.close()

    def confirm_delete(self):
        reply = QMessageBox.question(
            self, "Bevestiging", "Weet je zeker dat je dit dossier wilt verwijderen?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            QMessageBox.information(self, "Verwijderd", "Dossier is verwijderd.")
            self.close()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DossierDetailWindow()
    window.show()
    sys.exit(app.exec_())
