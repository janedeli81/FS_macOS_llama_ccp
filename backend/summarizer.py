# backend/summarizer.py

from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import List, Optional

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
]


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


def _load_template(doc_type: str) -> str:
    path = PROMPT_FILES.get(doc_type.upper()) or PROMPT_FILES["UNKNOWN"]
    return Path(path).read_text(encoding="utf-8")


def _mistral_instruct_prompt(system_msg: str, user_msg: str) -> str:
    """
    Mistral Instruct format.
    Works well with Mistral Instruct GGUF.
    """
    system_msg = (system_msg or "").strip()
    user_msg = (user_msg or "").strip()

    if system_msg:
        return f"<s>[INST] <<SYS>>\n{system_msg}\n<</SYS>>\n\n{user_msg} [/INST]"
    return f"<s>[INST] {user_msg} [/INST]"


def _wrap_user(template: str, body: str, max_sents: int = 4) -> str:
    return (
        template.strip()
        + "\n[TEKST]\n"
        + (body or "").strip()
        + "\n</TEKST>\n"
        + f"Geef maximaal {max_sents} zinnen."
    )


def _get_llm():
    """
    Load GGUF model via llama-cpp-python.

    Stability-first:
    - serialize init + inference with _LLM_LOCK
    - default threads=1 on macOS (config)
    - default mmap disabled on macOS (config)
    """
    global _llm

    with _LLM_LOCK:
        if _llm is not None:
            return _llm

        try:
            from llama_cpp import Llama  # type: ignore
        except Exception as e:
            raise RuntimeError(
                "llama-cpp-python is not installed. Add it to requirements and remove ctransformers."
            ) from e

        mp = Path(str(MODEL_PATH))
        if not mp.exists():
            raise FileNotFoundError(f"LLM model not found: {mp}")

        # Print llama.cpp build/system info (helps confirm Metal backend in logs)
        try:
            from llama_cpp import llama_print_system_info  # type: ignore
            if bool(LCPP_VERBOSE):
                llama_print_system_info()
        except Exception:
            pass

        # IMPORTANT:
        # Keep n_gpu_layers=0 by default for packaged mac builds unless you tested Metal carefully.
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
    """
    Single entry point for inference. Must be locked to avoid concurrent ggml execution.
    """
    llm = _get_llm()
    with _LLM_LOCK:
        res = llm(
            prompt,
            max_tokens=int(max_new or MAX_NEW_TOKENS),
            temperature=0.2,
            top_p=0.9,
            repeat_penalty=1.15,
            stop=STOP_WORDS,
        )
    return (res["choices"][0]["text"] or "").strip()


def _clean_echo(txt: str) -> str:
    t = (txt or "").strip()
    t = re.sub(r"(?i)^\s*je bent.*?\n", "", t)
    t = re.sub(r"(?i)(\bje bent\b[\s,;:.!?]*){2,}", "Je bent ", t)
    return t.strip()


def _reduce_group(summaries: List[str], system_msg: str) -> str:
    user = (
        "Vat de volgende deelsamenvattingen samen tot één tekst van max. 4 zinnen.\n\n"
        + "\n\n".join(f"— {i + 1}. {t}" for i, t in enumerate(summaries))
    )
    prompt = _mistral_instruct_prompt(system_msg, user)
    return _generate(prompt).strip()


def summarize_document(
    doc_type: str,
    doc_text: Optional[str] = None,
    **kwargs,
) -> str:
    """
    MAP: summarize chunks
    REDUCE: hierarchical aggregation
    """
    if doc_text is None:
        doc_text = kwargs.get("text") or kwargs.get("document_text") or ""

    template = _load_template(doc_type)
    text = _sanitize(doc_text)

    # Special trimming for TLL: drop everything after "Overwegende"
    if doc_type.upper() == "TLL":
        m = re.search(r"(?i)\bOverwegende\b", text)
        if m:
            text = text[: m.start()].strip()

    chunks = _chunk(text, MAX_CHARS_PER_CHUNK)
    if not chunks:
        return "Geen tekst aangetroffen."

    system_msg = "Schrijf een korte, professionele samenvatting in het Nederlands."

    partials: List[str] = []
    for ch in chunks:
        user_msg = _wrap_user(template, ch, max_sents=4)
        prompt = _mistral_instruct_prompt(system_msg, user_msg)

        out = _generate(prompt)
        partials.append(_clean_echo(out))

    if len(partials) > AGGREGATE_MAX_PARTIALS:
        partials = partials[:AGGREGATE_MAX_PARTIALS]

    while len(partials) > 1:
        grouped: List[str] = []
        for i in range(0, len(partials), AGGREGATE_GROUP_SIZE):
            grouped.append(_reduce_group(partials[i : i + AGGREGATE_GROUP_SIZE], system_msg))
        partials = grouped

    return partials[0] if partials else ""
