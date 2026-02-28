# UI/final_report_window.py

import sys
from pathlib import Path
from typing import Optional, List

from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QTextEdit,
    QMessageBox,
    QFileDialog,
    QFrame,
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import QTimer, Qt

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4

from backend.state import AppState, DOC_STATUS_SUMMARIZED
from UI.ui_theme import apply_window_theme


class FinalReportWindow(QWidget):
    """
    Final report generator:
    - reads summaries ONLY from the current case
    - writes report into case/final/
    """

    def __init__(self, state: Optional[AppState] = None):
        super().__init__()
        self.state = state

        self.setWindowTitle("Concept rapport")
        self.setMinimumSize(1100, 720)

        self._build_ui()
        apply_window_theme(self)

        # Generate automatically after UI is shown
        QTimer.singleShot(250, self.generate_final_report)

    def _build_ui(self) -> None:
        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        wrapper = QVBoxLayout()
        wrapper.setContentsMargins(26, 22, 26, 26)
        wrapper.setSpacing(0)

        self.page = QFrame()
        self.page.setObjectName("page")

        page_layout = QVBoxLayout(self.page)
        page_layout.setContentsMargins(60, 40, 60, 44)
        page_layout.setSpacing(12)

        title = QLabel("Concept rapport")
        title.setObjectName("title")
        title.setFont(QFont("Segoe UI", 28, QFont.Bold))
        page_layout.addWidget(title)

        self.info = QLabel("Samenvattingen worden samengevoegd tot één rapport.")
        self.info.setObjectName("fieldLabel")
        self.info.setFont(QFont("Segoe UI", 12))
        page_layout.addWidget(self.info)

        self.result_box = QTextEdit()
        self.result_box.setObjectName("input")
        self.result_box.setReadOnly(True)
        page_layout.addWidget(self.result_box, 1)

        btn_row = QVBoxLayout()
        btn_row.setSpacing(10)

        self.view_button = QPushButton("Bekijk rapport")
        self.view_button.setObjectName("secondaryButton")
        self.view_button.setEnabled(False)
        self.view_button.clicked.connect(self.open_generated_text)
        btn_row.addWidget(self.view_button)

        self.export_button = QPushButton("Opslaan als PDF")
        self.export_button.setObjectName("primaryButton")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.save_pdf_copy)
        btn_row.addWidget(self.export_button)

        page_layout.addLayout(btn_row)

        wrapper.addWidget(self.page)
        container = QWidget()
        container.setLayout(wrapper)

        root.addWidget(container)
        self.setLayout(root)

    def _case_paths(self) -> dict:
        if self.state is None or self.state.case.case_dir is None:
            raise RuntimeError("Case is not initialized.")

        final_dir = self.state.case.final_dir or (Path(self.state.case.case_dir) / "final")
        final_dir.mkdir(parents=True, exist_ok=True)

        pdf_path = self.state.case.final_report_path or (final_dir / "final_report.pdf")
        txt_path = final_dir / "final_report.txt"

        return {"final_dir": final_dir, "pdf": Path(pdf_path), "txt": Path(txt_path)}

    def generate_final_report(self) -> None:
        if self.state is None:
            self.result_box.setPlainText("Geen case geladen.")
            return

        paths = self._case_paths()

        summarized_docs = [d for d in self.state.documents if d.selected and d.status == DOC_STATUS_SUMMARIZED]
        if not summarized_docs:
            self.result_box.setPlainText("Geen samenvattingen gevonden voor deze case.")
            return

        # Build report in the same order as documents list
        parts: List[str] = []
        for d in summarized_docs:
            if d.summary and d.summary.txt_path and Path(d.summary.txt_path).exists():
                txt_path = Path(d.summary.txt_path)
            else:
                # Fallback convention
                summaries_dir = self.state.case.summaries_dir
                if summaries_dir is None:
                    continue
                stem = Path(d.source_path).stem
                txt_path = Path(summaries_dir) / f"{stem}_summary.txt"

            header = f"--- {d.original_name} ({d.final_type()}) ---"
            try:
                text = txt_path.read_text(encoding="utf-8", errors="ignore").strip()
                parts.append(f"{header}\n{text}\n")
            except Exception as e:
                parts.append(f"{header}\n[Could not read summary: {e}]\n")

        combined_text = "\n\n".join(parts).strip()

        # Save TXT
        paths["txt"].write_text(combined_text, encoding="utf-8")

        # Save PDF
        self.create_pdf_report(combined_text, paths["pdf"])

        self.generated_txt_path = paths["txt"]
        self.generated_pdf_path = paths["pdf"]

        self.result_box.setPlainText(combined_text)
        self.view_button.setEnabled(True)
        self.export_button.setEnabled(True)

    def create_pdf_report(self, text: str, pdf_path: Path) -> None:
        doc = SimpleDocTemplate(str(pdf_path), pagesize=A4)
        styles = getSampleStyleSheet()
        flowables = []

        # Split into paragraphs to keep PDF readable
        for part in text.split("\n\n"):
            safe = part.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            safe = safe.replace("\n", "<br/>")
            flowables.append(Paragraph(safe, styles["Normal"]))
            flowables.append(Spacer(1, 12))

        doc.build(flowables)

    def open_generated_text(self) -> None:
        if not hasattr(self, "generated_txt_path") or not Path(self.generated_txt_path).exists():
            QMessageBox.warning(self, "Niet gevonden", "Geen rapportbestand beschikbaar.")
            return

        try:
            content = Path(self.generated_txt_path).read_text(encoding="utf-8", errors="ignore")
            dlg = QTextEdit()
            dlg.setReadOnly(True)
            dlg.setPlainText(content)
            dlg.setWindowTitle("Bekijk rapport")
            dlg.resize(900, 700)
            dlg.show()
            self._viewer = dlg
        except Exception as e:
            QMessageBox.warning(self, "Fout", f"Kan rapport niet openen:\n{e}")

    def save_pdf_copy(self) -> None:
        if not hasattr(self, "generated_pdf_path") or not Path(self.generated_pdf_path).exists():
            QMessageBox.warning(self, "Niet gevonden", "Er is geen PDF om op te slaan.")
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Bewaar PDF rapport",
            "rapport.pdf",
            "PDF-bestanden (*.pdf)"
        )
        if not save_path:
            return

        try:
            Path(save_path).write_bytes(Path(self.generated_pdf_path).read_bytes())
            QMessageBox.information(self, "Opgeslagen", "PDF is succesvol opgeslagen.")
        except Exception as e:
            QMessageBox.critical(self, "Fout", f"Kan PDF niet opslaan:\n{e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FinalReportWindow()
    window.show()
    sys.exit(app.exec_())
