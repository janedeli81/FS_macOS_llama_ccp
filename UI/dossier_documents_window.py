# UI/dossier_documents_window.py

import sys
import json
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
    def __init__(self, state: Optional[AppState] = None, api_client=None):
        super().__init__()
        self.state = state
        self.api_client = api_client  # Store API client

        self.setWindowTitle("Samenvattingen")
        self.setMinimumSize(1100, 780)
        self._center_on_screen()

        self.worker: Optional[SummarizationWorker] = None
        self.current_doc_id: Optional[str] = None
        self.row_by_doc_id: Dict[str, int] = {}

        self._build_ui()
        apply_window_theme(self)

        self._normalize_resume_state(reset_summarizing=True)
        self.load_table()

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

        # NEW: visible log panel
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setPlaceholderText("Log verschijnt hier tijdens samenvatten…")
        self.log_box.setFixedHeight(140)
        page_layout.addWidget(self.log_box)

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

    def _append_log(self, msg: str) -> None:
        if not msg:
            return
        # Keep log bounded
        current = self.log_box.toPlainText()
        lines = current.splitlines() if current else []
        lines.append(msg)
        if len(lines) > 600:
            lines = lines[-600:]
        self.log_box.setPlainText("\n".join(lines))
        self.log_box.verticalScrollBar().setValue(self.log_box.verticalScrollBar().maximum())

    def _is_worker_running(self) -> bool:
        try:
            return self.worker is not None and hasattr(self.worker, "isRunning") and self.worker.isRunning()
        except Exception:
            return False

    def _read_summary_doc_type(self, doc) -> Optional[str]:
        try:
            paths = self._summary_paths_for_doc(doc)
            json_path = paths.get("json")
            if json_path is None or not json_path.exists():
                return None

            data = json.loads(json_path.read_text(encoding="utf-8", errors="ignore"))
            dt = data.get("doc_type")
            if isinstance(dt, str) and dt.strip():
                return dt.strip()
        except Exception:
            pass
        return None

    def _backup_and_remove_summary_files(self, doc) -> None:
        try:
            paths = self._summary_paths_for_doc(doc)
        except Exception:
            return

        ts = QDateTime.currentDateTime().toString("yyyyMMdd_HHmmss")

        for key in ("txt", "json"):
            fp = paths.get(key)
            if fp is None or not fp.exists():
                continue

            backup = fp.with_name(fp.name + f".bak_{ts}")
            try:
                fp.rename(backup)
            except Exception:
                try:
                    shutil.copy2(fp, backup)
                    fp.unlink()
                except Exception:
                    pass

    def _normalize_resume_state(self, reset_summarizing: bool = True) -> None:
        if self.state is None:
            return

        changed = False

        for doc in self.state.documents:
            if not doc.selected and doc.status != DOC_STATUS_SKIPPED:
                doc.status = DOC_STATUS_SKIPPED
                doc.error_message = ""
                changed = True
                continue

            desired_type = (doc.final_type() or "UNKNOWN").strip().upper()

            try:
                paths = self._summary_paths_for_doc(doc)
                has_txt = paths["txt"].exists()
                has_json = paths["json"].exists()
                has_any = has_txt or has_json
            except Exception:
                has_any = False
                has_json = False

            if doc.selected and has_any:
                used_type = self._read_summary_doc_type(doc) if has_json else None
                if used_type and used_type.strip().upper() != desired_type:
                    self._backup_and_remove_summary_files(doc)
                    doc.status = DOC_STATUS_QUEUED
                    doc.error_message = ""
                    changed = True
                    continue

                if doc.status != DOC_STATUS_SUMMARIZED:
                    doc.status = DOC_STATUS_SUMMARIZED
                    doc.error_message = ""
                    changed = True
                continue

            if doc.selected and doc.status == DOC_STATUS_SUMMARIZING:
                if reset_summarizing:
                    doc.status = DOC_STATUS_QUEUED
                    doc.error_message = ""
                    changed = True
                continue

            if doc.selected and doc.status in (DOC_STATUS_DETECTED, DOC_STATUS_EXTRACTED):
                doc.status = DOC_STATUS_QUEUED
                changed = True
                continue

        if changed:
            self.state.save_manifest()

    def on_resume_clicked(self) -> None:
        if self.state is None:
            return

        if self._is_worker_running():
            QMessageBox.information(self, "Info", "Samenvattingen zijn al bezig.")
            return

        self._normalize_resume_state(reset_summarizing=False)
        self.load_table()
        self.start_auto_summarization()

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

    def start_auto_summarization(self) -> None:
        if self.state is None:
            return

        if self._is_worker_running():
            self.resume_btn.setEnabled(False)
            return

        next_doc = next((d for d in self.state.documents if d.status == DOC_STATUS_QUEUED), None)
        if next_doc is None:
            self.resume_btn.setEnabled(True)
            self._update_subtitle()
            self._update_progress_bar()
            return

        # Check if user can process documents (trial or balance)
        if self.api_client:
            can_process = self._check_can_process_document()
            if not can_process:
                # Stop auto-summarization, show payment window
                self._show_purchase_required_dialog()
                return

        self._start_summarization_for_doc(next_doc.doc_id)

    def _start_summarization_for_doc(self, doc_id: str) -> None:
        if self.state is None or self.state.case.summaries_dir is None or self.state. case.extracted_dir is None:
            QMessageBox.critical(self, "Fout", "Case directories are not initialized.")
            return

        doc = next((d for d in self.state.documents if d.doc_id == doc_id), None)
        if doc is None:
            return

        # Deduct document from user's balance via API
        if self.api_client:
            self._append_log(f"Checking user balance for document: {doc.original_name}")
            result = self.api_client.process_document(
                document_name=doc.original_name,
                case_id=self.state.case.case_id
            )

            if not result["success"]:
                # Cannot process - show error and stop
                error_msg = result.get("error", "Cannot process document")
                self._append_log(f"ERROR: {error_msg}")

                QMessageBox.warning(
                    self,
                    "Kan document niet verwerken",
                    f"Fout bij het controleren van documentsaldo:\n\n{error_msg}\n\n"
                    "Controleer je internetverbinding en probeer opnieuw."
                )

                # Mark as queued again so user can retry
                doc.status = DOC_STATUS_QUEUED
                self.state.save_manifest()
                self.load_table()
                return

            # Success - log balance info
            remaining = result.get("remaining_balance", 0)
            was_trial = result.get("was_trial", False)

            if was_trial:
                self._append_log(f"✓ Document authorized (trial period)")
            else:
                self._append_log(f"✓ Document deducted from balance (remaining: {remaining})")

        self.resume_btn.setEnabled(False)
        self.current_doc_id = doc_id

        doc.status = DOC_STATUS_SUMMARIZING
        self.state.save_manifest()

        self._set_status_in_table(doc_id, DOC_STATUS_SUMMARIZING)
        self._update_subtitle()

        self.log_box.clear()
        self._append_log(f"=== Start: {doc.original_name} | Type={doc.final_type()} ===")

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

        # Subtitle: keep short (1 line)
        first_line = self.subtitle.text().split("\n")[0]
        short = msg if len(msg) <= 160 else (msg[:160] + "…")
        self.subtitle.setText(first_line + "\n" + short)

        # Log: full message
        self._append_log(msg)

    def _on_worker_error(self, message: str) -> None:
        if self.state is None or self.current_doc_id is None:
            return

        self._append_log("ERROR: " + str(message))

        doc = next((d for d in self.state.documents if d.doc_id == self.current_doc_id), None)
        if doc is None:
            return

        doc.status = DOC_STATUS_ERROR
        doc.error_message = str(message)
        self.state.save_manifest()

        self._set_status_in_table(doc.doc_id, DOC_STATUS_ERROR)
        self._update_subtitle()

        self.current_doc_id = None
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

        self._append_log("=== Done ===")

        self._set_status_in_table(doc.doc_id, DOC_STATUS_SUMMARIZED)
        self._refresh_row_buttons(doc.doc_id)
        self._update_subtitle()
        self._update_progress_bar()

        self.current_doc_id = None
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

        text = txt_path.read_text(encoding="utf-8", errors="ignore")

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Samenvatting – {doc.original_name}")
        dlg.setMinimumSize(900, 650)

        layout = QVBoxLayout(dlg)
        box = QTextEdit()
        box.setReadOnly(True)
        box.setPlainText(text)
        layout.addWidget(box)

        dlg.exec_()

    def export_summary(self, doc_id: str, kind: str) -> None:
        if self.state is None:
            return
        doc = next((d for d in self.state.documents if d.doc_id == doc_id), None)
        if doc is None:
            return

        paths = self._summary_paths_for_doc(doc)
        src = paths.get(kind)
        if src is None or not src.exists():
            QMessageBox.warning(self, "Niet gevonden", f"Geen {kind.upper()} gevonden.")
            return

        dest, _ = QFileDialog.getSaveFileName(self, "Opslaan als", src.name)
        if not dest:
            return
        try:
            shutil.copy2(src, dest)
        except Exception as e:
            QMessageBox.critical(self, "Fout", str(e))
    def _check_can_process_document(self) -> bool:
        """Check if user can process document (trial or has balance)"""
        if not self.api_client:
            # No API client - allow processing (offline mode)
            return True

        try:
            status = self.api_client.get_user_status()
            if not status:
                # API error - allow processing to avoid blocking
                return True

            return status.get("can_process", False)

        except Exception as e:
            self.log(f"Warning: Could not check user status: {e}")
            # On error, allow processing
            return True

    def _show_purchase_required_dialog(self) -> None:
        """Show dialog when user needs to purchase documents"""
        status = self.api_client.get_user_status() if self.api_client else None

        if status and status.get("is_trial"):
            # Trial ended
            message = (
                "Je gratis proefperiode is afgelopen.\n\n"
                "Om door te gaan met het verwerken van documenten, "
                "moet je een documentenpakket kopen.\n\n"
                "Wil je nu een pakket kopen?"
            )
        else:
            # No balance
            remaining = status.get("documents_remaining", 0) if status else 0
            message = (
                f"Je hebt geen documenten meer over (saldo: {remaining}).\n\n"
                "Om door te gaan met het verwerken van documenten, "
                "moet je een documentenpakket kopen.\n\n"
                "Wil je nu een pakket kopen?"
            )

        reply = QMessageBox.question(
            self,
            "Documentenpakket vereist",
            message,
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # Open purchase window
            from UI.purchase_window import PurchaseWindow
            self.purchase_window = PurchaseWindow(
                state=self.state,
                api_client=self.api_client,
                parent_window=self
            )
            self.purchase_window.show()

    def open_final_report(self) -> None:
        if self.state is None:
            return
        w = FinalReportWindow(self.state, api_client=self.api_client)
        w.show()

    def go_back(self) -> None:
        self.close()

    def _center_on_screen(self) -> None:
        try:
            screen = QApplication.primaryScreen().availableGeometry()
            self.move(
                screen.center().x() - self.width() // 2,
                screen.center().y() - self.height() // 2,
            )
        except Exception:
            pass
