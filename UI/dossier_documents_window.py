# UI/dossier_documents_window.py

import sys
import shutil
from pathlib import Path
from typing import Optional, Dict

from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QDialog,
    QTextEdit,
    QFileDialog,
    QProgressBar,
    QFrame,
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt, QDateTime, QTimer

from backend.state import (
    AppState,
    DOC_STATUS_EXTRACTED,
    DOC_STATUS_DETECTED,
    DOC_STATUS_QUEUED,
    DOC_STATUS_SUMMARIZING,
    DOC_STATUS_SUMMARIZED,
    DOC_STATUS_ERROR,
    DOC_STATUS_SKIPPED,
)
from backend.summarizer_worker import SummarizationWorker
from UI.ui_theme import apply_window_theme
from UI.final_report_window import FinalReportWindow


class DossierDocumentsWindow(QWidget):
    """
    Summaries Table:
    - shows documents for current case
    - supports manual start/resume summarization
    - protects against resume clicks during active summarization
    """

    def __init__(self, state: Optional[AppState] = None):
        super().__init__()
        self.state = state

        self.setWindowTitle("Samenvattingen")
        self.setMinimumSize(1100, 720)
        self._center_on_screen()

        self.worker: Optional[SummarizationWorker] = None
        self.current_doc_id: Optional[str] = None

        self.row_by_doc_id: Dict[str, int] = {}

        self._build_ui()
        apply_window_theme(self)

        # Normalize state on open (fix interrupted runs / old manifests)
        self._normalize_resume_state(reset_summarizing=True)

        self.load_table()

        # Auto-start on open (safe), user can always resume manually if needed.
        QTimer.singleShot(250, self.start_auto_summarization)

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

        title = QLabel("Samenvattingen per document")
        title.setObjectName("title")
        title.setFont(QFont("Segoe UI", 28, QFont.Bold))
        page_layout.addWidget(title)

        self.subtitle = QLabel("")
        self.subtitle.setObjectName("fieldLabel")
        self.subtitle.setFont(QFont("Segoe UI", 12))
        self.subtitle.setWordWrap(True)
        page_layout.addWidget(self.subtitle)

        self.progress = QProgressBar()
        self.progress.setMinimum(0)
        self.progress.setMaximum(100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(26)
        page_layout.addWidget(self.progress)

        # Control row (manual start/resume)
        control_row = QHBoxLayout()
        control_row.setSpacing(12)

        self.resume_btn = QPushButton("Start / Hervat samenvattingen")
        self.resume_btn.setObjectName("secondaryButton")
        self.resume_btn.setCursor(Qt.PointingHandCursor)
        self.resume_btn.clicked.connect(self.on_resume_clicked)

        control_row.addWidget(self.resume_btn, alignment=Qt.AlignLeft)
        control_row.addStretch(1)

        page_layout.addLayout(control_row)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Bestandsnaam",
            "Type",
            "Status",
            "Datum",
            "Bekijk",
            "Export TXT",
            "Export JSON",
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        page_layout.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self.back_btn = QPushButton("Terug")
        self.back_btn.setObjectName("secondaryButton")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.clicked.connect(self.go_back)

        self.report_btn = QPushButton("Concept rapport genereren")
        self.report_btn.setObjectName("primaryButton")
        self.report_btn.setCursor(Qt.PointingHandCursor)
        self.report_btn.clicked.connect(self.open_final_report)

        btn_row.addWidget(self.back_btn, alignment=Qt.AlignLeft)
        btn_row.addStretch(1)
        btn_row.addWidget(self.report_btn, alignment=Qt.AlignRight)

        page_layout.addLayout(btn_row)

        wrapper.addWidget(self.page)

        container = QWidget()
        container.setLayout(wrapper)

        root.addWidget(container)
        self.setLayout(root)

    def _is_worker_running(self) -> bool:
        try:
            return self.worker is not None and hasattr(self.worker, "isRunning") and self.worker.isRunning()
        except Exception:
            return False

    # -------------------------
    # Resume / normalize logic
    # -------------------------
    def _normalize_resume_state(self, reset_summarizing: bool = True) -> None:
        """
        Normalize case state.

        reset_summarizing=True  -> when opening a case: treat old 'summarizing' as interrupted -> requeue.
        reset_summarizing=False -> when user clicks Resume during the same session: do NOT touch 'summarizing'.
        """
        if self.state is None:
            return

        changed = False

        for doc in self.state.documents:
            # Ensure unselected documents stay skipped
            if not doc.selected and doc.status != DOC_STATUS_SKIPPED:
                doc.status = DOC_STATUS_SKIPPED
                doc.error_message = ""
                changed = True
                continue

            # If summary files exist, mark summarized
            try:
                paths = self._summary_paths_for_doc(doc)
                has_any = paths["txt"].exists() or paths["json"].exists()
            except Exception:
                has_any = False

            if doc.selected and has_any and doc.status != DOC_STATUS_SUMMARIZED:
                doc.status = DOC_STATUS_SUMMARIZED
                doc.error_message = ""
                changed = True
                continue

            # If previous session was interrupted during summarizing -> back to queued
            if doc.selected and doc.status == DOC_STATUS_SUMMARIZING:
                if reset_summarizing:
                    doc.status = DOC_STATUS_QUEUED
                    doc.error_message = ""
                    changed = True
                continue

            # If selected doc is in an old/neutral state -> queue it
            if doc.selected and doc.status in (DOC_STATUS_DETECTED, DOC_STATUS_EXTRACTED):
                doc.status = DOC_STATUS_QUEUED
                changed = True
                continue

        if changed:
            self.state.save_manifest()

    def on_resume_clicked(self) -> None:
        if self.state is None:
            return

        # Prevent breaking the current summarization run
        if self._is_worker_running():
            QMessageBox.information(
                self,
                "Info",
                "Samenvattingen zijn al bezig. Wacht tot het huidige document klaar is."
            )
            return

        # Normalize without touching 'summarizing' (safe) and reload UI
        self._normalize_resume_state(reset_summarizing=False)
        self.load_table()

        # Start/resume summarization
        self.start_auto_summarization()

    # -------------------------
    # UI helpers
    # -------------------------
    def _update_subtitle(self) -> None:
        if self.state is None:
            self.subtitle.setText("Geen case geladen.")
            return

        total = len(self.state.documents)
        queued = len([d for d in self.state.documents if d.status == DOC_STATUS_QUEUED])
        running = len([d for d in self.state.documents if d.status == DOC_STATUS_SUMMARIZING])
        done = len([d for d in self.state.documents if d.status == DOC_STATUS_SUMMARIZED])
        err = len([d for d in self.state.documents if d.status == DOC_STATUS_ERROR])

        self.subtitle.setText(
            f"Case: {self.state.case.case_id} • Documenten: {total} • "
            f"Queued: {queued} • Running: {running} • Done: {done} • Errors: {err}"
        )

    def load_table(self) -> None:
        if self.state is None:
            QMessageBox.warning(self, "Fout", "Geen AppState gevonden.")
            return

        self.row_by_doc_id = {}

        self.table.setRowCount(len(self.state.documents))
        for row, doc in enumerate(self.state.documents):
            self.row_by_doc_id[doc.doc_id] = row

            filename_item = QTableWidgetItem(doc.original_name)
            type_item = QTableWidgetItem(doc.final_type())
            status_item = QTableWidgetItem(doc.status)

            dt = QDateTime.currentDateTime()
            if doc.summary and doc.summary.updated_at:
                try:
                    dt = QDateTime.fromString(doc.summary.updated_at, Qt.ISODate)
                except Exception:
                    pass

            date_item = QTableWidgetItem(dt.toString("dd MMM yyyy HH:mm"))

            self.table.setItem(row, 0, filename_item)
            self.table.setItem(row, 1, type_item)
            self.table.setItem(row, 2, status_item)
            self.table.setItem(row, 3, date_item)

            # Buttons
            view_btn = QPushButton("Bekijk")
            view_btn.setObjectName("secondaryButton")
            view_btn.clicked.connect(lambda _, did=doc.doc_id: self.view_summary(did))

            export_txt_btn = QPushButton("TXT")
            export_txt_btn.setObjectName("secondaryButton")
            export_txt_btn.clicked.connect(lambda _, did=doc.doc_id: self.export_summary(did, "txt"))

            export_json_btn = QPushButton("JSON")
            export_json_btn.setObjectName("secondaryButton")
            export_json_btn.clicked.connect(lambda _, did=doc.doc_id: self.export_summary(did, "json"))

            self.table.setCellWidget(row, 4, view_btn)
            self.table.setCellWidget(row, 5, export_txt_btn)
            self.table.setCellWidget(row, 6, export_json_btn)

            self._refresh_row_buttons(doc.doc_id)

        self._update_subtitle()
        self._update_progress_bar()

    def _update_progress_bar(self) -> None:
        if self.state is None:
            self.progress.setValue(0)
            return

        selected = [d for d in self.state.documents if d.selected]
        if not selected:
            self.progress.setValue(0)
            return

        done = len([d for d in selected if d.status == DOC_STATUS_SUMMARIZED])
        pct = int((done / len(selected)) * 100)
        self.progress.setValue(max(0, min(100, pct)))

    def _summary_paths_for_doc(self, doc) -> Dict[str, Path]:
        if self.state is None or self.state.case.summaries_dir is None:
            raise RuntimeError("Case summaries_dir is not initialized.")

        stem = Path(doc.source_path).stem
        json_path = Path(self.state.case.summaries_dir) / f"{stem}_summary.json"
        txt_path = Path(self.state.case.summaries_dir) / f"{stem}_summary.txt"
        return {"json": json_path, "txt": txt_path}

    def _refresh_row_buttons(self, doc_id: str) -> None:
        if self.state is None:
            return

        doc = next((d for d in self.state.documents if d.doc_id == doc_id), None)
        if doc is None:
            return

        row = self.row_by_doc_id.get(doc_id)
        if row is None:
            return

        paths = self._summary_paths_for_doc(doc)
        has_txt = paths["txt"].exists()
        has_json = paths["json"].exists()

        view_btn = self.table.cellWidget(row, 4)
        export_txt_btn = self.table.cellWidget(row, 5)
        export_json_btn = self.table.cellWidget(row, 6)

        if view_btn:
            view_btn.setEnabled(has_txt)
        if export_txt_btn:
            export_txt_btn.setEnabled(has_txt)
        if export_json_btn:
            export_json_btn.setEnabled(has_json)

    # -------------------------
    # Summarization pipeline
    # -------------------------
    def start_auto_summarization(self) -> None:
        if self.state is None:
            return

        # If a worker is already running, do nothing.
        if self._is_worker_running():
            self.resume_btn.setEnabled(False)
            return

        next_doc = next((d for d in self.state.documents if d.status == DOC_STATUS_QUEUED), None)
        if next_doc is None:
            self.resume_btn.setEnabled(True)
            self._update_subtitle()
            self._update_progress_bar()
            return

        self._start_summarization_for_doc(next_doc.doc_id)

    def _start_summarization_for_doc(self, doc_id: str) -> None:
        if self.state is None or self.state.case.summaries_dir is None or self.state.case.extracted_dir is None:
            QMessageBox.critical(self, "Fout", "Case directories are not initialized.")
            return

        doc = next((d for d in self.state.documents if d.doc_id == doc_id), None)
        if doc is None:
            return

        self.resume_btn.setEnabled(False)

        self.current_doc_id = doc_id
        doc.status = DOC_STATUS_SUMMARIZING
        self.state.save_manifest()

        self._set_status_in_table(doc_id, DOC_STATUS_SUMMARIZING)
        self._update_subtitle()

        doc_type_code = doc.final_type() or "UNKNOWN"

        self.worker = SummarizationWorker(
            Path(doc.source_path),
            Path(self.state.case.summaries_dir),
            Path(self.state.case.extracted_dir),
            doc_type=doc_type_code,
            text=None,
        )
        self.worker.progress.connect(self._on_worker_progress)
        self.worker.error.connect(self._on_worker_error)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _on_worker_progress(self, message: str) -> None:
        if not message:
            return
        msg = message.strip()
        if len(msg) > 140:
            msg = msg[:140] + "..."
        # Keep first line (counters) + progress message
        first_line = self.subtitle.text().split("\n")[0]
        self.subtitle.setText(first_line + "\n" + msg)

    def _on_worker_error(self, message: str) -> None:
        if self.state is None or self.current_doc_id is None:
            return

        doc = next((d for d in self.state.documents if d.doc_id == self.current_doc_id), None)
        if doc is None:
            return

        doc.status = DOC_STATUS_ERROR
        doc.error_message = str(message)
        self.state.save_manifest()

        self._set_status_in_table(doc.doc_id, DOC_STATUS_ERROR)
        self._update_subtitle()

        self.current_doc_id = None

        # Continue with next queued doc
        QTimer.singleShot(150, self.start_auto_summarization)

    def _on_worker_finished(self, result: dict) -> None:
        if self.state is None or self.current_doc_id is None:
            return

        doc = next((d for d in self.state.documents if d.doc_id == self.current_doc_id), None)
        if doc is None:
            return

        paths = self._summary_paths_for_doc(doc)

        doc.status = DOC_STATUS_SUMMARIZED
        doc.summary.txt_path = paths["txt"]
        doc.summary.json_path = paths["json"]
        doc.summary.updated_at = QDateTime.currentDateTime().toString(Qt.ISODate)
        doc.error_message = ""
        self.state.save_manifest()

        self._set_status_in_table(doc.doc_id, DOC_STATUS_SUMMARIZED)
        self._refresh_row_buttons(doc.doc_id)
        self._update_subtitle()
        self._update_progress_bar()

        self.current_doc_id = None

        # Continue with next queued doc
        QTimer.singleShot(150, self.start_auto_summarization)

    def _set_status_in_table(self, doc_id: str, status: str) -> None:
        row = self.row_by_doc_id.get(doc_id)
        if row is None:
            return
        self.table.setItem(row, 2, QTableWidgetItem(status))
        self.table.setItem(row, 3, QTableWidgetItem(QDateTime.currentDateTime().toString("dd MMM yyyy HH:mm")))

    # -------------------------
    # Actions
    # -------------------------
    def view_summary(self, doc_id: str) -> None:
        if self.state is None:
            return

        doc = next((d for d in self.state.documents if d.doc_id == doc_id), None)
        if doc is None:
            return

        paths = self._summary_paths_for_doc(doc)
        txt_path = paths["txt"]

        if not txt_path.exists():
            QMessageBox.warning(self, "Niet gevonden", "Geen TXT-samenvatting gevonden.")
            return

        try:
            content = txt_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            QMessageBox.critical(self, "Fout", f"Kan samenvatting niet lezen:\n{e}")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Samenvatting – {doc.original_name}")
        dlg.resize(900, 700)

        layout = QVBoxLayout(dlg)

        editor = QTextEdit()
        editor.setObjectName("input")
        editor.setReadOnly(True)
        editor.setPlainText(content)
        layout.addWidget(editor)

        close_btn = QPushButton("Sluiten")
        close_btn.setObjectName("secondaryButton")
        close_btn.clicked.connect(dlg.close)
        layout.addWidget(close_btn)

        dlg.setLayout(layout)
        dlg.exec_()

    def export_summary(self, doc_id: str, fmt: str) -> None:
        if self.state is None:
            return

        doc = next((d for d in self.state.documents if d.doc_id == doc_id), None)
        if doc is None:
            return

        paths = self._summary_paths_for_doc(doc)
        src = paths.get(fmt)
        if src is None or not src.exists():
            QMessageBox.warning(self, "Niet gevonden", f"Geen {fmt.upper()}-bestand gevonden.")
            return

        default_name = src.name
        filter_str = "Text (*.txt)" if fmt == "txt" else "JSON (*.json)"

        dst, _ = QFileDialog.getSaveFileName(self, "Opslaan", default_name, filter_str)
        if not dst:
            return

        try:
            shutil.copyfile(src, Path(dst))
            QMessageBox.information(self, "Opgeslagen", f"Bestand opgeslagen:\n{dst}")
        except Exception as e:
            QMessageBox.critical(self, "Fout", f"Kan bestand niet opslaan:\n{e}")

    def open_final_report(self) -> None:
        if self.state is None:
            QMessageBox.warning(self, "Fout", "Geen AppState gevonden.")
            return

        self.close()
        self.report_window = FinalReportWindow(state=self.state)
        self.report_window.show()

    def go_back(self) -> None:
        from UI.document_overview_window import DocumentOverviewWindow

        self.close()
        self.prev = DocumentOverviewWindow(state=self.state)
        self.prev.show()

    def closeEvent(self, event):
        self._stop_worker()
        event.accept()

    def _stop_worker(self) -> None:
        t = self.worker
        if t is None:
            return
        try:
            if hasattr(t, "isRunning") and t.isRunning():
                if hasattr(t, "requestInterruption"):
                    t.requestInterruption()
                if hasattr(t, "quit"):
                    t.quit()
                if hasattr(t, "wait"):
                    t.wait(3000)
        except Exception:
            pass

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        rect = screen.availableGeometry()
        x = rect.x() + (rect.width() - self.width()) // 2
        y = rect.y() + (rect.height() - self.height()) // 2
        self.move(x, y)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DossierDocumentsWindow()
    window.show()
    sys.exit(app.exec_())
