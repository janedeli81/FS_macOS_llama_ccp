# backend/summarization/prompts.py

from __future__ import annotations

from pathlib import Path
from typing import Tuple

from backend.config import PROMPT_FILES


def mistral_inst(system_msg: str, user_msg: str) -> str:
    sys = (system_msg or "").strip()
    usr = (user_msg or "").strip()
    if sys:
        return f"<s>[INST] {sys}\n\n{usr} [/INST]"
    return f"<s>[INST] {usr} [/INST]"


def load_templates(doc_type: str) -> Tuple[str, str]:
    """Load MAP and REDUCE templates from a single prompt file."""
    path = PROMPT_FILES.get((doc_type or "").upper()) or PROMPT_FILES["UNKNOWN"]
    txt = Path(path).read_text(encoding="utf-8", errors="ignore")
    txt = txt.replace("\r\n", "\n")

    sep = "\n---REDUCE---\n"
    if sep in txt:
        map_tpl, reduce_tpl = txt.split(sep, 1)
        return map_tpl.strip(), reduce_tpl.strip()
    return txt.strip(), ""


def wrap_user(template: str, body: str, *, extra: str = "") -> str:
    msg = template.strip() + "\n\n[TEKST]\n" + (body or "").strip() + "\n</TEKST>\n"
    if extra:
        msg += "\n" + extra.strip()
    return msg


def count_tokens_rough(s: str) -> int:
    # Rough estimator; safe guard for ctx
    return max(1, int(len(s) / 3.6))


def fit_prompt_to_ctx(
    system_msg: str,
    template: str,
    body: str,
    target_ctx: int,
    *,
    extra: str = "",
) -> str:
    ch = (body or "").strip()
    limit = max(700, int(target_ctx * 0.86))

    while True:
        user_msg = wrap_user(template, ch, extra=extra)
        prompt = mistral_inst(system_msg, user_msg)
        if count_tokens_rough(prompt) <= limit or len(ch) < 600:
            return prompt
        ch = ch[: int(len(ch) * 0.88)].strip()