# backend/config.py

import os
import sys
from pathlib import Path


def get_backend_dir() -> Path:
    """
    Return the folder that contains backend/ resources.

    - Source run: .../backend
    - PyInstaller: sys._MEIPASS/backend
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "backend"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


def get_user_data_dir(app_name: str = "ForensicSummarizer") -> Path:
    """
    Return a writable per-user data directory.

    macOS: ~/Library/Application Support/<app_name>
    Windows: %APPDATA%\\<app_name>
    Linux: ~/.local/share/<app_name>
    """
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


# --- Base dirs ---
BASE_DIR = get_backend_dir()  # backend/
PROMPTS_DIR = BASE_DIR / "prompts"

# --- User-writable dirs (IMPORTANT for notarized .app) ---
USER_DATA_DIR = get_user_data_dir()
OUTPUT_DIR = USER_DATA_DIR / "output_summaries"
EXTRACTED_DIR = USER_DATA_DIR / "extracted_documents"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)

# --- Final report outputs (if used) ---
FINAL_REPORT_PATH = OUTPUT_DIR / "final_report.txt"
FINAL_REPORT_PDF_PATH = OUTPUT_DIR / "final_report.pdf"

# --- Summarization params ---
MAX_CHARS_PER_CHUNK = 1800
N_CTX = 2048
MAX_NEW_TOKENS = 180
AGGREGATE_GROUP_SIZE = 4
AGGREGATE_MAX_PARTIALS = 6

# --- Mapping: doc type -> prompt file ---
PROMPT_FILES = {
    "PV": PROMPTS_DIR / "pv.txt",
    "VC": PROMPTS_DIR / "vc.txt",
    "RECLASS": PROMPTS_DIR / "reclass.txt",
    "UJD": PROMPTS_DIR / "ujd.txt",
    "PJ": PROMPTS_DIR / "pj_old.txt",
    "TLL": PROMPTS_DIR / "tll.txt",
    "UNKNOWN": PROMPTS_DIR / "unknown.txt",
}

# --- Model download settings (first-run download to user dir) ---
MODEL_FILENAME = "Mistral-7B-Instruct-v0.3-Q4_K_M.gguf"
MODEL_URL = (
    "https://huggingface.co/bartowski/Mistral-7B-Instruct-v0.3-GGUF/resolve/main/"
    "Mistral-7B-Instruct-v0.3-Q4_K_M.gguf?download=true"
)
MODEL_SHA256 = "1270d22c0fbb3d092fb725d4d96c457b7b687a5f5a715abe1e818da303e562b6"


def get_bundled_model_path() -> Path:
    """
    Path to a model bundled inside a PyInstaller macOS .app (legacy builds).
    We do not write into the .app after signing, only read if present.
    """
    if getattr(sys, "frozen", False) and sys.platform == "darwin":
        exe_path = Path(sys.executable).resolve()
        contents_dir = exe_path.parent.parent  # .../Contents
        resources_dir = contents_dir / "Resources"
        return resources_dir / "backend" / "llm_models" / MODEL_FILENAME

    # Source run fallback (if you keep a local model next to the code)
    return BASE_DIR / "llm_models" / MODEL_FILENAME


def get_model_path() -> Path:
    """
    Prefer user-writable model location (for first-run download).
    If user model doesn't exist yet but a bundled model exists, use the bundled one.
    """
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

# --------------------------------------------------------------------
# llama-cpp-python runtime knobs (stability-first defaults for macOS)
# Env overrides:
#   FS_LCPP_THREADS, FS_LCPP_BATCH, FS_LCPP_GPU_LAYERS,
#   FS_LCPP_USE_MMAP, FS_LCPP_USE_MLOCK, FS_LCPP_VERBOSE
# --------------------------------------------------------------------
def _default_threads() -> int:
    """
    Conservative defaults to reduce native ggml crashes on macOS.
    """
    if sys.platform == "darwin":
        return 2
    cpu = os.cpu_count() or 4
    return max(1, min(8, int(cpu)))


LCPP_THREADS = int(os.environ.get("FS_LCPP_THREADS", str(_default_threads())))

# Smaller batch reduces peak memory and lowers crash risk in some mac builds.
LCPP_BATCH = int(os.environ.get("FS_LCPP_BATCH", "16" if sys.platform == "darwin" else "16"))

# GPU layers:
# On macOS prefer Metal by default. Override via FS_LCPP_GPU_LAYERS.
# Use:
#   FS_LCPP_GPU_LAYERS=0   -> force CPU
#   FS_LCPP_GPU_LAYERS=-1  -> try to offload all layers to GPU (Metal)
_default_gpu_layers = -1 if sys.platform == "darwin" else 0
LCPP_GPU_LAYERS = int(os.environ.get("FS_LCPP_GPU_LAYERS", str(_default_gpu_layers)))

# mmap:
# - Disabled by default on macOS for stability in notarized apps (override if needed).
LCPP_USE_MMAP = os.environ.get("FS_LCPP_USE_MMAP", "0" if sys.platform == "darwin" else "1").strip() == "1"

# mlock:
# - Usually off; can help performance but sometimes causes permission issues.
LCPP_USE_MLOCK = os.environ.get("FS_LCPP_USE_MLOCK", "0").strip() == "1"

# Verbose llama.cpp logs:
LCPP_VERBOSE = os.environ.get("FS_LCPP_VERBOSE", "0").strip() == "1"

# --- Optional legacy (kept for compatibility with other modules if present) ---
OLLAMA_HOST = "http://127.0.0.1:11434"
OLLAMA_MODEL = "tinyllama"
