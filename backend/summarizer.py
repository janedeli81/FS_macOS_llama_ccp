# backend/summarizer.py
# All comments are intentionally in English (project convention).

from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from backend.config import (
    PROMPT_FILES,
    MAX_CHARS_PER_CHUNK,
    MODEL_PATH,
    N_CTX,
    MAX_NEW_TOKENS,
    AGGREGATE_GROUP_SIZE,
    AGGREGATE_MAX_PARTIALS,
    LCPP_THREADS,
    LCPP_BATCH,
    LCPP_GPU_LAYERS,
    LCPP_USE_MMAP,
    LCPP_USE_MLOCK,
    LCPP_VERBOSE,
)

# -----------------------------------------------------------------------------
# Runtime overrides (useful for prompt testing)
# -----------------------------------------------------------------------------
#   FS_FAST_MODE=1              -> summarize only first chunks (fast)
#   FS_FAST_MAX_CHUNKS=1        -> number of chunks to process in fast mode
#   FS_MAP_MAX_NEW=140          -> max tokens for MAP step
#   FS_REDUCE_MAX_NEW=260       -> max tokens for REDUCE step
#   FS_TEMPERATURE=0            -> deterministic output for A/B prompt tests
#   FS_TOP_P=1
#   FS_REPETITION_PENALTY=1.15
FAST_MODE = os.getenv("FS_FAST_MODE", "0").strip() == "1"
FAST_MAX_CHUNKS = int(os.getenv("FS_FAST_MAX_CHUNKS", "1"))
MAP_MAX_NEW = int(os.getenv("FS_MAP_MAX_NEW", str(MAX_NEW_TOKENS)))
REDUCE_MAX_NEW = int(os.getenv("FS_REDUCE_MAX_NEW", str(max(220, MAX_NEW_TOKENS))))
TEMPERATURE = float(os.getenv("FS_TEMPERATURE", "0.2"))
TOP_P = float(os.getenv("FS_TOP_P", "0.9"))
REPETITION_PENALTY = float(os.getenv("FS_REPETITION_PENALTY", "1.15"))

# Global singleton model instance (process-wide)
_llm = None

# Hard lock to prevent concurrent inference / init (ggml/llama.cpp is not safely re-entrant)
_LLM_LOCK = threading.Lock()

STOP_WORDS = [
    "</TEKST>",
    "</TEKST_WAAR_HET_OM_GAAT>",
    "JOUW ANTWOORD:",
    "JOUW ANTWOORD",
    "[TEKST_OM_SAMEN_TE_VATTEN]",
    "<|user|>",
    "<|system|>",
    "<|assistant|>",
]

# -----------------------------------------------------------------------------
# Helpers (text)
# -----------------------------------------------------------------------------

def _count_tokens_rough(s: str) -> int:
    """Rough token estimator to avoid ctx overflow."""
    return max(1, int(len(s) / 3.6))


def _sanitize(s: str) -> str:
    s = (s or "").replace("\r\n", "\n")
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"(?i)Pagina\s+\d+\s+van\s+\d+\s*", "", s)
    s = re.sub(r"(?im)^\s*Retouradres.*$", "", s)
    s = s.replace("**", "")
    return s.strip()


def _chunk(text: str, max_chars: int) -> List[str]:
    t = (text or "").strip()
    if not t:
        return []
    out: List[str] = []
    i, n = 0, len(t)
    while i < n:
        piece = t[i : i + max_chars]
        j = piece.rfind("\n")
        if j > int(max_chars * 0.6):
            piece = piece[:j]
        out.append(piece.strip())
        i += len(piece)
    return out


def _load_templates(doc_type: str) -> Tuple[str, str]:
    """Load MAP and REDUCE templates from a single prompt file."""
    path = PROMPT_FILES.get(doc_type.upper()) or PROMPT_FILES["UNKNOWN"]
    txt = Path(path).read_text(encoding="utf-8")

    sep = "\n---REDUCE---\n"
    if sep in txt:
        map_tpl, reduce_tpl = txt.split(sep, 1)
        return map_tpl.strip(), reduce_tpl.strip()

    return txt.strip(), ""


