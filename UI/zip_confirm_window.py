# UI/zip_confirm_window.py

import sys
import json
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QComboBox, QScrollArea, QFrame, QMessageBox
)
from PyQt5.QtGui import QFont

from backend.config import OUTPUT_DIR


class ZipConfirmWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bevestig documenten in ZIP-bestand")
        self.setGeometry(200, 200, 750, 500)

        layout = QVBoxLayout()

        title = QLabel("Bevestig documenten in ZIP-bestand")
        title.setFont(QFont("Arial", 18))
        layout.addWidget(title)

        self.document_blocks = []

        # Scrollable content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(scroll_content)

        self.load_documents()

        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area)

        # Confirm button
        self.confirm_btn = QPushButton("✅ Dossier aanmaken")
        self.confirm_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-weight: bold;
                padding: 10px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        self.confirm_btn.clicked.connect(self.handle_confirm)
        layout.addWidget(self.confirm_btn)

        self.setLayout(layout)

    def load_documents(self):
        json_files = sorted(OUTPUT_DIR.glob("*_summary.json"))

        if not json_files:
            QMessageBox.warning(self, "Geen documenten", "Er zijn geen samenvattingen gevonden in output_summaries/")
            return

        for json_path in json_files:
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                filename = data.get("filename", json_path.stem)
                doc_type = data.get("doc_type", "UNKNOWN")
                workflow = data.get("workflow", "Standaard Samenvatting")

                block = self.create_file_block(filename, doc_type, workflow)
                self.scroll_layout.addWidget(block)

            except Exception as e:
                print(f"Fout bij laden van {json_path.name}: {e}")

    def create_file_block(self, filename, doc_type, workflow):
        block = QFrame()
        block.setFrameShape(QFrame.Box)
        block.setStyleSheet("background-color: #f5f5f5;")
        block_layout = QVBoxLayout(block)

        # Filename
        name_label = QLabel(f"📄 Naam: {filename}")
        block_layout.addWidget(name_label)

        # Document type
        doc_type_label = QLabel("Document Type:")
        doc_type_combo = QComboBox()
        doc_type_combo.addItems(["RECLASS", "TLL", "PJ", "VC", "PV", "UJD", "UNKNOWN"])
        doc_type_combo.setCurrentText(doc_type)
        block_layout.addWidget(doc_type_label)
        block_layout.addWidget(doc_type_combo)

        # Workflow
        workflow_label = QLabel("Workflow:")
        workflow_combo = QComboBox()
        workflow_combo.addItems([
            "Reclasseringsrapport",
            "TLL Generator",
            "Oude PJ rapportage",
            "VC Samenvatter",
            "PV Samenvatter",
            "Standaard Samenvatting"
        ])
        workflow_combo.setCurrentText(workflow)
        block_layout.addWidget(workflow_label)
        block_layout.addWidget(workflow_combo)

        self.document_blocks.append({
            "filename": filename,
            "doc_type_combo": doc_type_combo,
            "workflow_combo": workflow_combo
        })

        return block

    def handle_confirm(self):
        # Later this can return selected types/workflows
        print("✅ Dossier aangemaakt!")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ZipConfirmWindow()
    window.show()
    sys.exit(app.exec_())
