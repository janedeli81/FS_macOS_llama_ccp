# backend/summarization/output_utils.py

from __future__ import annotations

import re
from typing import List


def clean_output(txt: str) -> str:
    t = (txt or '').strip()

    # Remove common intros
    t = re.sub(r'(?is)^\s*(hier(onder)?\s+)?(volgt|staat)\s+(de\s+)?samenvatting\s*:?[\s]*', '', t)
    t = re.sub(r'(?is)^\s*samenvatting\s*:?[\s]*', '', t)

    # Remove prompt/task lines
    t = re.sub(r'(?im)^\s*haal\s+diep\s+adem.*$', '', t)
    t = re.sub(r'(?im)^\s*werk\s+stapsgewijs.*$', '', t)
    t = re.sub(r'(?im)^\s*dit\s+is\s+een\s+samenvatting.*$', '', t)
    t = re.sub(r'(?im)^\s*deze\s+samenvatting\s+is\s+gebaseerd\s+op.*$', '', t)

    # Remove tag echoes
    t = re.sub(r'(?im)^\s*\[TEKST\]\s*$', '', t)
    t = re.sub(r'(?im)^\s*</TEKST>\s*$', '', t)
    t = re.sub(r'(?im)^\s*DEELSAMENVATTINGEN?\s*:?[\s]*$', '', t)

    # Remove chat markers
    t = t.replace('<|assistant|>', '').replace('<|user|>', '').replace('<|system|>', '')
    t = t.replace('[INST]', '').replace('[/INST]', '')

    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()


def normalize_bullets(txt: str) -> str:
    t = clean_output(txt)
    if not t:
        return ''

    lines = [ln.rstrip() for ln in t.splitlines()]
    out: List[str] = []

    for ln in lines:
        s = ln.strip()
        if not s:
            continue

        # Skip obvious headers
        if re.fullmatch(r'(?i)(deel-)?samenvatting\s*:?', s):
            continue
        if re.fullmatch(r'(?i)eind(tekst|verslag)\s*:?', s):
            continue

        # Normalize bullet prefix
        if re.match(r'^[-*•]\s+', s):
            out.append('- ' + re.sub(r'^[-*•]\s+', '', s))
        elif re.match(r'^\d+[).]\s+', s):
            out.append('- ' + re.sub(r'^\d+[).]\s+', '', s))
        elif s.startswith('— '):
            out.append('- ' + s[2:].strip())
        else:
            out.append('- ' + s)

    return '\n'.join(out).strip()


def normalize_reduce_text(txt: str) -> str:
    t = clean_output(txt)
    if not t:
        return ''

    t = re.sub(r'(?im)^\s*eind(tekst|verslag)\s*:?[\s]*', '', t).strip()
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()