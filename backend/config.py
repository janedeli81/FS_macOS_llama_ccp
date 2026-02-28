# backend/config.py

import os
import sys
from pathlib import Path


def get_backend_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "backend"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


def get_user_data_dir(app_name: str = "ForensicSummarizer") -> Path:
    home = Path.home()

    if sys.platform == "darwin":
        base = home / "Library" / "Application Support"
    elif sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming")))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", str(home / ".local" / "share")))

    path = base / app_name
    path.mkdir(parents=True, exist_ok=True)
    return path


BASE_DIR = get_backend_dir()
PROMPTS_DIR = BASE_DIR / "prompts"

USER_DATA_DIR = get_user_data_dir()
OUTPUT_DIR = USER_DATA_DIR / "output_summaries"
EXTRACTED_DIR = USER_DATA_DIR / "extracted_documents"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)

FINAL_REPORT_PATH = OUTPUT_DIR / "final_report.txt"
FINAL_REPORT_PDF_PATH = OUTPUT_DIR / "final_report.pdf"

MAX_CHARS_PER_CHUNK = 15000
N_CTX = 32768
MAX_NEW_TOKENS = 1024

AGGREGATE_GROUP_SIZE = 6
AGGREGATE_MAX_PARTIALS = 0

PROMPT_FILES = {
    "PV": PROMPTS_DIR / "pv.txt",
    "VC": PROMPTS_DIR / "vc.txt",
    "RECLASS": PROMPTS_DIR / "reclass.txt",
    "UJD": PROMPTS_DIR / "ujd.txt",
    # CHANGED: use pj.txt (new)
    "PJ": PROMPTS_DIR / "pj.txt",
    "TLL": PROMPTS_DIR / "tll.txt",
    "UNKNOWN": PROMPTS_DIR / "unknown.txt",
}

MODEL_FILENAME = "Mistral-Small-Instruct-2409-Q4_K_M.gguf"

# Hugging Face direct download URL.
# You can override it via FS_MODEL_DOWNLOAD_URL environment variable if needed.
MODEL_URL = (
    "https://huggingface.co/bartowski/Mistral-Small-Instruct-2409-GGUF/resolve/main/"
    "Mistral-Small-Instruct-2409-Q4_K_M.gguf?download=true"
)

# Optional integrity check.
# Leave empty to skip checksum verification, or set the expected sha256.
MODEL_SHA256 = ""


def get_bundled_model_path() -> Path:
    if getattr(sys, "frozen", False) and sys.platform == "darwin":
        exe_path = Path(sys.executable).resolve()
        contents_dir = exe_path.parent.parent
        resources_dir = contents_dir / "Resources"
        return resources_dir / "backend" / "llm_models" / MODEL_FILENAME

    return BASE_DIR / "llm_models" / MODEL_FILENAME


def get_model_path() -> Path:
    override = os.environ.get("FS_MODEL_PATH", "").strip()
    if override:
        p = Path(override).expanduser()
        if p.is_dir():
            p = p / MODEL_FILENAME
        return p

    user_models_dir = USER_DATA_DIR / "llm_models"
    user_models_dir.mkdir(parents=True, exist_ok=True)
    user_model_path = user_models_dir / MODEL_FILENAME

    if user_model_path.exists():
        return user_model_path

    bundled = get_bundled_model_path()
    if bundled.exists():
        return bundled

    return user_model_path


MODEL_PATH = get_model_path()

# ---------------------------------------------------------------------------
# Default runtime tuning (Apple Silicon / Metal friendly)
# Applied only if the user did NOT set FS_* vars externally.
# ---------------------------------------------------------------------------

def apply_runtime_env_defaults() -> None:
    """
    Apply default environment variables for runtime tuning.

    These values are used only if the user did not already set them externally
    (Terminal, system env, etc.). This keeps the app self-contained while still
    allowing overrides.
    """
    cpu_cnt = os.cpu_count() or 8

    defaults = {
        # Context window
        "FS_CTX": str(N_CTX),

        # llama.cpp runtime
        "FS_BATCH_SIZE": "128",
        # Reasonable default: use up to 8 threads, but not more than CPU count
        "FS_THREADS": str(min(8, cpu_cnt)),

        # Generation limits (faster defaults)
        "FS_REDUCE_MAX_NEW": "1536",
        "FS_REPAIR_MAX_NEW": "768",

        # Sampling
        "FS_REPETITION_PENALTY": "1.15",
    }

    # Apple Silicon / Metal: request "max possible" GPU offload by default.
    # llama.cpp will offload as much as it can, but may still fail on low memory,
    # so we also add robust fallback in llm.py (see below).
    if sys.platform == "darwin":
        defaults["FS_GPU_LAYERS"] = "999"

    for k, v in defaults.items():
        os.environ.setdefault(k, v)


apply_runtime_env_defaults()