def _wrap_user(template: str, body: str, extra: str = "") -> str:
    """Wrap the source text with clear delimiters."""
    msg = (
        template.strip()
        + "\n[TEKST]\n"
        + (body or "").strip()
        + "\n</TEKST>\n"
    )
    if extra:
        msg += "\n" + extra.strip()
    return msg


def _clean_echo(txt: str) -> str:
    """Remove common prompt-echo artifacts."""
    t = (txt or "").strip()
    t = re.sub(r"(?i)^\s*je bent.*?\n", "", t)
    t = re.sub(r"(?i)(\bje bent\b[\s,;:.!?]*){2,}", "Je bent ", t)
    return t.strip()


# -----------------------------------------------------------------------------
# Prompt format (Mistral Instruct)
# -----------------------------------------------------------------------------

def _mistral_instruct_prompt(system_msg: str, user_msg: str) -> str:
    """Mistral Instruct format (GGUF)."""
    system_msg = (system_msg or "").strip()
    user_msg = (user_msg or "").strip()

    if system_msg:
        return f"<s>[INST] <<SYS>>\n{system_msg}\n<</SYS>>\n\n{user_msg} [/INST]"
    return f"<s>[INST] {user_msg} [/INST]"


def _fit_user_to_ctx(
    system_msg: str,
    template: str,
    body: str,
    target_ctx: int,
    extra: str = "",
) -> str:
    """Shrink the body until the rough token estimate fits into the target context."""
    ch = (body or "").strip()
    limit = max(256, int(target_ctx * 0.90))

    while True:
        user_msg = _wrap_user(template, ch, extra=extra)
        prompt = _mistral_instruct_prompt(system_msg, user_msg)

        if _count_tokens_rough(prompt) <= limit or len(ch) < 200:
            return prompt

        ch = ch[: int(len(ch) * 0.85)]


# -----------------------------------------------------------------------------
# Model loader (llama-cpp-python)
# -----------------------------------------------------------------------------

def _get_llm():
    """Load GGUF model via llama-cpp-python."""
    global _llm

    with _LLM_LOCK:
        if _llm is not None:
            return _llm

        try:
            from llama_cpp import Llama  # type: ignore
        except Exception as e:
            raise RuntimeError("llama-cpp-python is not installed.") from e

        mp = Path(str(MODEL_PATH))
        if not mp.exists():
            raise FileNotFoundError(f"LLM model not found: {mp}")

        # Optional: print llama.cpp build info for debugging (Metal, etc.)
        try:
            from llama_cpp import llama_print_system_info  # type: ignore
            if bool(LCPP_VERBOSE):
                llama_print_system_info()
        except Exception:
            pass

        _llm = Llama(
            model_path=str(mp),
            n_ctx=int(N_CTX),
            n_threads=int(LCPP_THREADS),
            n_batch=int(LCPP_BATCH),
            n_gpu_layers=int(LCPP_GPU_LAYERS),
            use_mmap=bool(LCPP_USE_MMAP),
            use_mlock=bool(LCPP_USE_MLOCK),
            verbose=bool(LCPP_VERBOSE),
        )

        print(
            "[summarizer] llama.cpp model loaded:"
            f" path={mp} ctx={int(N_CTX)} threads={int(LCPP_THREADS)}"
            f" batch={int(LCPP_BATCH)} gpu_layers={int(LCPP_GPU_LAYERS)}"
            f" mmap={'on' if LCPP_USE_MMAP else 'off'} mlock={'on' if LCPP_USE_MLOCK else 'off'}"
        )

        return _llm


