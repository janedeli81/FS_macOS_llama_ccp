# UI/zip_upload_window.py

import sys
import os
import zipfile
from pathlib import Path
from typing import Optional

from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QFileDialog,
    QVBoxLayout,
    QHBoxLayout,
    QMessageBox,
    QTextEdit,
    QProgressBar,
    QFrame,
    QSizePolicy,
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

from backend.config import MODEL_PATH
from backend.state import AppState
from backend.summarizer_worker import ClassificationWorker
from UI.document_overview_window import DocumentOverviewWindow
from UI.ui_theme import apply_window_theme


def _is_macos_zip_artifact(path: Path) -> bool:
    try:
        if "__MACOSX" in path.parts:
            return True
    except Exception:
        pass

    name = path.name
    if name == ".DS_Store":
        return True
    if name.startswith("._"):
        return True

    return False


class ZipUploadWindow(QWidget):
    """
    ZIP Upload screen:
    - select ZIP
    - extract to case/extracted
    - detect document types (classification)
    - save results to manifest.json
    - go to Documents Manager
    """

    def __init__(self, state: Optional[AppState] = None):
        super().__init__()

        self.state = state or AppState()

        self.setWindowTitle("Nieuw dossier (ZIP)")
        self.setMinimumSize(1100, 720)
        self._center_on_screen()

        self.selected_file: Optional[str] = None
        self.all_files = []
        self.classified = {}
        self.output_dir: Optional[Path] = None
        self.extracted_dir: Optional[Path] = None

        self.classifier: Optional[ClassificationWorker] = None

        self._build_ui()
        apply_window_theme(self)

        self.update_model_status_label()

    def _build_ui(self):
        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.page = QFrame()
        self.page.setObjectName("page")

        page_layout = QVBoxLayout(self.page)
        page_layout.setContentsMargins(60, 40, 60, 44)
        page_layout.setSpacing(14)

        title = QLabel("Nieuw dossier (ZIP upload)")
        title.setObjectName("title")
        title.setFont(QFont("Segoe UI", 28, QFont.Bold))
        title.setAlignment(Qt.AlignLeft)
        title.setWordWrap(True)
        page_layout.addWidget(title)

        uitleg = QLabel("Kies een ZIP-bestand met dossierdocumenten:")
        uitleg.setObjectName("fieldLabel")
        uitleg.setFont(QFont("Segoe UI", 12))
        uitleg.setWordWrap(True)
        page_layout.addWidget(uitleg)

        file_row = QHBoxLayout()
        file_row.setSpacing(12)

        self.choose_btn = QPushButton("Bestand kiezen")
        self.choose_btn.setObjectName("secondaryButton")
        self.choose_btn.setCursor(Qt.PointingHandCursor)
        self.choose_btn.clicked.connect(self.select_zip)
        self.choose_btn.setFixedHeight(40)

        self.file_label = QLabel("Geen bestand gekozen")
        self.file_label.setObjectName("fieldLabel")
        self.file_label.setFont(QFont("Segoe UI", 12))
        self.file_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        file_row.addWidget(self.choose_btn, 0, Qt.AlignLeft)
        file_row.addWidget(self.file_label, 1, Qt.AlignVCenter)
        page_layout.addLayout(file_row)

        model_card = QFrame()
        model_card.setObjectName("card")

        model_layout = QVBoxLayout(model_card)
        model_layout.setContentsMargins(16, 12, 16, 12)
        model_layout.setSpacing(8)

        model_title = QLabel("LLM-model status")
        model_title.setObjectName("sectionTitle")
        model_title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        model_layout.addWidget(model_title)

        self.model_status_label = QLabel("")
        self.model_status_label.setObjectName("fieldLabel")
        self.model_status_label.setFont(QFont("Segoe UI", 10))
        self.model_status_label.setWordWrap(True)
        model_layout.addWidget(self.model_status_label)

        page_layout.addWidget(model_card, 0)

        self.log_area = QTextEdit()
        self.log_area.setObjectName("input")
        self.log_area.setReadOnly(True)
        self.log_area.setFont(QFont("Segoe UI", 11))
        self.log_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.log_area.setMinimumHeight(220)
        page_layout.addWidget(self.log_area, 1)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(14)

        self.back_btn = QPushButton("Terug")
        self.back_btn.setObjectName("secondaryButton")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.clicked.connect(self.go_back)
        self.back_btn.setFixedHeight(44)
        self.back_btn.setFixedWidth(120)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setFormat("%p% gereed")
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(28)
        self.progress_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.create_btn = QPushButton("Aanmaken")
        self.create_btn.setObjectName("primaryButton")
        self.create_btn.setCursor(Qt.PointingHandCursor)
        self.create_btn.clicked.connect(self.confirm_creation)
        self.create_btn.setFixedHeight(44)
        self.create_btn.setFixedWidth(160)

        bottom_row.addWidget(self.back_btn, 0, Qt.AlignLeft)
        bottom_row.addWidget(self.progress_bar, 1)
        bottom_row.addWidget(self.create_btn, 0, Qt.AlignRight)

        page_layout.addLayout(bottom_row)

        wrapper = QVBoxLayout()
        wrapper.setContentsMargins(18, 14, 18, 18)
        wrapper.addWidget(self.page)

        container = QWidget()
        container.setLayout(wrapper)

        root.addWidget(container)
        self.setLayout(root)

    def _human_size(self, num_bytes: int) -> str:
        gb = 1024 ** 3
        mb = 1024 ** 2
        kb = 1024

        if num_bytes >= gb:
            return f"{num_bytes / gb:.2f} GB"
        if num_bytes >= mb:
            return f"{num_bytes / mb:.1f} MB"
        if num_bytes >= kb:
            return f"{num_bytes / kb:.0f} KB"
        return f"{num_bytes} B"

    def _model_exists(self) -> bool:
        try:
            p = Path(MODEL_PATH)
            return p.exists() and p.stat().st_size > 10 * 1024 * 1024
        except Exception:
            return False

    def update_model_status_label(self) -> None:
        p = Path(MODEL_PATH)
        if p.exists():
            size_str = self._human_size(p.stat().st_size)
            offline = "Ja"
            note = "Model is lokaal beschikbaar. Offline gebruik is mogelijk."
        else:
            size_str = "-"
            offline = "Nee"
            note = "Model ontbreekt. Ga terug en download het model in het Modelcontrole-scherm."

        text = (
            f"Offline klaar: {offline}\n"
            f"Bestand: {p.name}\n"
            f"Grootte: {size_str}\n"
            f"Pad: {p}\n"
            f"{note}"
        )
        self.model_status_label.setText(text)

    def log(self, text: str) -> None:
        self.log_area.append(text)

    def _set_ui_busy(self, busy: bool) -> None:
        self.choose_btn.setEnabled(not busy)
        self.create_btn.setEnabled(not busy)
        self.back_btn.setEnabled(not busy)

    def select_zip(self) -> None:
        zip_path, _ = QFileDialog.getOpenFileName(
            self, "Selecteer ZIP-bestand", "", "ZIP bestanden (*.zip)"
        )
        if zip_path:
            self.selected_file = zip_path
            self.file_label.setText(Path(zip_path).name)

    def confirm_creation(self) -> None:
        if not self.selected_file:
            QMessageBox.warning(self, "Geen bestand", "Selecteer eerst een ZIP-bestand.")
            return

        if not self._model_exists():
            QMessageBox.warning(
                self,
                "Model ontbreekt",
                "Het LLM-model is niet gevonden.\nGa terug en download het model in het Modelcontrole-scherm."
            )
            return

        self._set_ui_busy(True)
        self.progress_bar.setMaximum(0)
        self.progress_bar.setValue(0)

        try:
            # IMPORTANT: this now stores cases under USER_DATA_DIR/cases (via backend/state.py)
            self.state.init_new_case(Path(self.selected_file))
            self.extracted_dir = self.state.case.extracted_dir
            self.output_dir = self.state.case.summaries_dir

            if self.extracted_dir is None:
                raise RuntimeError("Case extracted_dir is not initialized.")
            if self.output_dir is None:
                raise RuntimeError("Case summaries_dir is not initialized.")

            self.log(f"Case aangemaakt: {self.state.case.case_id}")
            self.log(f"Extracted dir: {self.extracted_dir}")

        except Exception as e:
            self._set_ui_busy(False)
            self.progress_bar.setMaximum(100)
            self.progress_bar.setValue(0)
            QMessageBox.critical(self, "Fout", f"Fout bij case-initialisatie:\n{e}")
            return

        try:
            with zipfile.ZipFile(self.selected_file, "r") as zip_ref:
                zip_ref.extractall(self.extracted_dir)
                self.log(f"ZIP uitgepakt naar: {self.extracted_dir}")

            self.all_files = []
            for root, _, files in os.walk(self.extracted_dir):
                root_path = Path(root)
                if "__MACOSX" in root_path.parts:
                    continue

                for filename in files:
                    full_path = root_path / filename
                    if _is_macos_zip_artifact(full_path):
                        continue
                    self.all_files.append(full_path)

            if not self.all_files:
                self._set_ui_busy(False)
                self.progress_bar.setMaximum(100)
                self.progress_bar.setValue(0)
                QMessageBox.warning(self, "Leeg", "ZIP-bestand bevat geen documenten.")
                return

            self.start_classification()

        except Exception as e:
            self._set_ui_busy(False)
            self.progress_bar.setMaximum(100)
            self.progress_bar.setValue(0)
            QMessageBox.critical(self, "Fout", f"Fout bij uitpakken van ZIP:\n{e}")

    def start_classification(self) -> None:
        self.log("Detecting document types for all files...")

        self.progress_bar.setMaximum(0)
        self.progress_bar.setValue(0)

        self.classified = {}
        self.classifier = ClassificationWorker(self.all_files)
        self.classifier.progress.connect(self.log)
        self.classifier.error.connect(self.log)
        self.classifier.finished.connect(self.on_classification_finished)
        self.classifier.start()

    def on_classification_finished(self, results: list) -> None:
        try:
            self.classified = {item["path"]: item for item in results}
            self.all_files = [Path(item["path"]) for item in results]

            if not self.all_files:
                self._set_ui_busy(False)
                self.progress_bar.setMaximum(100)
                self.progress_bar.setValue(0)
                QMessageBox.warning(self, "Leeg", "Geen documenten met tekst gevonden na classificatie.")
                return

            self.log("\nDetected document types:")
            for item in results:
                self.log(f" • {item.get('filename', Path(item['path']).name)}  →  {item.get('doc_type', '')}")

            self.state.documents = []
            for item in results:
                self.state.add_document(
                    original_name=item.get("filename", Path(item["path"]).name),
                    source_path=Path(item["path"]),
                    detected_type=item.get("doc_type", "") or "",
                    detected_confidence=item.get("confidence"),
                    selected=True,
                )

            mp = self.state.save_manifest()
            self.log(f"\n✅ Classification saved: {mp}")

            self.progress_bar.setMaximum(100)
            self.progress_bar.setValue(100)
            self._set_ui_busy(False)

            self.next_window = DocumentOverviewWindow(state=self.state)
            self.next_window.show()
            self.close()

        except Exception as e:
            self._set_ui_busy(False)
            self.progress_bar.setMaximum(100)
            self.progress_bar.setValue(0)
            QMessageBox.critical(self, "Fout", f"Fout na classificatie:\n{e}")

    def go_back(self) -> None:
        from UI.cases_list_window import CasesListWindow

        self.close()
        self.prev = CasesListWindow(state=self.state)
        self.prev.show()

    def closeEvent(self, event):
        self._stop_threads()
        event.accept()

    def _stop_threads(self) -> None:
        t = self.classifier
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
    window = ZipUploadWindow()
    window.show()
    sys.exit(app.exec_())
