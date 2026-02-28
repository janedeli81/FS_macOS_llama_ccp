# backend/summarization/llm.py

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from backend.config import MODEL_PATH, MAX_NEW_TOKENS, N_CTX
from backend.summarization.settings import STOP_WORDS, TEMPERATURE, TOP_P, REPETITION_PENALTY

_llm: Optional[object] = None


def _resolve_model_file(model_path: Path) -> Path:
    """
    Resolve MODEL_PATH to a concrete .gguf file.
    MODEL_PATH may be a file path or a directory containing a .gguf file.
    """
    if model_path.is_file():
        return model_path

    if model_path.is_dir():
        candidates = sorted(model_path.glob("*.gguf"))
        if not candidates:
            raise FileNotFoundError(f"No .gguf model file found in directory: {model_path}")
        return candidates[0]

    raise FileNotFoundError(f"LLM model path not found: {model_path}")


def _read_int_env(name: str, default: int) -> int:
    v = os.getenv(name, "").strip()
    if not v:
        return default
    try:
        return int(v)
    except Exception:
        return default


def _default_n_ctx() -> int:
    """
    Keep model context in sync with pipeline TARGET_CTX (defaults to backend.config.N_CTX).
    Allows overriding via FS_CTX / FS_CONTEXT.
    """
    v = (os.getenv("FS_CTX", "").strip() or os.getenv("FS_CONTEXT", "").strip())
    if v:
        try:
            return int(v)
        except Exception:
            pass
    return int(N_CTX)


def _default_n_gpu_layers() -> int:
    """
    GPU offload control:
    - If FS_GPU_LAYERS is set, use it.
    - Otherwise, auto-enable on macOS by requesting a very large number of layers (llama.cpp will offload max possible).
    - On other platforms default to CPU-only.
    """
    raw = os.getenv("FS_GPU_LAYERS", "").strip()
    if raw:
        try:
            return int(raw)
        except Exception:
            return 0

    if sys.platform == "darwin":
        # Request "max possible" GPU offload; llama.cpp will clamp to what fits.
        return 999

    return 0


def get_llm() -> object:
    """Load GGUF model via llama-cpp-python (llama_cpp.Llama)."""
    global _llm

    try:
        from llama_cpp import Llama  # type: ignore
    except Exception as e:
        raise ImportError(
            "llama-cpp-python is required for summarization. Install it in your environment."
        ) from e

    if _llm is not None:
        return _llm

    mp = Path(str(MODEL_PATH))
    mp = _resolve_model_file(mp)

    # Runtime settings
    n_batch = _read_int_env("FS_BATCH_SIZE", 128)
    cpu_cnt = os.cpu_count() or 8
    n_threads = _read_int_env("FS_THREADS", max(4, cpu_cnt // 2))

    n_ctx = _default_n_ctx()
    n_gpu_layers = _default_n_gpu_layers()

    debug_llama = os.getenv("FS_DEBUG_LLAMA", "0").strip() == "1"

    init_kwargs = dict(
        model_path=str(mp),
        n_threads=n_threads,
        n_batch=n_batch,
        n_ctx=n_ctx,
        n_gpu_layers=n_gpu_layers,
        verbose=bool(debug_llama),
    )

    # Try GPU first (macOS default), fallback to CPU on any load error (VRAM/unified memory issues, missing GPU backend, etc.)

    def _candidate_gpu_layers(requested: int) -> list[int]:
        """
        Build a small fallback ladder for Metal/CUDA offload.
        This prevents a hard fallback to CPU-only when the requested value is too high.
        """
        if requested <= 0:
            return [0]

        # If user requested a specific number (e.g. 40), try it first, then step down.
        # If requested is huge (e.g. 999), try a few practical values too.
        ladder = [requested, 60, 50, 40, 32, 24, 16, 8, 0]

        # Keep unique, keep <= requested (except when requested is huge like 999; then keep all)
        out: list[int] = []
        for x in ladder:
            if x in out:
                continue
            if requested < 900 and x > requested:
                continue
            out.append(x)
        return out

    # Robust load with GPU ladder, then CPU as last option
    last_err: Optional[Exception] = None
    for layers in _candidate_gpu_layers(n_gpu_layers):
        init_kwargs["n_gpu_layers"] = layers
        try:
            _llm = Llama(**init_kwargs)
            break
        except Exception as e:
            last_err = e
            _llm = None

    if _llm is None:
        # If everything failed, raise the last error
        raise last_err  # type: ignore[misc]

    # Optional: print backend info into logs when needed
    if os.getenv("FS_PRINT_SYSTEM_INFO", "0").strip() == "1":
        try:
            from llama_cpp import llama_print_system_info  # type: ignore
            llama_print_system_info()
        except Exception:
            pass

    print(
        f"[summarizer] model loaded: n_ctx={init_kwargs.get('n_ctx')} | "
        f"n_gpu_layers={init_kwargs.get('n_gpu_layers')} | n_batch={n_batch} | n_threads={n_threads}"
    )
    return _llm


def generate(prompt: str, *, max_new: Optional[int] = None) -> str:
    """
    Generate text completion for the given prompt.
    Returns raw model text (trimmed).
    """
    llm = get_llm()
    max_tokens = int(max_new or MAX_NEW_TOKENS)

    result = llm.create_completion(
        prompt=prompt,
        max_tokens=max_tokens,
        temperature=TEMPERATURE,
        top_p=TOP_P,
        repeat_penalty=REPETITION_PENALTY,
        stop=STOP_WORDS,
    )

    try:
        text = result["choices"][0]["text"]
    except Exception:
        return ""

    return (text or "").strip()