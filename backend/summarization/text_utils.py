# backend/summarization/text_utils.py

from __future__ import annotations

import re
from typing import List, Optional


def sanitize(s: str) -> str:
    t = (s or "").replace("\r\n", "\n")

    # Common boilerplate
    t = re.sub(r"(?i)\bPagina\s+\d+\s+van\s+\d+\s*", "", t)
    t = re.sub(r"(?im)^\s*Retouradres.*$", "", t)

    # Remove accidental markdown emphasis
    t = t.replace("**", "")

    # Normalize whitespace
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def chunk(text: str, max_chars: int) -> List[str]:
    t = (text or "").strip()
    if not t:
        return []

    out: List[str] = []
    i, n = 0, len(t)

    while i < n:
        end = min(i + max_chars, n)
        piece = t[i:end]

        j = piece.rfind("\n")
        if j > int(max_chars * 0.6):
            end = i + j

        if end <= i:
            end = min(i + max_chars, n)

        chunk_text = t[i:end].strip()
        if chunk_text:
            out.append(chunk_text)

        i = end

    return out


def strip_pv_boilerplate(text: str) -> str:
    """Remove PV boilerplate blocks that harm summarization quality."""
    if not text:
        return ""

    drop_line_patterns = [
        r"\binformatie\s+over\s+dit\s+document\b",
        r"\belektronisch\s+ondertekend\b",
        r"\beidas\b",
        r"\bhttps?://validatie\.nl\b|\bvalidatie\.nl\b",
        r"\bslachtofferrechten\b",
        r"\bmijnslachtofferzaak\.nl\b|\bmijnslachtofferzaak\b",
        r"\bslachtofferhulp\b",
        r"^form\.nr:",
        r"\bdocumentkenmerk\b",
        r"\bpolitieprocesdossier\.pdf\b",
        r"\bpagina\s+\d+\s+van\s+\d+\b",
        r"\bproces-verbaalnummer\b",
        r"\bdit\s+proces-verbaal\s+is\s+door\s+mij\s+opgemaakt\b",
        r"\bop\s+ambtseed\b|\bop\s+ambtsbelofte\b",
    ]

    drop_re = re.compile("|".join(drop_line_patterns), flags=re.IGNORECASE)

    out_lines = []
    for ln in (text or "").splitlines():
        s = ln.strip()
        if not s:
            continue

        if drop_re.search(s):
            continue

        # Drop pure BIN noise lines (often irrelevant for content)
        if re.search(r"\bBIN\d{6,}\b", s, flags=re.IGNORECASE):
            continue

        out_lines.append(ln)

    cleaned = "\n".join(out_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def compact_pv_qa(text: str) -> str:
    """Compress Q/A verhoor sections, keeping only substantive content."""
    if not text:
        return ""

    keep_keywords = [
        "zaakinhoudelijk",
        "mishandeling",
        "steek",
        "letsel",
        "camerabeelden",
        "video",
        "seh",
        "spoedeisende",
        "ziekenhuis",
        "huisarts",
        "bewustzijn",
        "wekadvies",
        "alcohol",
        "drugs",
        "coke",
        "coca",
        "promille",
        "schulden",
        "tikkie",
    ]
    drop_keywords = [
        "wat is jouw naam",
        "geboortedatum",
        "woonadres",
        "telefoonnummer",
        "postcode",
        "advocaat",
        "consultatie",
        "verhoorbijstand",
        "folder",
        "rechten verdachte",
        "verificatie personalia",
        "identiteitskaart",
        "degene die de vraag stelde",
        "dit verhoor vind plaats",
    ]

    lines = [ln.rstrip() for ln in text.splitlines()]
    out: List[str] = []
    in_zaak = False

    for ln in lines:
        s = ln.strip()
        if not s:
            continue

        if re.search(r"(?i)\bzaakinhoudelijk\s+verhoor\b", s):
            in_zaak = True
            out.append(s)
            continue

        # Remove empty Q/A markers
        if re.match(r"(?i)^(v|a|o|0)\s*:\s*$", s):
            continue

        # Always drop obvious procedure/personal lines
        if any(k in s.lower() for k in drop_keywords):
            continue

        # If we are before the substantive part, keep only highly relevant lines
        if not in_zaak:
            if any(k in s.lower() for k in keep_keywords):
                out.append(s)
            continue

        # In substantive part: keep most, but still drop pure headers/forms
        if re.search(r"(?i)^form\.nr:|^proces-verbaalnummer", s):
            continue

        out.append(s)

    compacted = "\n".join(out)
    compacted = re.sub(r"\n{3,}", "\n\n", compacted)
    return compacted.strip()


_RE_QA_PREFIX = re.compile(r"(?i)^\s*(v\.?|a\.?|vraag|antw(?:oord)?)\s*[:\-]\s+\S")


def is_pv_qa_verhoor(text: str) -> bool:
    """Heuristic detector for PV Q/A verhoor transcripts.

    Why this exists:
    - Some PVs are not Q/A transcripts (e.g., 'onderzoek telefoon', 'bevindingen').
    - Applying `compact_pv_qa()` blindly can remove important narrative content.
    """
    t = (text or "").strip()
    if not t:
        return False

    if re.search(r"(?i)\bzaakinhoudelijk\s+verhoor\b", t):
        return True

    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    if not lines:
        return False

    # Limit scanning to keep it fast on very large PVs.
    sample = lines[:2000]
    qa_hits = sum(1 for ln in sample if _RE_QA_PREFIX.match(ln))

    # Typical verhoor transcripts have frequent V:/A: lines.
    if qa_hits >= 12:
        return True
    if len(sample) >= 200 and qa_hits >= 6 and (qa_hits / max(1, len(sample))) >= 0.02:
        return True

    return False


def compact_pv_qa_if_needed(text: str) -> str:
    """Apply Q/A compaction only when the PV looks like a verhoor transcript."""
    if is_pv_qa_verhoor(text):
        return compact_pv_qa(text)
    return (text or "").strip()


def _is_numeric_heavy_line(line: str) -> bool:
    """Return True for lines that look like transaction tables / number dumps."""
    s = (line or "").strip()
    if not s:
        return False

    # Never treat page markers as numeric runs.
    if s.startswith("=== PAGINA"):
        return False

    digits = sum(ch.isdigit() for ch in s)
    letters = sum(ch.isalpha() for ch in s)

    # Strong signals for exports / tables.
    if digits >= 12 and digits > (letters * 1.2):
        return True

    # IBAN / account numbers and long numeric sequences.
    if re.search(r"(?i)\bIBAN\b|\brekening\b|\brekeningnummer\b", s) and digits >= 8:
        return True

    # Long lines with dates + many digits are often table rows.
    if re.search(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b", s) and digits >= 10 and letters <= 20:
        return True

    return False


def compact_numeric_runs(
    text: str,
    *,
    min_block_lines: int = 10,
    keep_head: int = 6,
    keep_tail: int = 4,
) -> str:
    """Compress long numeric/table-like blocks while preserving context."""
    if not text:
        return ""

    lines = text.splitlines()
    out: List[str] = []
    i = 0
    n = len(lines)

    while i < n:
        if _is_numeric_heavy_line(lines[i]):
            j = i
            while j < n and _is_numeric_heavy_line(lines[j]):
                j += 1

            block = [ln.rstrip() for ln in lines[i:j] if ln.strip()]
            if len(block) >= min_block_lines:
                head = block[:keep_head]
                tail = block[-keep_tail:] if keep_tail > 0 else []
                omitted = max(0, len(block) - len(head) - len(tail))
                out.extend(head)
                if omitted > 0:
                    out.append(f"[...] {omitted} regels met transactie-/cijfergegevens weggelaten [...]")
                    out.extend(tail)
            else:
                out.extend(block)

            i = j
            continue

        out.append(lines[i].rstrip())
        i += 1

    compacted = "\n".join(out)
    compacted = re.sub(r"\n{3,}", "\n\n", compacted)
    return compacted.strip()


def extract_tll_relevant(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return t

    start_patterns = [
        r"(?i)\bervan\s+verdacht\s+wordt\s*,?\s*dat\b",
        r"(?i)\btenlastelegging\b",
        r"(?i)\bten\s+laste\s+gelegd\b",
        r"(?i)\bwordt\s+verdacht\s+van\b",
        r"(?i)\bde\s+verdenking\s+is\s+dat\b",
        r"(?i)\bverdenking\b",
    ]

    start_idx: Optional[int] = None
    for pat in start_patterns:
        m = re.search(pat, t)
        if m:
            start_idx = m.start()
            break

    seg = t[start_idx:] if start_idx is not None else t

    end_patterns = [
        r"(?i)\boverwegende\b",
        r"(?i)\bartikelen\b",
        r"(?i)\bartikel\b",
        r"(?i)\bgelet\s+op\b",
        r"(?i)\baldus\b",
        r"(?i)\bondertekend\b",
        r"(?i)\bhandtekening\b",
    ]

    for pat in end_patterns:
        m = re.search(pat, seg)
        if m and m.start() > 300:
            seg = seg[: m.start()]
            break

    return seg.strip()


def extract_ujd_relevant(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return t

    headings = [
        r"(?i)\bopenstaande\s+zaken\s+betreffende\s+misdrijven\b",
        r"(?i)\bvolledig\s+afgedane\s+zaken\s+betreffende\s+misdrijven\b",
        r"(?i)\buittreksel\s+(van\s+)?justitiele\s+documentatie\b",
    ]
    for pat in headings:
        m = re.search(pat, t)
        if m:
            return t[m.start() :].strip()

    return t