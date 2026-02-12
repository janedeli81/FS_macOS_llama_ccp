# backend/summarizer.py
# All comments are intentionally in English (project convention).

from __future__ import annotations

import os
import re
import time
import threading
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from backend.config import (
    PROMPT_FILES,
    MAX_CHARS_PER_CHUNK,
    N_CTX,
    MAX_NEW_TOKENS,
    AGGREGATE_GROUP_SIZE,
    AGGREGATE_MAX_PARTIALS,
)

# Optional: model_manager can later be swapped from download -> decrypt runtime.
try:
    from backend.model_manager import ensure_model_ready  # type: ignore
except Exception:
    ensure_model_ready = None  # type: ignore

# Optional: fallback path resolver if model_manager is not available.
try:
    from backend.config import get_model_path  # type: ignore
except Exception:
    get_model_path = None  # type: ignore

# Optional llama.cpp tuning knobs (if present in macOS config).
try:
    from backend.config import (  # type: ignore
        LCPP_THREADS,
        LCPP_BATCH,
        LCPP_GPU_LAYERS,
        LCPP_USE_MMAP,
        LCPP_USE_MLOCK,
        LCPP_VERBOSE,
    )
except Exception:
    import platform

    # Auto-detect Apple Silicon for optimal GPU/CPU settings
    _is_apple_silicon = platform.machine() == "arm64" and platform.system() == "Darwin"
    _cpu_count = os.cpu_count() or 8

    if _is_apple_silicon:
        # Optimal settings for Apple Silicon (M1/M2/M3/M4)
        # Use physical cores only (Performance cores, typically half of total)
        LCPP_THREADS = int(os.getenv("FS_THREADS", str(max(4, _cpu_count // 2))))
        # Larger batch size works well with Metal GPU
        LCPP_BATCH = int(os.getenv("FS_BATCH_SIZE", "1024"))
        # Enable full Metal GPU acceleration (35 layers = all layers for Mistral-7B)
        LCPP_GPU_LAYERS = int(os.getenv("FS_GPU_LAYERS", "35"))
        print(f"[summarizer] Apple Silicon detected (Metal GPU enabled)")
    else:
        # Conservative defaults for Intel Mac / other platforms
        LCPP_THREADS = int(os.getenv("FS_THREADS", "8"))
        LCPP_BATCH = int(os.getenv("FS_BATCH_SIZE", "512"))
        LCPP_GPU_LAYERS = int(os.getenv("FS_GPU_LAYERS", "0"))
        print(f"[summarizer] Intel/other platform detected (CPU only)")

    LCPP_USE_MMAP = os.getenv("FS_USE_MMAP", "1").strip() != "0"
    LCPP_USE_MLOCK = os.getenv("FS_USE_MLOCK", "0").strip() == "1"
    LCPP_VERBOSE = os.getenv("FS_LCPP_VERBOSE", "0").strip() == "1"


# -----------------------------------------------------------------------------
# Runtime configuration (kept consistent with your Windows logic)
# -----------------------------------------------------------------------------
_llm: Optional[object] = None

# Hard lock to prevent concurrent init/inference (llama.cpp is not safely re-entrant in many builds).
_LLM_LOCK = threading.Lock()

STOP_WORDS = [
    "</s>",
    "<|assistant|>",
    "<|user|>",
    "<|system|>",
    "</TEKST>",
    "</TEKST_WAAR_HET_OM_GAAT>",
    "JOUW ANTWOORD:",
    "JOUW ANTWOORD",
]

FAST_MODE = os.getenv("FS_FAST_MODE", "0").strip() == "1"
FAST_MAX_CHUNKS = int(os.getenv("FS_FAST_MAX_CHUNKS", "1"))

MAP_MAX_NEW = int(os.getenv("FS_MAP_MAX_NEW", str(MAX_NEW_TOKENS)))
REDUCE_MAX_NEW = int(os.getenv("FS_REDUCE_MAX_NEW", str(max(420, MAX_NEW_TOKENS))))
REPAIR_MAX_NEW = int(os.getenv("FS_REPAIR_MAX_NEW", "520"))

TEMPERATURE = float(os.getenv("FS_TEMPERATURE", "0.0"))
TOP_P = float(os.getenv("FS_TOP_P", "1.0"))
REPETITION_PENALTY = float(os.getenv("FS_REPETITION_PENALTY", "1.08"))

ENABLE_REPAIR_PASS = os.getenv("FS_ENABLE_REPAIR_PASS", "1").strip() != "0"


# -----------------------------------------------------------------------------
# PII detection (post-check)
# -----------------------------------------------------------------------------
_RE_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_RE_PHONE = re.compile(r"\b(?:\+?\d[\d\s().-]{7,}\d)\b")
_RE_POSTCODE = re.compile(r"\b\d{4}\s?[A-Z]{2}\b", re.IGNORECASE)
_RE_BSN = re.compile(r"\b\d{9}\b")
_RE_PARKET = re.compile(r"\b\d{2}[./-]\d{6}[/-]\d{2}\b")
_RE_STREET = re.compile(
    r"\b[A-ZÀ-ÿ][\wÀ-ÿ .'-]{1,50}\s(?:straat|laan|weg|plein|dijk|kade|singel|hof|steeg|gracht|allee|pad|boulevard)\s+\d+[a-zA-Z]?\b",
    re.IGNORECASE,
)
_RE_AGE_PHRASE = re.compile(r"\b\d{1,3}\s*-\s*jarige\b", re.IGNORECASE)
_RE_AGE_WORD = re.compile(r"\b\d{1,3}\s*jarige\b", re.IGNORECASE)
_RE_DOB_CONTEXT = re.compile(r"(?i)\b(geboortedatum|geb\.?|geboren(?:\s+op)?|geboren te)\b")

_RE_INIT_SURNAME = re.compile(
    r"\b(?:[A-Z]\.){1,4}\s*[A-Z][a-zà-ÿ]+(?:[-\s][A-Z][a-zà-ÿ]+){0,2}\b"
)
_RE_CAP_NAME = re.compile(r"\b[A-Z][a-zà-ÿ]{2,}(?:\s+[A-Z][a-zà-ÿ]{2,}){1,3}\b")


# -----------------------------------------------------------------------------
# Model path resolution
# -----------------------------------------------------------------------------
def _resolve_model_path() -> Path:
    """
    Resolve an actual GGUF path.

    Priority (FIXED - encrypted model ALWAYS has highest priority):
    1) model_manager.ensure_model_ready() - encrypted model (HIGHEST PRIORITY)
    2) FS_MODEL_PATH env override - explicit user override
    3) backend.config.get_model_path() - fallback for old unencrypted model
    4) backend.config.MODEL_PATH - last resort

    CRITICAL: model_manager.ensure_model_ready() MUST be called FIRST
    to ensure encrypted model (.enc) is used instead of old unencrypted (.gguf) files
    that may exist in user's Application Support folder.
    """
    # 1) ENCRYPTED MODEL (ALWAYS FIRST!)
    # Try model_manager.ensure_model_ready() which handles encrypted .enc files.
    # This MUST be checked first, otherwise old unencrypted models will be used.
    if callable(ensure_model_ready):
        try:
            p = ensure_model_ready(progress_cb=None)  # type: ignore[arg-type]
            # Success - using encrypted model
            return Path(p)
        except FileNotFoundError:
            # Encrypted model not found - this is expected for users without .enc file
            # Fall through to check for unencrypted fallback
            print("[INFO] Encrypted model not found, checking for unencrypted fallback...")
        except Exception as e:
            # Unexpected error during decryption
            print(f"[WARNING] model_manager.ensure_model_ready() failed: {e}")
            print("[WARNING] Will try fallback to unencrypted model...")

    # 2) EXPLICIT ENV OVERRIDE
    # Allow user to explicitly specify a model path if they know what they're doing.
    override = os.environ.get("FS_MODEL_PATH", "").strip()
    if override:
        p = Path(override).expanduser()
        if p.exists() and p.stat().st_size > 10 * 1024 * 1024:
            print(f"[INFO] Using model from FS_MODEL_PATH override: {p}")
            return p
        print(f"[WARNING] FS_MODEL_PATH set but model not found or invalid: {p}")

    # 3) FALLBACK: UNENCRYPTED MODEL (for backward compatibility)
    # Only use this if encrypted model is not available.
    # WARNING: This may pick up OLD models from previous installations!
    if callable(get_model_path):
        try:
            p = Path(get_model_path())
            if p.exists() and p.stat().st_size > 10 * 1024 * 1024:
                print(f"[WARNING] Using UNENCRYPTED model (fallback): {p}")
                print("[WARNING] This may be an old version. Encrypted model is recommended.")
                return p
        except Exception as e:
            print(f"[WARNING] get_model_path() failed: {e}")

    # 4) LAST RESORT
    # Use MODEL_PATH from config as absolute last resort.
    try:
        from backend.config import MODEL_PATH
        p = Path(str(MODEL_PATH))
        print(f"[WARNING] Using MODEL_PATH (last resort): {p}")
        return p
    except Exception:
        # Should never happen, but handle gracefully
        raise RuntimeError(
            "Cannot resolve model path. No model found.\n"
            "Expected: encrypted model (.enc) next to application\n"
            "Or set: FS_MODEL_PATH environment variable"
        )


# -----------------------------------------------------------------------------
# Model loader (llama-cpp-python)
# -----------------------------------------------------------------------------
def get_llm() -> object:
    """Load GGUF via llama-cpp-python."""
    global _llm

    with _LLM_LOCK:
        if _llm is not None:
            return _llm

        try:
            from llama_cpp import Llama  # type: ignore
        except Exception as e:
            raise RuntimeError("llama-cpp-python is required on macOS build.") from e

        mp = _resolve_model_path()
        if not mp.exists():
            raise FileNotFoundError(f"LLM model not found: {mp}")

        # Optional: print llama.cpp build info (Metal, etc.)
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
    """
    Single entry point for inference.
    Returns plain text (choices[0].text).
    """
    llm = get_llm()
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


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _count_tokens_rough(s: str) -> int:
    # Rough estimator; safe guard for ctx
    return max(1, int(len(s) / 3.6))


def _sanitize(s: str) -> str:
    t = (s or "").replace("\r\n", "\n")

    # Common boilerplate
    t = re.sub(r"(?i)\bPagina\s+\d+\s+van\s+\d+\s*", "", t)
    t = re.sub(r"(?im)^\s*Retouradres.*$", "", t)

    # Remove accidental markdown emphasis
    t = t.replace("**", "")

    # Normalize whitespace
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _mistral_inst(system_msg: str, user_msg: str) -> str:
    sys_msg = (system_msg or "").strip()
    usr_msg = (user_msg or "").strip()
    sys_block = f"<<SYS>>\n{sys_msg}\n<</SYS>>\n\n" if sys_msg else ""
    return f"<s>[INST] {sys_block}{usr_msg} [/INST]"


def _chunk(text: str, max_chars: int) -> List[str]:
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


def _load_templates(doc_type: str) -> Tuple[str, str]:
    """
    Load MAP and REDUCE templates from a single prompt file.

    Supports both LF and CRLF around separator.
    """
    path = PROMPT_FILES.get((doc_type or "").upper()) or PROMPT_FILES["UNKNOWN"]
    txt = Path(path).read_text(encoding="utf-8", errors="ignore")
    txt = txt.replace("\r\n", "\n")

    sep = "\n---REDUCE---\n"
    if sep in txt:
        map_tpl, reduce_tpl = txt.split(sep, 1)
        return map_tpl.strip(), reduce_tpl.strip()
    return txt.strip(), ""


def _wrap_user(template: str, body: str, *, extra: str = "") -> str:
    msg = template.strip() + "\n\n[TEKST]\n" + (body or "").strip() + "\n</TEKST>\n"
    if extra:
        msg += "\n" + extra.strip()
    return msg


def _fit_prompt_to_ctx(
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
        user_msg = _wrap_user(template, ch, extra=extra)
        prompt = _mistral_inst(system_msg, user_msg)
        if _count_tokens_rough(prompt) <= limit or len(ch) < 600:
            return prompt
        ch = ch[: int(len(ch) * 0.88)].strip()


def _clean_output(txt: str) -> str:
    t = (txt or "").strip()

    # Remove common intros
    t = re.sub(r"(?is)^\s*(hier(onder)?\s+)?(volgt|staat)\s+(de\s+)?samenvatting\s*:?\s*", "", t)
    t = re.sub(r"(?is)^\s*samenvatting\s*:?\s*", "", t)

    # Remove prompt/task lines
    t = re.sub(r"(?im)^\s*haal\s+diep\s+adem.*$", "", t)
    t = re.sub(r"(?im)^\s*werk\s+stapsgewijs.*$", "", t)
    t = re.sub(r"(?im)^\s*dit\s+is\s+een\s+samenvatting.*$", "", t)
    t = re.sub(r"(?im)^\s*deze\s+samenvatting\s+is\s+gebaseerd\s+op.*$", "", t)

    # Remove tag echoes
    t = re.sub(r"(?im)^\s*\[TEKST\]\s*$", "", t)
    t = re.sub(r"(?im)^\s*</TEKST>\s*$", "", t)
    t = re.sub(r"(?im)^\s*DEELSAMENVATTINGEN?\s*:?\s*$", "", t)

    # Remove chat markers
    t = t.replace("<|assistant|>", "").replace("<|user|>", "").replace("<|system|>", "")
    t = t.replace("[INST]", "").replace("[/INST]", "")

    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _normalize_bullets(txt: str) -> str:
    t = _clean_output(txt)
    if not t:
        return ""

    lines = [ln.rstrip() for ln in t.splitlines()]
    out: List[str] = []

    for ln in lines:
        s = ln.strip()
        if not s:
            continue

        # Skip obvious headers
        if re.fullmatch(r"(?i)(deel-)?samenvatting\s*:?", s):
            continue
        if re.fullmatch(r"(?i)eind(tekst|verslag)\s*:?", s):
            continue

        # Normalize bullet prefix
        if re.match(r"^[-*•]\s+", s):
            out.append("- " + re.sub(r"^[-*•]\s+", "", s))
        elif re.match(r"^\d+[).]\s+", s):
            out.append("- " + re.sub(r"^\d+[).]\s+", "", s))
        elif s.startswith("— "):
            out.append("- " + s[2:].strip())
        else:
            out.append("- " + s)

    return "\n".join(out).strip()


def _normalize_reduce_text(txt: str) -> str:
    t = _clean_output(txt)
    if not t:
        return ""
    t = re.sub(r"(?im)^\s*eind(tekst|verslag)\s*:?\s*", "", t).strip()
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


# -----------------------------------------------------------------------------
# Doc-specific extraction helpers
# -----------------------------------------------------------------------------
def _extract_tll_relevant(text: str) -> str:
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


def _extract_ujd_relevant(text: str) -> str:
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
            return t[m.start():].strip()

    return t


# -----------------------------------------------------------------------------
# Post-processing / privacy / quality
# -----------------------------------------------------------------------------
def _scrub_names_best_effort(s: str) -> str:
    """
    Conservative scrub of obvious name patterns that leak through:
    - Initials + surname (A.B. Surname)
    - Capitalized full names in certain contexts
    """
    t = s or ""
    t = _RE_INIT_SURNAME.sub("betrokkene", t)

    # Replace "Betrokkene, <Naam>" patterns
    t = re.sub(
        r"(?im)\bbetrokkene[, ]+\b[A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+){0,3}\b",
        "betrokkene",
        t,
    )
    t = re.sub(
        r"(?im)\bbetrokkene\s+is\s+[A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+){0,3}\b",
        "betrokkene is betrokkene",
        t,
    )

    # Very conservative: scrub only if preceded by "naam:"
    t = re.sub(r"(?im)\bnaam\s*:\s*" + _RE_CAP_NAME.pattern, "naam: betrokkene", t)

    return t


def _dedupe_lines_and_paragraphs(s: str) -> str:
    """
    Remove exact duplicate lines and duplicate consecutive paragraphs.
    """
    if not s or not s.strip():
        return s

    # Line dedupe (keep order)
    lines = s.splitlines()
    seen = set()
    out_lines = []
    for ln in lines:
        key = ln.strip()
        if not key:
            out_lines.append(ln)
            continue
        if key in seen:
            continue
        seen.add(key)
        out_lines.append(ln)

    t = "\n".join(out_lines)

    # Paragraph dedupe (consecutive)
    paras = [p.strip() for p in re.split(r"\n\s*\n", t) if p.strip()]
    out_paras = []
    prev = None
    for p in paras:
        if prev is not None and p == prev:
            continue
        out_paras.append(p)
        prev = p

    return "\n\n".join(out_paras).strip()


def _shorten_ujd(s: str) -> str:
    """
    Remove noisy legal/procedural fragments in UJD outputs to keep it dossier-friendly.
    """
    t = s or ""
    t = re.sub(r"(?i)\b(primair|subsidiair|meer subsidiair)\b", "", t)
    t = re.sub(r"(?i)\bfeit\s*\d+\b", "", t)
    t = re.sub(
        r"(?i)\b(start-?\s*en\s*einddatum\s*proeftijd|startdatum\s*proeftijd|einddatum\s*proeftijd)\b.*",
        "",
        t,
    )
    t = re.sub(r"(?i)\bgijzeling\b.*", "", t)
    t = re.sub(r"€\s*\d{1,3}(?:\.\d{3})*(?:,\d{2})?", "", t)

    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _redact_pii(summary: str, doc_type: str) -> Tuple[str, bool]:
    s = summary or ""
    original = s

    s = re.sub(r"(?i)\bverdachte\b", "betrokkene", s)
    s = re.sub(r"(?i)\bonderzochte\b", "betrokkene", s)

    s = _RE_EMAIL.sub("", s)
    s = _RE_BSN.sub("", s)

    def _phone_repl(m: re.Match) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        return "" if len(digits) >= 9 else m.group(0)

    s = _RE_PHONE.sub(_phone_repl, s)

    s = _RE_POSTCODE.sub("", s)
    s = _RE_STREET.sub("[adres verwijderd]", s)

    if (doc_type or "").upper() != "PV":
        s = re.sub(r"(?i)\bpl\d{4}-\d{6,}\b", "[PV-kenmerk verwijderd]", s)

    s = _RE_PARKET.sub("", s)
    s = re.sub(r"(?im)^\s*(geboortedatum|geb\.|geboren)\b.*$", "", s)

    s = re.sub(
        r"\b(\d{1,3})\s*-\s*jarige\s+(man|vrouw|persoon)\b",
        r"een \2",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"\b(\d{1,3})\s*jarige\s+(man|vrouw|persoon)\b",
        r"een \2",
        s,
        flags=re.IGNORECASE,
    )
    s = _RE_AGE_PHRASE.sub("", s)
    s = _RE_AGE_WORD.sub("", s)

    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"\s+\n", "\n", s)
    s = s.strip()

    return s, (s != original)


def _needs_repair(summary: str) -> bool:
    t = summary or ""
    if not t.strip():
        return False

    if "[TEKST]" in t or "</TEKST>" in t or "DEELSAMENVATTING" in t.upper():
        return True
    if re.search(r"(?i)\bdeze\s+samenvatting\s+is\s+gebaseerd\b", t):
        return True

    if _RE_EMAIL.search(t) or _RE_BSN.search(t) or _RE_POSTCODE.search(t):
        return True
    if _RE_STREET.search(t) or _RE_PARKET.search(t):
        return True
    if _RE_DOB_CONTEXT.search(t):
        return True
    if _RE_AGE_PHRASE.search(t) or _RE_AGE_WORD.search(t):
        return True

    if _RE_INIT_SURNAME.search(t):
        return True

    return False


def _repair_pass(summary: str, doc_type: str) -> str:
    system_msg = (
        "Je bent een uiterst nauwkeurige forensisch-juridische redacteur. "
        "Je herschrijft tekst zonder nieuwe feiten toe te voegen."
    )

    user_msg = f"""
Herschrijf de onderstaande tekst tot een anonieme, formele tekst (Nederlands) voor een forensisch-psychiatrisch/juridisch verslag.

HARD REGELS
- Voeg GEEN nieuwe feiten toe. Laat GEEN inhoudelijke feiten weg.
- Verwijder uitsluitend persoonsgegevens (namen/initialen, geboortedatum/plaats, leeftijd, adressen, postcodes, telefoons, e-mail, BSN/ID, parket/zaaknummers).
- Gebruik consequente rollen: betrokkene / aangever(aangeefster) / getuige.
- Geen meta-tekst (geen 'dit is een samenvatting', geen verwijzingen naar prompts/tags/bullets).
- Geen markdown-kopjes (geen ###, geen vetgedrukte titels), geen blokken met drie aanhalingstekens.
- Houd de tekst in de verleden tijd.

TEKST:
<<BEGIN_TEKST>>
{(summary or "").strip()}
<<EINDE_TEKST>>
""".strip()

    prompt = _mistral_inst(system_msg, user_msg)
    out = _generate(prompt, max_new=REPAIR_MAX_NEW)
    return _normalize_reduce_text(out)


# -----------------------------------------------------------------------------
# Reduce helper
# -----------------------------------------------------------------------------
def _reduce_group(
    summaries: List[str],
    system_msg: str,
    target_ctx: int,
    reduce_template: str,
    *,
    extra: str = "",
) -> str:
    header = reduce_template.strip() if reduce_template.strip() else (
        "Combineer de onderstaande bullets tot één professionele tekst."
    )

    items = [s.strip() for s in summaries if (s or "").strip()]
    if not items:
        return ""

    def build_user(parts: List[str]) -> str:
        chunks = []
        for i, p in enumerate(parts, start=1):
            chunks.append(f"{i})\n{p}")
        user = header + "\n\nDEELSAMENVATTINGEN:\n" + "\n\n".join(chunks)
        if extra:
            user += "\n\n" + extra.strip()
        return user.strip()

    parts = items[:]
    prompt = _mistral_inst(system_msg, build_user(parts))
    limit = int(target_ctx * 0.86)

    max_item_chars = max(len(x) for x in parts)
    while _count_tokens_rough(prompt) > limit:
        if max_item_chars > 800:
            max_item_chars = int(max_item_chars * 0.85)
            parts = [x[:max_item_chars].strip() for x in parts]
        elif len(parts) > 1:
            parts = parts[: max(1, len(parts) // 2)]
        else:
            break
        prompt = _mistral_inst(system_msg, build_user(parts))

    out = _generate(prompt, max_new=REDUCE_MAX_NEW)
    return _normalize_reduce_text(out)


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------
def summarize_document(
    doc_type: str,
    doc_text: Optional[str] = None,
    **kwargs,
) -> str:
    """
    Summarize a document using MAP -> REDUCE (always runs REDUCE if template exists).

    kwargs:
      progress_callback: Callable[[str], None]
    """
    if doc_text is None:
        doc_text = kwargs.get("text") or kwargs.get("document_text") or ""

    progress_cb: Optional[Callable[[str], None]] = kwargs.get("progress_callback")

    def emit(msg: str) -> None:
        if callable(progress_cb):
            try:
                progress_cb(msg)
            except Exception:
                pass

    dtype = (doc_type or "UNKNOWN").upper()
    map_template, reduce_template = _load_templates(dtype)

    text = _sanitize(doc_text)

    if dtype == "TLL":
        text = _extract_tll_relevant(text)
    elif dtype == "UJD":
        text = _extract_ujd_relevant(text)

    chunks = _chunk(text, MAX_CHARS_PER_CHUNK)
    if not chunks:
        emit("No text found after extraction/sanitize.")
        return "Geen tekst aangetroffen."

    system_msg = (
        "Je bent een zorgvuldig forensisch samenvatter. "
        "Volg de regels strikt. Verzin niets. "
        "Als iets niet expliciet in de tekst staat, laat het weg."
    )

    target_ctx = int(N_CTX)

    emit(
        f"DocType={dtype} | chunks={len(chunks)} | max_chars_per_chunk={MAX_CHARS_PER_CHUNK} | "
        f"ctx={target_ctx} | reduce={'yes' if bool(reduce_template.strip()) else 'no'}"
    )

    map_extra = (
        "OUTPUT: uitsluitend bullets. Geen inleiding, geen kopjes, geen meta-tekst. "
        "Geen doublures. Neem alleen feiten op die expliciet in de bronpassage staan."
    )
    reduce_extra = (
        "OUTPUT: eindtekst zonder herhaling. Geen meta-tekst. "
        "Geen verwijzingen naar 'bullets' of 'deelsamenvattingen'. "
        "Geen duplicaten van zinnen/regels. Geen lege kopjes."
    )

    if FAST_MODE:
        chunks = chunks[: max(1, FAST_MAX_CHUNKS)]
        emit(f"FAST_MODE enabled | processing first {len(chunks)} chunk(s)")
        map_extra += " Beperk je antwoord tot maximaal 10 bullets voor deze passage."
        reduce_extra += " Houd de eindtekst beknopt (ongeveer 8–12 zinnen)."

    # -------------------------------------------------------------------------
    # 1) MAP
    # -------------------------------------------------------------------------
    partials: List[str] = []
    total_chunks = len(chunks)

    for idx, ch in enumerate(chunks, start=1):
        emit(f"MAP {idx}/{total_chunks} started")
        t0 = time.time()

        prompt = _fit_prompt_to_ctx(system_msg, map_template, ch, target_ctx, extra=map_extra)

        try:
            out = _generate(prompt, max_new=MAP_MAX_NEW)
        except Exception as e:
            emit(f"MAP error: {e} | retrying with trimmed chunk")
            trimmed = ch[: max(800, int(len(ch) * 0.75))]
            prompt = _fit_prompt_to_ctx(system_msg, map_template, trimmed, target_ctx, extra=map_extra)
            out = _generate(prompt, max_new=MAP_MAX_NEW)

        partials.append(_normalize_bullets(out))
        emit(f"MAP {idx}/{total_chunks} done ({time.time() - t0:.1f}s)")

    if int(AGGREGATE_MAX_PARTIALS) > 0 and len(partials) > int(AGGREGATE_MAX_PARTIALS):
        emit(f"Trimming partials: {len(partials)} -> {int(AGGREGATE_MAX_PARTIALS)}")
        partials = partials[: int(AGGREGATE_MAX_PARTIALS)]

    # -------------------------------------------------------------------------
    # 2) REDUCE
    # -------------------------------------------------------------------------
    group_size = int(AGGREGATE_GROUP_SIZE) if int(AGGREGATE_GROUP_SIZE) > 0 else 4

    if reduce_template.strip():
        if len(partials) == 1:
            emit("REDUCE single-pass (1 partial)")
            partials = [
                _reduce_group(
                    partials,
                    system_msg,
                    target_ctx,
                    reduce_template,
                    extra=reduce_extra,
                )
            ]
        else:
            round_no = 0
            while len(partials) > 1:
                round_no += 1
                emit(f"REDUCE round {round_no} started | partials={len(partials)} | group_size={group_size}")
                t0 = time.time()

                grouped: List[str] = []
                for i in range(0, len(partials), group_size):
                    grouped.append(
                        _reduce_group(
                            partials[i : i + group_size],
                            system_msg,
                            target_ctx,
                            reduce_template,
                            extra=reduce_extra,
                        )
                    )

                partials = grouped
                emit(f"REDUCE round {round_no} done ({time.time() - t0:.1f}s) | new_partials={len(partials)}")
    else:
        emit("No REDUCE template; returning merged MAP bullets.")
        partials = ["\n".join([p for p in partials if p.strip()]).strip()]

    final = partials[0] if partials else ""
    final = _normalize_reduce_text(final)

    # -------------------------------------------------------------------------
    # 3) Post-process
    # -------------------------------------------------------------------------
    final, _ = _redact_pii(final, dtype)
    final = _scrub_names_best_effort(final)
    final = _dedupe_lines_and_paragraphs(final)

    if dtype == "UJD":
        final = _shorten_ujd(final)

    if ENABLE_REPAIR_PASS and _needs_repair(final):
        emit("REPAIR pass: cleaning meta/PII leakage")
        try:
            repaired = _repair_pass(final, dtype)
            repaired, _ = _redact_pii(repaired, dtype)
            repaired = _scrub_names_best_effort(repaired)
            repaired = _dedupe_lines_and_paragraphs(repaired)
            if dtype == "UJD":
                repaired = _shorten_ujd(repaired)
            final = repaired
        except Exception as e:
            emit(f"REPAIR pass failed: {e} (continuing with best-effort output)")

    final = _normalize_reduce_text(final)
    emit("Summarization finished.")
    return final