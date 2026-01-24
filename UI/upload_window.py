# UI/upload_window.py

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QTextEdit,
    QProgressBar,
    QMessageBox,
)

from backend.config import MODEL_PATH
from backend.state import (
    AppState,
    MODEL_STATUS_READY,
    MODEL_STATUS_MISSING,
    MODEL_STATUS_DOWNLOADING,
    MODEL_STATUS_ERROR,
)
from UI.ui_theme import apply_window_theme


class ModelDownloadWorker(QThread):
    progress = pyqtSignal(int, str)  # percent, message (percent can be -1 for indeterminate)
    done = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, model_path: Path):
        super().__init__()
        self.model_path = model_path

    def run(self) -> None:
        try:
            self.model_path.parent.mkdir(parents=True, exist_ok=True)

            used_backend = self._try_backend_downloader()
            if used_backend:
                if self._model_exists():
                    self.done.emit()
                    return
                raise RuntimeError("Backend downloader finished, but model file is still missing/invalid.")

            url = self._get_download_url_from_config()
            if not url:
                raise RuntimeError(
                    "MODEL download is not configured.\n"
                    "Add MODEL_DOWNLOAD_URL (or MODEL_URL) to backend/config.py."
                )

            self._download_via_http(url)
            if not self._model_exists():
                raise RuntimeError("Download finished, but model file is still missing/invalid.")

            self.done.emit()

        except Exception as e:
            self.failed.emit(str(e))

    def _model_exists(self) -> bool:
        try:
            return self.model_path.exists() and self.model_path.stat().st_size > 10 * 1024 * 1024
        except Exception:
            return False

    def _try_backend_downloader(self) -> bool:
        try:
            import backend.llm_runner as llm_runner  # type: ignore
        except Exception:
            return False

        candidates = [
            "ensure_model",
            "ensure_model_downloaded",
            "download_model_if_missing",
            "download_model",
        ]

        for name in candidates:
            fn = getattr(llm_runner, name, None)
            if not callable(fn):
                continue

            self.progress.emit(-1, f"Using backend downloader: {name}()")

            try:
                sig = inspect.signature(fn)
                params = list(sig.parameters.values())

                if len(params) == 0:
                    fn()
                    return True

                if len(params) == 1:
                    try:
                        fn(self.model_path)
                        return True
                    except Exception:
                        fn(str(self.model_path))
                        return True

                if len(params) == 2:
                    try:
                        fn(self.model_path, True)
                        return True
                    except Exception:
                        fn(str(self.model_path), True)
                        return True

            except Exception:
                continue

        return False

    def _get_download_url_from_config(self) -> str:
        try:
            import backend.config as cfg  # type: ignore
        except Exception:
            return ""

        url = getattr(cfg, "MODEL_DOWNLOAD_URL", "") or ""
        if url:
            return url.strip()

        url = getattr(cfg, "MODEL_URL", "") or ""
        if url:
            return url.strip()

        repo = getattr(cfg, "HF_REPO_ID", "") or getattr(cfg, "MODEL_REPO_ID", "") or ""
        fname = getattr(cfg, "HF_FILENAME", "") or getattr(cfg, "MODEL_FILENAME", "") or ""
        if repo and fname:
            return f"https://huggingface.co/{repo}/resolve/main/{fname}"

        return ""

    def _download_via_http(self, url: str) -> None:
        try:
            import requests
        except Exception as e:
            raise RuntimeError("The 'requests' package is required for HTTP model downloads.") from e

        tmp_path = self.model_path.with_suffix(self.model_path.suffix + ".part")

        self.progress.emit(0, f"Downloading model from: {url}")

        with requests.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()

            total = int(r.headers.get("Content-Length", "0") or "0")
            if total <= 0:
                self.progress.emit(-1, "Downloading... (unknown size)")
            else:
                self.progress.emit(0, f"Downloading... (total {total} bytes)")

            downloaded = 0
            chunk_size = 16 * 1024 * 1024  # 16MB

            with tmp_path.open("wb") as f:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)

                    if total > 0:
                        pct = int((downloaded / total) * 100)
                        pct = max(0, min(100, pct))
                        self.progress.emit(pct, f"Downloaded {downloaded} / {total} bytes")
                    else:
                        self.progress.emit(-1, f"Downloaded {downloaded} bytes")

        tmp_path.replace(self.model_path)