def _generate(prompt: str, *, max_new: Optional[int] = None) -> str:
    """Single entry point for inference."""
    llm = _get_llm()
    with _LLM_LOCK:
        res = llm(
            prompt,
            max_tokens=int(max_new or MAX_NEW_TOKENS),
            temperature=TEMPERATURE,
            top_p=TOP_P,
            repeat_penalty=REPETITION_PENALTY,
            stop=STOP_WORDS,
        )
    return (res["choices"][0]["text"] or "").strip()


def _reduce_group(
    summaries: List[str],
    system_msg: str,
    target_ctx: int,
    reduce_template: str,
    extra: str = "",
) -> str:
    """Reduce a group of partial MAP outputs into a single text."""
    header = reduce_template.strip() if reduce_template.strip() else (
        "Combineer de onderstaande deelsamenvattingen tot één professionele tekst."
    )

    def build_user(items: List[str]) -> str:
        user_msg = (
            header
            + "\n\n[DEELSAMENVATTINGEN]\n"
            + "\n\n".join(f"— {i + 1}. {t}" for i, t in enumerate(items))
            + "\n</DEELSAMENVATTINGEN>\n"
        )
        if extra:
            user_msg += "\n" + extra.strip()
        return user_msg

    items = list(summaries)
    user = build_user(items)
    prompt = _mistral_instruct_prompt(system_msg, user)

    # If it does not fit ctx, reduce the group size.
    while _count_tokens_rough(prompt) > int(target_ctx * 0.90) and len(items) > 1:
        items = items[: max(1, len(items) // 2)]
        user = build_user(items)
        prompt = _mistral_instruct_prompt(system_msg, user)

    return _clean_echo(_generate(prompt, max_new=REDUCE_MAX_NEW))


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

def summarize_document(
    doc_type: str,
    doc_text: Optional[str] = None,
    **kwargs,
) -> str:
    """Summarize a document using MAP -> REDUCE (hierarchical aggregation)."""
    if doc_text is None:
        doc_text = kwargs.get("text") or kwargs.get("document_text") or ""

    progress_cb: Optional[Callable[[str], None]] = kwargs.get("progress_callback")

    def emit(msg: str) -> None:
        if callable(progress_cb):
            try:
                progress_cb(msg)
            except Exception:
                pass

    map_template, reduce_template = _load_templates(doc_type)
    text = _sanitize(doc_text)

    # Special trimming for TLL: drop everything after "Overwegende"
    if doc_type.upper() == "TLL":
        m = re.search(r"(?i)\bOverwegende\b", text)
        if m:
            text = text[: m.start()].strip()

    chunks = _chunk(text, MAX_CHARS_PER_CHUNK)
    if not chunks:
        return "Geen tekst aangetroffen."

    if FAST_MODE:
        chunks = chunks[: max(1, FAST_MAX_CHUNKS)]

    system_msg = (
        "Je schrijft in het Nederlands. "
        "Volg de instructies strikt, gebruik uitsluitend informatie uit de tekst, en verzin niets."
    )

    partials: List[str] = []
    total = len(chunks)

    # MAP step
    for i, ch in enumerate(chunks, start=1):
        emit(f"Summarizing chunk {i}/{total}...")
        prompt = _fit_user_to_ctx(system_msg, map_template, ch, int(N_CTX))
        out = _generate(prompt, max_new=MAP_MAX_NEW)
        partials.append(_clean_echo(out))

    if len(partials) > AGGREGATE_MAX_PARTIALS:
        partials = partials[:AGGREGATE_MAX_PARTIALS]

    # REDUCE step (hierarchical)
    round_idx = 0
    while len(partials) > 1:
        round_idx += 1
        emit(f"Combining partial summaries (round {round_idx})...")

        grouped: List[str] = []
        for i in range(0, len(partials), AGGREGATE_GROUP_SIZE):
            group = partials[i : i + AGGREGATE_GROUP_SIZE]
            grouped.append(_reduce_group(group, system_msg, int(N_CTX), reduce_template))

        partials = grouped

    emit("Done.")
    return partials[0] if partials else ""
