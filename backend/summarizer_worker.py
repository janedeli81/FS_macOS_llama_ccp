# backend/summarizer_worker.py

from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path
from typing import Dict, List, Optional

from PyQt5.QtCore import QThread, pyqtSignal

from backend.classifiers import classify_document
from backend.process_zip import extract_basic_meta, guess_workflow
from backend.summarizer import summarize_document
from backend.text_extraction import extract_text
from backend.model_manager import ensure_model_ready
from backend.config import MODEL_PATH


# Global lock to avoid concurrent model download/init/inference across QThreads.
_LLM_JOB_LOCK = threading.Lock()


def _is_macos_zip_artifact(path: Path) -> bool:
    """
    Detect macOS ZIP artifacts:
    - __MACOSX folder entries
    - AppleDouble files (._filename)
    - .DS_Store
    """
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


def _is_model_present() -> bool:
    """
    Quick presence check to decide whether we should display 'download' messages.
    """
    try:
        p = Path(MODEL_PATH)
        return p.exists() and p.stat().st_size > 10 * 1024 * 1024
    except Exception:
        return False


class ClassificationWorker(QThread):
    """Stage 1: Extract text + detect doc types for all documents first."""

    progress = pyqtSignal(str)
    finished = pyqtSignal(list)  # List[dict]
    error = pyqtSignal(str)

    def __init__(self, file_paths: List[Path]):
        super().__init__()

        # Filter out macOS metadata artifacts up-front.
        clean: List[Path] = []
        for p in file_paths:
            pp = Path(p)
            if _is_macos_zip_artifact(pp):
                continue
            clean.append(pp)

        self.file_paths = clean

    def run(self):
        results: List[Dict] = []
        try:
            total = len(self.file_paths)

            for i, file_path in enumerate(self.file_paths, start=1):
                if _is_macos_zip_artifact(file_path):
                    continue

                try:
                    self.progress.emit(f"({i}/{total}) Detecting type: {file_path.name}")

                    text = extract_text(file_path)
                    if not text or not text.strip():
                        self.error.emit(f"Warning: No text extracted for {file_path.name} (skipped)")
                        continue

                    doc_type = classify_document(file_path, text)
                    results.append(
                        {
                            "path": str(file_path),
                            "filename": file_path.name,
                            "doc_type": doc_type,
                            "text": text,
                        }
                    )

                except Exception as e:
                    self.error.emit(f"Error classifying {file_path.name}: {e}")

            self.finished.emit(results)

        except Exception as e:
            self.error.emit(f"Classification failed: {e}")


class SummarizationWorker(QThread):
    """Stage 2: Summarize one document (doc_type/text can be precomputed)."""

    progress = pyqtSignal(str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(
        self,
        file_path: Path,
        output_dir: Path,
        extracted_dir: Path,
        *,
        doc_type: Optional[str] = None,
        text: Optional[str] = None,
    ):
        super().__init__()
        self.file_path = Path(file_path)
        self.output_dir = Path(output_dir)
        self.extracted_dir = Path(extracted_dir)
        self.precomputed_doc_type = doc_type
        self.precomputed_text = text

    def _ensure_extracted_copy(self) -> Path:
        """Copy original file to extracted_dir unless it's already there."""
        self.extracted_dir.mkdir(parents=True, exist_ok=True)
        target = self.extracted_dir / self.file_path.name

        try:
            if self.file_path.resolve().parent == self.extracted_dir.resolve():
                return self.file_path
        except Exception:
            pass

        try:
            shutil.copy2(self.file_path, target)
            return target
        except Exception:
            return self.file_path

    def run(self):
        try:
            filename = self.file_path.name

            # Never process macOS metadata files.
            if _is_macos_zip_artifact(self.file_path):
                self.progress.emit(f"Skipping macOS metadata file: {filename}")
                return

            # 0) Ensure model first (download on first run).
            # IMPORTANT: "Starting summarization..." should appear only after this.
            with _LLM_JOB_LOCK:
                already_present = _is_model_present()

                if not already_present:
                    # Optional hint: user sees that we are waiting for the model download.
                    self.progress.emit("Preparing LLM model (first run download)...")

                ensure_model_ready(progress_cb=lambda m: self.progress.emit(m))

            # 1) Now we can safely announce summarization start (model is ready).
            self.progress.emit("Starting summarization...")

            self.progress.emit(f"Processing: {filename}")

            self.output_dir.mkdir(parents=True, exist_ok=True)

            extracted_path = self._ensure_extracted_copy()

            # 2) Get text
            text = self.precomputed_text
            if text is None:
                text = extract_text(extracted_path)
            if not text or not text.strip():
                self.error.emit(f"Warning: No text extracted in {filename}")
                return

            # 3) Get doc_type
            doc_type = self.precomputed_doc_type
            if not doc_type:
                doc_type = classify_document(extracted_path, text)
            self.progress.emit(f"Document type: {doc_type}")

            # 4) Run summarization (also keep it serialized if your LLM backend isn't thread-safe)
            with _LLM_JOB_LOCK:
                def progress_cb(message: str):
                    self.progress.emit(message)

                summary = summarize_document(
                    doc_type=doc_type,
                    text=text,
                    progress_callback=progress_cb,
                )

            # 5) Save TXT
            stem = extracted_path.stem
            txt_path = self.output_dir / f"{stem}_summary.txt"
            txt_path.write_text(summary, encoding="utf-8")

            # 6) Save JSON with metadata
            json_path = self.output_dir / f"{stem}_summary.json"
            json_data = {
                "filename": filename,
                "doc_type": doc_type,
                "workflow": guess_workflow(doc_type),
                "summary": summary,
                "meta": extract_basic_meta(text),
            }
            json_path.write_text(
                json.dumps(json_data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            # 7) Done
            self.finished.emit(
                {
                    "filename": filename,
                    "doc_type": doc_type,
                    "summary": summary,
                    "path": txt_path,
                }
            )

        except Exception as e:
            self.error.emit(f"Error processing {self.file_path.name}: {e}")
