# backend/text_extraction.py

from __future__ import annotations

from pathlib import Path
from typing import Optional, List
import re

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
    """
    text_parts: List[str] = []

    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            page_text = page_text.strip()
            if not page_text:
                continue

            # Light dehyphenation: join words split as "wo-\nord".
            page_text = re.sub(r"(?<=\w)-\n(?=\w)", "", page_text)

            text_parts.append(f"\n\n=== PAGINA {i} ===\n{page_text}\n")

    return "\n".join(text_parts)


def _sanitize(text: str) -> str:
    t = text or ""
    t = re.sub(r"\r\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r"Pagina\s+\d+\s+van\s+\d+\s*", "", t, flags=re.I)
    return t.strip()
