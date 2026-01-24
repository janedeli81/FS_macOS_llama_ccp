# backend/state.py
# All comments are intentionally in English (project convention).

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# -----------------------------
# Enums / constants (simple strings to keep JSON easy)
# -----------------------------

DOC_STATUS_EXTRACTED = "extracted"
DOC_STATUS_DETECTED = "detected"
DOC_STATUS_QUEUED = "queued"
DOC_STATUS_SUMMARIZING = "summarizing"
DOC_STATUS_SUMMARIZED = "summarized"
DOC_STATUS_ERROR = "error"
DOC_STATUS_SKIPPED = "skipped"

MODEL_STATUS_READY = "ready"
MODEL_STATUS_MISSING = "missing"
MODEL_STATUS_DOWNLOADING = "downloading"
MODEL_STATUS_ERROR = "error"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe_mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _to_path(value: Optional[str]) -> Optional[Path]:
    if not value:
        return None
    return Path(value)


def _path_str(p: Optional[Path]) -> Optional[str]:
    if p is None:
        return None
    return str(p)


def new_case_id() -> str:
    # Human-readable case id + short UUID suffix for uniqueness.
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    suffix = uuid.uuid4().hex[:6]
    return f"{ts}_{suffix}"


def default_cases_root() -> Path:
    """
    Determine the root folder where cases are stored.

    Priority:
    1) backend/config.py: CASES_DIR (if provided)
    2) backend/config.py: USER_DATA_DIR / "cases" (recommended for desktop apps)
    3) fallback: ./cases (dev)
    """
    try:
        import backend.config as cfg  # type: ignore
        cases_dir = getattr(cfg, "CASES_DIR", None)
        if cases_dir:
            return Path(cases_dir)

        user_data_dir = getattr(cfg, "USER_DATA_DIR", None)
        if user_data_dir:
            return Path(user_data_dir) / "cases"
    except Exception:
        pass

    return Path("cases")


# -----------------------------
# Data structures
# -----------------------------

@dataclass
class UserState:
    email: str = ""


@dataclass
class ModelState:
    name: str = ""
    status: str = MODEL_STATUS_MISSING
    path: Optional[Path] = None
    last_checked_at: Optional[str] = None
    error_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["path"] = _path_str(self.path)
        return d

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ModelState":
        return ModelState(
            name=d.get("name", ""),
            status=d.get("status", MODEL_STATUS_MISSING),
            path=_to_path(d.get("path")),
            last_checked_at=d.get("last_checked_at"),
            error_message=d.get("error_message", ""),
        )


@dataclass
class SummaryState:
    txt_path: Optional[Path] = None
    json_path: Optional[Path] = None
    updated_at: Optional[str] = None
    error_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "txt_path": _path_str(self.txt_path),
            "json_path": _path_str(self.json_path),
            "updated_at": self.updated_at,
            "error_message": self.error_message,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "SummaryState":
        return SummaryState(
            txt_path=_to_path(d.get("txt_path")),
            json_path=_to_path(d.get("json_path")),
            updated_at=d.get("updated_at"),
            error_message=d.get("error_message", ""),
        )


@dataclass
class DocumentState:
    doc_id: str
    original_name: str
    source_path: Path
    file_ext: str = ""
    detected_type: str = ""
    detected_confidence: Optional[float] = None
    type_override: str = ""
    selected: bool = True
    status: str = DOC_STATUS_DETECTED
    summary: SummaryState = field(default_factory=SummaryState)
    error_message: str = ""

    def final_type(self) -> str:
        # Override wins; otherwise use detected.
        return (self.type_override or self.detected_type or "").strip()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "original_name": self.original_name,
            "source_path": _path_str(self.source_path),
            "file_ext": self.file_ext,
            "detected_type": self.detected_type,
            "detected_confidence": self.detected_confidence,
            "type_override": self.type_override,
            "selected": self.selected,
            "status": self.status,
            "summary": self.summary.to_dict(),
            "error_message": self.error_message,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "DocumentState":
        return DocumentState(
            doc_id=d["doc_id"],
            original_name=d.get("original_name", ""),
            source_path=Path(d.get("source_path", "")),
            file_ext=d.get("file_ext", ""),
            detected_type=d.get("detected_type", ""),
            detected_confidence=d.get("detected_confidence"),
            type_override=d.get("type_override", ""),
            selected=bool(d.get("selected", True)),
            status=d.get("status", DOC_STATUS_DETECTED),
            summary=SummaryState.from_dict(d.get("summary", {}) or {}),
            error_message=d.get("error_message", ""),
        )


@dataclass
class CaseState:
    case_id: str = ""
    case_dir: Optional[Path] = None
    source_zip_path: Optional[Path] = None

    extracted_dir: Optional[Path] = None
    summaries_dir: Optional[Path] = None
    final_dir: Optional[Path] = None

    selected_zip_path: Optional[Path] = None
    final_report_path: Optional[Path] = None

    archive_created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "case_dir": _path_str(self.case_dir),
            "source_zip_path": _path_str(self.source_zip_path),
            "extracted_dir": _path_str(self.extracted_dir),
            "summaries_dir": _path_str(self.summaries_dir),
            "final_dir": _path_str(self.final_dir),
            "selected_zip_path": _path_str(self.selected_zip_path),
            "final_report_path": _path_str(self.final_report_path),
            "archive_created_at": self.archive_created_at,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "CaseState":
        return CaseState(
            case_id=d.get("case_id", ""),
            case_dir=_to_path(d.get("case_dir")),
            source_zip_path=_to_path(d.get("source_zip_path")),
            extracted_dir=_to_path(d.get("extracted_dir")),
            summaries_dir=_to_path(d.get("summaries_dir")),
            final_dir=_to_path(d.get("final_dir")),
            selected_zip_path=_to_path(d.get("selected_zip_path")),
            final_report_path=_to_path(d.get("final_report_path")),
            archive_created_at=d.get("archive_created_at"),
        )


