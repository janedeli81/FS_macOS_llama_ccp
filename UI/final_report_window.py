import sys
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton,
    QVBoxLayout, QTextEdit, QMessageBox, QFileDialog
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import QTimer

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4

from backend.config import OUTPUT_DIR, FINAL_REPORT_PATH, FINAL_REPORT_PDF_PATH


class FinalReportWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Concept Rapport Generatie")
        self.setGeometry(250, 250, 750, 450)

        self.layout = QVBoxLayout()

        self.title = QLabel("Rapport wordt gegenereerd...")
        self.title.setFont(QFont("Arial", 20))
        self.layout.addWidget(self.title)

        self.info = QLabel("Alle samenvattingen worden samengevoegd tot één rapport.")
        self.layout.addWidget(self.info)

        self.result_box = QTextEdit()
        self.result_box.setReadOnly(True)
        self.result_box.hide()
        self.layout.addWidget(self.result_box)

        self.view_button = QPushButton("Bekijk gegenereerd rapport")
        self.view_button.setEnabled(False)
        self.view_button.clicked.connect(self.open_generated_file)
        self.layout.addWidget(self.view_button)

        self.export_button = QPushButton("Download rapport als PDF")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.save_pdf_copy)
        self.layout.addWidget(self.export_button)

        self.setLayout(self.layout)

        QTimer.singleShot(2000, self.generate_final_report)

    def generate_final_report(self):
        OUTPUT_DIR.mkdir(exist_ok=True)
        summary_files = sorted(OUTPUT_DIR.glob("*_summary.txt"))

        if not summary_files:
            self.result_box.setText("⚠️ Geen samenvattingen gevonden.")
            self.result_box.show()
            self.title.setText("⚠️ Niets om te genereren")
            return

        final_parts = []
        for file in summary_files:
            try:
                text = file.read_text(encoding="utf-8").strip()
                part = f"--- {file.name} ---\n{text}\n"
                final_parts.append(part)
            except Exception as e:
                final_parts.append(f"--- {file.name} ---\n⚠️ Kon niet lezen: {e}\n")

        combined_text = "\n\n".join(final_parts)

        # Save .txt
        FINAL_REPORT_PATH.write_text(combined_text, encoding="utf-8")
        self.generated_file_path = FINAL_REPORT_PATH

        # Save .pdf
        self.create_pdf_report(combined_text, FINAL_REPORT_PDF_PATH)
        self.generated_pdf_path = FINAL_REPORT_PDF_PATH

        self.result_box.setText(combined_text)
        self.result_box.show()
        self.title.setText("✅ Rapport succesvol gegenereerd!")
        self.view_button.setEnabled(True)
        self.export_button.setEnabled(True)

    def create_pdf_report(self, text: str, pdf_path: Path):
        doc = SimpleDocTemplate(str(pdf_path), pagesize=A4)
        styles = getSampleStyleSheet()
        flowables = []

        for part in text.split("\n\n"):
            flowables.append(Paragraph(part.replace("\n", "<br/>"), styles["Normal"]))
            flowables.append(Spacer(1, 12))

        doc.build(flowables)

    def open_generated_file(self):
        if hasattr(self, "generated_file_path") and self.generated_file_path.exists():
            try:
                content = self.generated_file_path.read_text(encoding="utf-8")
                dlg = QTextEdit()
                dlg.setReadOnly(True)
                dlg.setPlainText(content)
                dlg.setWindowTitle("Bekijk rapport")
                dlg.resize(700, 600)
                dlg.show()
                self._viewer = dlg
            except Exception as e:
                QMessageBox.warning(self, "Fout", f"Kan bestand niet openen:\n{e}")
        else:
            QMessageBox.warning(self, "Niet gevonden", "Geen rapportbestand beschikbaar.")

    def save_pdf_copy(self):
        if not hasattr(self, "generated_pdf_path") or not self.generated_pdf_path.exists():
            QMessageBox.warning(self, "Niet gevonden", "Er is geen PDF om te downloaden.")
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Bewaar PDF rapport",
            "rapport.pdf",
            "PDF-bestanden (*.pdf)"
        )
        if save_path:
            try:
                Path(save_path).write_bytes(self.generated_pdf_path.read_bytes())
                QMessageBox.information(self, "Opgeslagen", "PDF is succesvol opgeslagen.")
            except Exception as e:
                QMessageBox.critical(self, "Fout", f"Kan PDF niet opslaan:\n{e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FinalReportWindow()
    window.show()
    sys.exit(app.exec_())
