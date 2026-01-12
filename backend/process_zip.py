# backend/process_zip.py

import os
import json
import shutil
import zipfile
import tempfile
import re
from pathlib import Path

from backend.text_extraction import extract_text
from backend.classifiers import classify_document
from backend.summarizer import summarize_document

# Import absolute paths from config (cross-platform + PyInstaller-safe)
from backend.config import OUTPUT_DIR, EXTRACTED_DIR

# Ensure folders exist
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)


def _should_skip_member(name: str) -> bool:
    """
    Skip macOS metadata files and other non-document artifacts commonly found in ZIPs:
    - __MACOSX folder
    - AppleDouble files (._filename)
    - .DS_Store
    """
    n = name.replace("\\", "/")

    # Skip directories
    if n.endswith("/"):
        return True

    # Skip macOS metadata folder
    if n.startswith("__MACOSX/") or "/__MACOSX/" in n:
        return True

    base = Path(n).name

    # Skip AppleDouble metadata files
    if base.startswith("._"):
        return True

    # Skip Finder artifact
    if base == ".DS_Store":
        return True

    return False


def _safe_clear_dir(dir_path: Path) -> None:
    """
    Remove all files and folders inside the given directory.
    """
    if not dir_path.exists():
        return

    for p in dir_path.iterdir():
        try:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)
        except Exception:
            # Best-effort cleanup; do not crash processing.
            pass


def _unique_target_path(dst_dir: Path, filename: str) -> Path:
    """
    Avoid overwriting if the ZIP contains multiple files with the same name.
    """
    dst_dir.mkdir(parents=True, exist_ok=True)
    base = Path(filename).name
    target = dst_dir / base
    if not target.exists():
        return target

    stem = target.stem
    suffix = target.suffix
    i = 1
    while True:
        candidate = dst_dir / f"{stem}__{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def process_zip(zip_path: Path, output_dir: Path = OUTPUT_DIR, output_format: str = "txt"):
    """
    Process a ZIP archive:
    - extract documents (skipping macOS artifacts)
    - classify each file
    - summarize content
    - save .txt and .json summaries
    - copy original docs to extracted_documents/
    """
    print(f"Start processing ZIP: {zip_path}")

    # Clear old output summaries
    for f in output_dir.glob("*_summary.*"):
        try:
            f.unlink(missing_ok=True)
        except Exception:
            pass

    # Clear previously extracted documents
    _safe_clear_dir(EXTRACTED_DIR)

    # Extract ZIP to a temporary folder (filtering macOS artifacts)
    with tempfile.TemporaryDirectory() as temp_dir:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            extracted_count = 0
            for info in zip_ref.infolist():
                if _should_skip_member(info.filename):
                    continue
                zip_ref.extract(info, temp_dir)
                extracted_count += 1

            print(f"Archive extracted to: {temp_dir} (files extracted: {extracted_count})")

        # Process all files inside the temporary folder
        for root, _, files in os.walk(temp_dir):
            # Skip __MACOSX even if it somehow exists on disk
            if "__MACOSX" in Path(root).parts:
                continue

            for filename in files:
                # Skip AppleDouble and other hidden artifacts
                if filename.startswith("._") or filename == ".DS_Store":
                    continue

                full_path = Path(root) / filename
                print(f"\nProcessing: {full_path.name}")

                try:
                    # Extract text from document
                    text = extract_text(full_path)
                    if not text:
                        print("Warning: No text extracted.")
                        continue

                    # Classify document type
                    doc_type = classify_document(full_path, text)
                    print(f"Document type: {doc_type}")

                    # Summarize based on type
                    summary = summarize_document(doc_type, text)

                    # Prepare output paths
                    stem = full_path.stem
                    txt_path = output_dir / f"{stem}_summary.txt"
                    json_path = output_dir / f"{stem}_summary.json"

                    # Save TXT summary
                    txt_path.write_text(summary, encoding="utf-8")

                    # Save JSON summary with metadata
                    json_data = {
                        "filename": full_path.name,
                        "doc_type": doc_type,
                        "workflow": guess_workflow(doc_type),
                        "summary": summary,
                        "meta": extract_basic_meta(text),
                    }
                    json_path.write_text(
                        json.dumps(json_data, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )

                    # Save a copy of the original file (avoid collisions)
                    extracted_copy_path = _unique_target_path(EXTRACTED_DIR, full_path.name)
                    shutil.copy2(full_path, extracted_copy_path)

                    print(f"Saved: {txt_path.name} and {json_path.name}")

                except Exception as e:
                    print(f"Error processing {full_path.name}: {e}")


def guess_workflow(doc_type: str) -> str:
    """Simple mapping from document type to workflow name."""
    mapping = {
        "PJ": "Oude Pro Justitia rapportage",
        "VC": "VC Samenvatter",
        "PV": "PV Samenvatter",
        "RECLASS": "Reclasseringsrapport",
        "TLL": "TLL Generator (obv vordering IBS)",
        "UJD": "Uittreksel Samenvatter",
        "UNKNOWN": "Standaard Samenvatting",
    }
    return mapping.get(doc_type, "Standaard Samenvatting")


def extract_basic_meta(text: str) -> dict:
    """
    Very simple rule-based metadata extraction.
    Can be replaced by an LLM later if needed.
    """
    meta = {}

    m = re.search(r"(?:Verdachte|Betrokkene|Persoon):?\s*(.+)", text, re.IGNORECASE)
    meta["verdachte"] = m.group(1).strip() if m else ""

    m = re.search(r"Geboortedatum:?\s*([\d\-\.]{8,12})", text, re.IGNORECASE)
    meta["geboortedatum"] = m.group(1).strip() if m else ""

    m = re.search(r"Delict:?\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
    meta["delict"] = m.group(1).strip() if m else ""

    m = re.search(r"Advies:?\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
    meta["advies"] = m.group(1).strip() if m else ""

    m = re.search(r"Risico(?:-inschatting)?:?\s*(Hoog|Midden|Laag)", text, re.IGNORECASE)
    meta["risico"] = m.group(1).capitalize() if m else ""

    return meta
