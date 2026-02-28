# backend/summarization/settings.py

"""Runtime settings for local LLM summarization.

All values are read from environment variables with safe defaults.
"""

from __future__ import annotations

import os

from backend.config import MAX_NEW_TOKENS, N_CTX


STOP_WORDS = [
    "</s>",
    "<|assistant|>",
    "<|user|>",
    "<|system|>",
    "</TEKST>",
    "[INST]",
    "[/INST]",
    "</TEKST_WAAR_HET_OM_GAAT>",
    "JOUW ANTWOORD:",
    "JOUW ANTWOORD",
]

# Fast mode (dev)
FAST_MODE = os.getenv("FS_FAST_MODE", "0").strip() == "1"
FAST_MAX_CHUNKS = int(os.getenv("FS_FAST_MAX_CHUNKS", "1"))

# Generation
MAP_MAX_NEW = int(os.getenv("FS_MAP_MAX_NEW", str(MAX_NEW_TOKENS)))
REDUCE_MAX_NEW = int(os.getenv("FS_REDUCE_MAX_NEW", str(max(1024, MAX_NEW_TOKENS))))
REPAIR_MAX_NEW = int(os.getenv("FS_REPAIR_MAX_NEW", "768"))

TEMPERATURE = float(os.getenv("FS_TEMPERATURE", "0.05"))
TOP_P = float(os.getenv("FS_TOP_P", "0.95"))
REPETITION_PENALTY = float(os.getenv("FS_REPETITION_PENALTY", "1.15"))

ENABLE_REPAIR_PASS = os.getenv("FS_ENABLE_REPAIR_PASS", "1").strip() != "0"

# Context
TARGET_CTX = int(os.getenv("FS_CTX", str(N_CTX)))

# Optional PV sentence bounds (for extra guidance in prompts)
PV_SENT_MIN = int(os.getenv("FS_PV_SENT_MIN", "8"))
PV_SENT_MAX = int(os.getenv("FS_PV_SENT_MAX", "14"))