class ModelCheckWindow(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state

        self.setWindowTitle("Modelcontrole")
        self.setMinimumSize(1100, 720)
        self._center_on_screen()

        self.model_path = Path(MODEL_PATH)
        self.worker: Optional[ModelDownloadWorker] = None

        self._build_ui()
        apply_window_theme(self)

        self._refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.page = QFrame()
        self.page.setObjectName("page")

        page_layout = QVBoxLayout(self.page)
        page_layout.setContentsMargins(60, 40, 60, 44)
        page_layout.setSpacing(14)

        title = QLabel("MODEL CONTROLE")
        title.setObjectName("title")
        title.setFont(QFont("Segoe UI", 28, QFont.Bold))
        title.setWordWrap(True)
        page_layout.addWidget(title)

        subtitle = QLabel("Controleer of het LLM-model lokaal beschikbaar is. Zo niet, download het eenmalig.")
        subtitle.setObjectName("fieldLabel")
        subtitle.setWordWrap(True)
        page_layout.addWidget(subtitle)

        self.status_card = QFrame()
        self.status_card.setObjectName("card")
        card_layout = QVBoxLayout(self.status_card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(10)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        card_layout.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        card_layout.addWidget(self.progress)

        self.log_area = QTextEdit()
        self.log_area.setObjectName("input")
        self.log_area.setReadOnly(True)
        self.log_area.setFixedHeight(180)
        card_layout.addWidget(self.log_area)

        page_layout.addWidget(self.status_card)
        page_layout.addStretch(1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self.back_btn = QPushButton("Terug")
        self.back_btn.setObjectName("secondaryButton")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.clicked.connect(self._go_back_to_login)

        self.download_btn = QPushButton("Download model")
        self.download_btn.setObjectName("secondaryButton")
        self.download_btn.setCursor(Qt.PointingHandCursor)
        self.download_btn.clicked.connect(self._start_download)

        self.continue_btn = QPushButton("Doorgaan")
        self.continue_btn.setObjectName("primaryButton")
        self.continue_btn.setCursor(Qt.PointingHandCursor)
        self.continue_btn.clicked.connect(self._go_to_cases_list)

        btn_row.addWidget(self.back_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.download_btn)
        btn_row.addWidget(self.continue_btn)

        page_layout.addLayout(btn_row)

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
            return self.model_path.exists() and self.model_path.stat().st_size > 10 * 1024 * 1024
        except Exception:
            return False

    def _refresh(self) -> None:
        exists = self._model_exists()

        self.state.model.path = self.model_path
        self.state.model.name = getattr(self.state.model, "name", "") or self.model_path.name

        if exists:
            self.state.model.status = MODEL_STATUS_READY
            size_str = self._human_size(self.model_path.stat().st_size)
            offline = "Ja"
            note = "Model is lokaal beschikbaar. Offline gebruik is mogelijk."
        else:
            if self.state.model.status == MODEL_STATUS_DOWNLOADING:
                offline = "Nee"
                size_str = "-"
                note = "Model wordt nu gedownload. Dit gebeurt eenmalig."
            else:
                self.state.model.status = MODEL_STATUS_MISSING
                offline = "Nee"
                size_str = "-"
                note = "Model is niet gevonden. Klik op 'Download model' om te downloaden."

        text = (
            f"Offline klaar: {offline}\n"
            f"Bestand: {self.model_path.name}\n"
            f"Grootte: {size_str}\n"
            f"Pad: {self.model_path}\n\n"
            f"{note}"
        )
        self.status_label.setText(text)

        self.continue_btn.setEnabled(exists and self.state.model.status != MODEL_STATUS_DOWNLOADING)
        self.download_btn.setEnabled((not exists) and self.state.model.status != MODEL_STATUS_DOWNLOADING)

    def _set_progress(self, percent: int) -> None:
        self.progress.setVisible(True)
        if percent < 0:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(max(0, min(100, percent)))

    def _start_download(self) -> None:
        if self._model_exists():
            QMessageBox.information(self, "Info", "Model is al aanwezig.")
            self._refresh()
            return

        self.state.model.status = MODEL_STATUS_DOWNLOADING
        self._refresh()

        self.log_area.append("Starting model download...")
        self._set_progress(-1)

        self.worker = ModelDownloadWorker(model_path=self.model_path)
        self.worker.progress.connect(self._on_worker_progress)
        self.worker.done.connect(self._on_worker_done)
        self.worker.failed.connect(self._on_worker_failed)
        self.worker.start()

    def _on_worker_progress(self, percent: int, message: str) -> None:
        self._set_progress(percent)
        if message:
            self.log_area.append(message)

    def _on_worker_done(self) -> None:
        self.state.model.status = MODEL_STATUS_READY
        self.log_area.append("Model download complete.")
        self.progress.setVisible(False)
        self._refresh()
        QMessageBox.information(self, "Klaar", "Model is klaar voor gebruik.")

    def _on_worker_failed(self, error_message: str) -> None:
        self.state.model.status = MODEL_STATUS_ERROR
        self.state.model.error_message = error_message
        self.log_area.append(f"ERROR: {error_message}")
        self.progress.setVisible(False)
        self._refresh()
        QMessageBox.critical(self, "Fout", error_message)

    def _go_to_cases_list(self) -> None:
        if not self._model_exists():
            QMessageBox.warning(self, "Fout", "Model ontbreekt. Download het model eerst.")
            return

        from UI.cases_list_window import CasesListWindow

        self.close()
        self.cases_window = CasesListWindow(state=self.state)
        self.cases_window.show()

    def _go_back_to_login(self) -> None:
        from UI.login_window import LoginWindow
        self.close()
        self.login_window = LoginWindow()
        self.login_window.show()

    def _center_on_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if not screen:
            return
        rect = screen.availableGeometry()
        x = rect.x() + (rect.width() - self.width()) // 2
        y = rect.y() + (rect.height() - self.height()) // 2
        self.move(x, y)


UploadWindow = ModelCheckWindow
