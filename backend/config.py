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

MAX_CHARS_PER_CHUNK = 9000
N_CTX = 8192
MAX_NEW_TOKENS = 512

AGGREGATE_GROUP_SIZE = 4
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

# Model configuration
# The actual model path is managed by model_manager.py via ensure_model_ready()
# This constant is only used for the encrypted filename pattern
MODEL_FILENAME = "Mistral-7B-Instruct-v0.3-Q4_K_M.gguf"

# DEPRECATED: These functions search for UNENCRYPTED models and are kept
# only for backward compatibility. The primary method is model_manager.ensure_model_ready()
# which handles encrypted (.enc) models.


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