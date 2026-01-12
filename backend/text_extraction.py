# backend/text_extraction.py

from pathlib import Path
from typing import Optional
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
    text_parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n".join(text_parts)


def _sanitize(text: str) -> str:
    t = text or ""
    t = re.sub(r"\r\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r"Pagina\s+\d+\s+van\s+\d+\s*", "", t, flags=re.I)
    return t.strip()
