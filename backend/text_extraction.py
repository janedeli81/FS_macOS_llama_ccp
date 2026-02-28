# backend/text_extraction.py

from __future__ import annotations

from pathlib import Path
from typing import Optional, List
import re
import os

import docx
import pdfplumber


def extract_text(path: Path) -> Optional[str]:
    """
    Read text content from .docx, .pdf, or .txt file.
    Returns None if file format is unsupported.
    """
    suffix = path.suffix.lower()
    if suffix == ".docx":
        text = _extract_docx(path)
    elif suffix == ".pdf":
        text = _extract_pdf(path)
    elif suffix in {".txt", ".md"}:
        text = path.read_text(encoding="utf-8", errors="ignore")
    else:
        return None
    return _sanitize(text)


def _extract_docx(path: Path) -> str:
    doc = docx.Document(path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def _extract_pdf(path: Path) -> str:
    """
    Extract text from PDF.

    We add explicit page markers. This improves:
    - chunk boundaries
    - chronological ordering in PVs
    - traceability when the user cross-checks the source

    We also apply very light dehyphenation for common PDF line-wrap patterns.

    Optional OCR fallback:
    - Enable with FS_OCR=1 (or true/yes/on)
    - Requires pytesseract + Pillow and system tesseract installed
    """
    text_parts: List[str] = []

    # Optional OCR fallback for scanned/screenshot-heavy PDFs.
    # Enabled only when FS_OCR=1/true/yes/on.
    use_ocr = os.environ.get("FS_OCR", "").strip().lower() in {"1", "true", "yes", "on"}
    ocr_min_chars = int(os.environ.get("FS_OCR_MIN_CHARS", "40"))
    ocr_lang = os.environ.get("FS_OCR_LANG", "nld+eng").strip() or "nld+eng"
    tesseract_cmd = os.environ.get("FS_TESSERACT_CMD", "").strip()

    pytesseract = None
    if use_ocr:
        try:
            import pytesseract as _pytesseract  # type: ignore
            pytesseract = _pytesseract
            if tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        except Exception:
            # If OCR deps are missing, silently disable OCR.
            pytesseract = None
            use_ocr = False

    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            page_text = (page.extract_text() or "").strip()

            # If page text is empty/too short, try OCR when enabled.
            # This is critical for PDFs that contain screenshots (WhatsApp, bank overviews, photos).
            used_ocr = False
            if use_ocr:
                stripped_len = len(re.sub(r"\s+", "", page_text))
                if stripped_len < ocr_min_chars:
                    ocr_text = ""
                    if pytesseract is not None:
                        try:
                            # pdfplumber renders pages to PIL.Image under the hood.
                            img = page.to_image(resolution=200).original
                            ocr_text = (pytesseract.image_to_string(img, lang=ocr_lang) or "").strip()
                        except Exception:
                            ocr_text = ""
                    if ocr_text:
                        page_text = ocr_text
                        used_ocr = True

            if not page_text:
                continue

            # Light dehyphenation: join words split as "wo-\nord".
            page_text = re.sub(r"(?<=\w)-\n(?=\w)", "", page_text)

            marker = f"=== PAGINA {i}{' (OCR)' if used_ocr else ''} ==="
            text_parts.append(f"\n\n{marker}\n{page_text}\n")

    return "\n".join(text_parts)


def _sanitize(text: str) -> str:
    t = text or ""
    t = re.sub(r"\r\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r"Pagina\s+\d+\s+van\s+\d+\s*", "", t, flags=re.I)
    return t.strip()