@dataclass
class SettingsState:
    language: str = "nl"
    output_formats: List[str] = field(default_factory=lambda: ["txt", "json", "pdf"])

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "SettingsState":
        return SettingsState(
            language=d.get("language", "nl"),
            output_formats=list(d.get("output_formats", ["txt", "json", "pdf"])),
        )


@dataclass
class AppState:
    user: UserState = field(default_factory=UserState)
    model: ModelState = field(default_factory=ModelState)
    case: CaseState = field(default_factory=CaseState)
    documents: List[DocumentState] = field(default_factory=list)
    settings: SettingsState = field(default_factory=SettingsState)

    version: int = 1
    updated_at: str = field(default_factory=_now_iso)

    # ---------
    # Case lifecycle helpers
    # ---------

    def init_new_case(self, source_zip_path: Path, cases_root: Optional[Path] = None) -> None:
        """
        Initialize a new case folder structure and set paths.
        This does not extract or detect; it only prepares folders and manifest location.
        """
        root = cases_root or default_cases_root()
        _safe_mkdir(root)

        case_id = new_case_id()
        case_dir = root / case_id

        extracted_dir = case_dir / "extracted"
        summaries_dir = case_dir / "summaries"
        final_dir = case_dir / "final"
        selected_dir = case_dir / "selected"

        _safe_mkdir(case_dir)
        _safe_mkdir(extracted_dir)
        _safe_mkdir(summaries_dir)
        _safe_mkdir(final_dir)
        _safe_mkdir(selected_dir)

        self.case = CaseState(
            case_id=case_id,
            case_dir=case_dir,
            source_zip_path=source_zip_path,
            extracted_dir=extracted_dir,
            summaries_dir=summaries_dir,
            final_dir=final_dir,
            selected_zip_path=selected_dir / "selected_documents.zip",
            final_report_path=final_dir / "final_report.pdf",
            archive_created_at=None,
        )
        self.documents = []
        self.touch()

    def ensure_case_dirs(self) -> None:
        """
        Ensure case directory structure exists (useful when loading existing manifest).
        """
        if not self.case.case_dir:
            return
        _safe_mkdir(self.case.case_dir)
        if self.case.extracted_dir:
            _safe_mkdir(self.case.extracted_dir)
        if self.case.summaries_dir:
            _safe_mkdir(self.case.summaries_dir)
        if self.case.final_dir:
            _safe_mkdir(self.case.final_dir)
        if self.case.selected_zip_path:
            _safe_mkdir(Path(self.case.selected_zip_path).parent)

    def manifest_path(self) -> Optional[Path]:
        if not self.case.case_dir:
            return None
        return self.case.case_dir / "manifest.json"

    def touch(self) -> None:
        self.updated_at = _now_iso()

    # ---------
    # Documents helpers
    # ---------

    def add_document(
        self,
        original_name: str,
        source_path: Path,
        detected_type: str = "",
        detected_confidence: Optional[float] = None,
        selected: bool = True,
    ) -> DocumentState:
        doc = DocumentState(
            doc_id=uuid.uuid4().hex,
            original_name=original_name,
            source_path=source_path,
            file_ext=source_path.suffix.lower().lstrip("."),
            detected_type=detected_type,
            detected_confidence=detected_confidence,
            type_override="",
            selected=selected,
            status=DOC_STATUS_DETECTED,
        )
        self.documents.append(doc)
        self.touch()
        return doc

    def get_selected_documents(self) -> List[DocumentState]:
        return [d for d in self.documents if d.selected]

    def mark_archive_created_and_queue_selected(self) -> None:
        """
        Called when user clicks "Create case archive".
        - Sets archive_created_at
        - Queues selected documents
        """
        self.case.archive_created_at = _now_iso()

        for d in self.documents:
            if d.selected:
                d.status = DOC_STATUS_QUEUED
            else:
                d.status = DOC_STATUS_SKIPPED

        self.touch()

    # ---------
    # Serialization
    # ---------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "updated_at": self.updated_at,
            "user": asdict(self.user),
            "model": self.model.to_dict(),
            "case": self.case.to_dict(),
            "documents": [d.to_dict() for d in self.documents],
            "settings": self.settings.to_dict(),
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "AppState":
        state = AppState()
        state.version = int(d.get("version", 1))
        state.updated_at = d.get("updated_at", _now_iso())

        state.user = UserState(email=(d.get("user", {}) or {}).get("email", ""))
        state.model = ModelState.from_dict(d.get("model", {}) or {})
        state.case = CaseState.from_dict(d.get("case", {}) or {})
        state.documents = [DocumentState.from_dict(x) for x in (d.get("documents", []) or [])]
        state.settings = SettingsState.from_dict(d.get("settings", {}) or {})
        return state

    def save_manifest(self) -> Path:
        """
        Save manifest.json into case_dir. Raises if case_dir is not set.
        """
        mp = self.manifest_path()
        if mp is None:
            raise RuntimeError("Cannot save manifest: case_dir is not initialized.")
        self.ensure_case_dirs()
        self.touch()
        with mp.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        return mp

    @staticmethod
    def load_manifest(manifest_path: Path) -> "AppState":
        with manifest_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        state = AppState.from_dict(data)
        state.ensure_case_dirs()
        return state
