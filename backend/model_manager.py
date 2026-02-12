# backend/model_manager.py
# All comments are intentionally in English (project convention).

from __future__ import annotations

import base64
import os
import sys
import time
import shutil
from pathlib import Path
from typing import Callable, Optional

from backend.config import USER_DATA_DIR, MODEL_FILENAME

ProgressCb = Optional[Callable[[str], None]]

# Encrypted container format (very simple):
#   MAGIC(8) + NONCE(12) + CIPHERTEXT(...) + TAG(16)
_MAGIC = b"FSMODEL1"  # 8 bytes
_NONCE_LEN = 12
_TAG_LEN = 16

_RUNTIME_MODEL_PATH: Optional[Path] = None


def _emit(cb: ProgressCb, msg: str) -> None:
    if callable(cb):
        try:
            cb(msg)
        except Exception:
            pass


def _fmt_bytes(n: int) -> str:
    gb = 1024**3
    mb = 1024**2
    if n >= gb:
        return f"{n / gb:.2f} GB"
    return f"{n / mb:.1f} MB"


def _package_dir_best_effort() -> Optional[Path]:
    """
    Best-effort directory that contains the .app bundle (macOS) or project root (dev).
    For macOS PyInstaller .app:
      sys.executable = .../forensic_summarizer.app/Contents/MacOS/forensic_summarizer
      package_dir is parent of *.app bundle.
    """
    try:
        exe = Path(sys.executable).resolve()

        if sys.platform == "darwin" and ".app/Contents/MacOS" in str(exe):
            # .../MyApp.app/Contents/MacOS/<bin>
            app_bundle = exe.parents[2]  # <bin> -> MacOS -> Contents -> *.app
            return app_bundle.parent      # folder that contains *.app
    except Exception:
        pass

    # Dev fallback: repo root (backend/..)
    try:
        return Path(__file__).resolve().parents[1]
    except Exception:
        return None


def _enc_filename() -> str:
    """
    Default encrypted filename:
      "<MODEL_FILENAME>.enc"
    You can override via env if you want a stable name like "model.gguf.enc".
    """
    override = os.environ.get("FS_MODEL_ENC_FILENAME", "").strip()
    if override:
        return override
    return f"{MODEL_FILENAME}.enc"


def _find_encrypted_model() -> Path:
    """
    Search encrypted model in a very small, predictable set of locations.
    Priority:
      1) FS_MODEL_ENC_PATH (explicit)
      2) package_dir/<enc>
      3) package_dir/models/<enc>
      4) USER_DATA_DIR/models/<enc>
    """
    env_path = os.environ.get("FS_MODEL_ENC_PATH", "").strip()
    if env_path:
        p = Path(env_path).expanduser()
        if p.is_dir():
            p = p / _enc_filename()
        if p.exists():
            return p

    enc_name = _enc_filename()

    pkg = _package_dir_best_effort()
    if pkg:
        p1 = pkg / enc_name
        if p1.exists():
            return p1
        p2 = pkg / "models" / enc_name
        if p2.exists():
            return p2

    p3 = (USER_DATA_DIR / "models" / enc_name)
    if p3.exists():
        return p3

    raise FileNotFoundError(
        "Encrypted model not found. Expected one of:\n"
        f"- {enc_name} next to the .app package folder\n"
        f"- models/{enc_name} next to the .app package folder\n"
        f"- {p3}\n"
        "You can also set FS_MODEL_ENC_PATH explicitly."
    )


def _load_key_bytes() -> bytes:
    """
    Load 32-byte AES key.
    Simplest options:
      - env: FS_MODEL_KEY_B64 (base64-encoded 32 bytes)
      - env: FS_MODEL_KEY_HEX (64 hex chars)
      - file: model.key (base64) next to encrypted model
    """
    b64 = os.environ.get("FS_MODEL_KEY_B64", "").strip()
    if b64:
        key = base64.b64decode(b64)
        if len(key) != 32:
            raise ValueError("FS_MODEL_KEY_B64 must decode to exactly 32 bytes.")
        return key

    hx = os.environ.get("FS_MODEL_KEY_HEX", "").strip()
    if hx:
        key = bytes.fromhex(hx)
        if len(key) != 32:
            raise ValueError("FS_MODEL_KEY_HEX must be 64 hex chars (32 bytes).")
        return key

    # Try model.key next to enc file (base64)
    enc_path = _find_encrypted_model()
    key_file = enc_path.parent / "model.key"
    if key_file.exists():
        raw = key_file.read_text(encoding="utf-8", errors="ignore").strip()
        key = base64.b64decode(raw)
        if len(key) != 32:
            raise ValueError("model.key must be base64 for exactly 32 bytes.")
        return key

    raise RuntimeError(
        "Encryption key not provided. Provide one of:\n"
        "- FS_MODEL_KEY_B64 (base64)\n"
        "- FS_MODEL_KEY_HEX (hex)\n"
        "- model.key next to the encrypted model (base64)\n"
    )


def _get_runtime_dir() -> Path:
    """
    Store decrypted runtime artifacts in Caches (macOS best practice).
    """
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches" / "ForensicSummarizer"
    else:
        base = USER_DATA_DIR / "cache"

    rt = base / "runtime"
    rt.mkdir(parents=True, exist_ok=True)
    return rt


def cleanup_runtime_files(max_age_hours: int = 24) -> None:
    """
    Best-effort cleanup of decrypted runtime files.
    - max_age_hours == 0: remove all runtime artifacts immediately.
    - otherwise: remove only files older than max_age_hours.
    """
    rt = _get_runtime_dir()
    now = time.time()
    max_age_sec = max_age_hours * 3600

    for p in rt.glob("*.gguf*"):
        try:
            if max_age_hours == 0:
                p.unlink(missing_ok=True)
                continue

            age = now - p.stat().st_mtime
            if age >= max_age_sec:
                p.unlink(missing_ok=True)
        except Exception:
            pass

    for p in rt.glob("*.part"):
        try:
            if max_age_hours == 0:
                p.unlink(missing_ok=True)
                continue
            age = now - p.stat().st_mtime
            if age >= max_age_sec:
                p.unlink(missing_ok=True)
        except Exception:
            pass


def _copy_enc_to_app_support(enc_path: Path, progress_cb: ProgressCb) -> Path:
    """
    Copy encrypted model into Application Support for stability (avoids translocation issues).
    """
    models_dir = USER_DATA_DIR / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    dst = models_dir / enc_path.name
    if dst.exists() and dst.stat().st_size == enc_path.stat().st_size:
        return dst

    _emit(progress_cb, f"Copying encrypted model to: {dst}")
    shutil.copy2(enc_path, dst)
    return dst


def _decrypt_aes256gcm_stream(enc_path: Path, out_path: Path, key: bytes, progress_cb: ProgressCb) -> None:
    """
    Decrypt AES-256-GCM in streaming mode.
    Container layout: MAGIC(8) + NONCE(12) + CIPHERTEXT + TAG(16).
    """
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except Exception as e:
        raise RuntimeError("Missing dependency: cryptography. Add it to requirements.txt.") from e

    total_size = enc_path.stat().st_size
    header_size = len(_MAGIC) + _NONCE_LEN
    if total_size < header_size + _TAG_LEN + 1024:
        raise RuntimeError("Encrypted model file is too small or corrupted.")

    with open(enc_path, "rb") as f:
        magic = f.read(len(_MAGIC))
        if magic != _MAGIC:
            raise RuntimeError("Encrypted model has invalid header (MAGIC mismatch).")

        nonce = f.read(_NONCE_LEN)
        if len(nonce) != _NONCE_LEN:
            raise RuntimeError("Encrypted model header is corrupted (nonce).")

        # Read tag from end
        f.seek(-_TAG_LEN, os.SEEK_END)
        tag = f.read(_TAG_LEN)
        if len(tag) != _TAG_LEN:
            raise RuntimeError("Encrypted model is corrupted (tag).")

        # Ciphertext region
        ct_offset = header_size
        ct_len = total_size - header_size - _TAG_LEN

        decryptor = Cipher(
            algorithms.AES(key),
            modes.GCM(nonce, tag),
        ).decryptor()

        tmp = out_path.with_suffix(out_path.suffix + ".part")

        # Ensure private permissions best-effort (600)
        try:
            old_umask = os.umask(0o077)
        except Exception:
            old_umask = None

        try:
            with open(tmp, "wb") as out:
                f.seek(ct_offset)
                remaining = ct_len
                done = 0
                last_update = 0.0

                while remaining > 0:
                    chunk = f.read(min(4 * 1024 * 1024, remaining))
                    if not chunk:
                        raise RuntimeError("Unexpected EOF while reading ciphertext.")
                    remaining -= len(chunk)
                    done += len(chunk)

                    out.write(decryptor.update(chunk))

                    now = time.time()
                    if (now - last_update) > 0.7:
                        last_update = now
                        _emit(
                            progress_cb,
                            f"Decrypting model... {_fmt_bytes(done)} / {_fmt_bytes(ct_len)}"
                        )

                # Verify tag
                decryptor.finalize()

            tmp.replace(out_path)

        finally:
            if old_umask is not None:
                try:
                    os.umask(old_umask)
                except Exception:
                    pass

            # Best-effort cleanup of partial file
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass


def ensure_model_ready(progress_cb: ProgressCb = None) -> Path:
    """
    Ensure a decrypted GGUF exists for current app session and return its path.

    Workflow:
      1) find encrypted model (*.enc)
      2) copy encrypted model into Application Support (stability)
      3) decrypt into Caches/runtime (session file)
      4) return decrypted runtime path
    """
    global _RUNTIME_MODEL_PATH

    # Clean stale runtime artifacts (best-effort)
    cleanup_runtime_files(max_age_hours=24)

    rt_dir = _get_runtime_dir()
    runtime_name = f"{MODEL_FILENAME}.runtime.{os.getpid()}.gguf"
    runtime_path = rt_dir / runtime_name

    if _RUNTIME_MODEL_PATH and _RUNTIME_MODEL_PATH.exists() and _RUNTIME_MODEL_PATH.stat().st_size > 10 * 1024 * 1024:
        return _RUNTIME_MODEL_PATH

    if runtime_path.exists() and runtime_path.stat().st_size > 10 * 1024 * 1024:
        _RUNTIME_MODEL_PATH = runtime_path
        return runtime_path

    _emit(progress_cb, "Preparing LLM model (decrypt runtime)...")

    # Find & stabilize encrypted model
    enc = _find_encrypted_model()
    try:
        enc = _copy_enc_to_app_support(enc, progress_cb)
    except Exception:
        # If copy fails, continue using original path (still works most of the time)
        pass

    key = _load_key_bytes()

    _emit(progress_cb, f"Encrypted model: {enc.name} ({_fmt_bytes(enc.stat().st_size)})")
    _emit(progress_cb, f"Runtime model path: {runtime_path}")

    _decrypt_aes256gcm_stream(enc, runtime_path, key, progress_cb)

    # Sanity check
    if not runtime_path.exists() or runtime_path.stat().st_size < 10 * 1024 * 1024:
        raise RuntimeError("Decrypted runtime model looks invalid (too small).")

    _RUNTIME_MODEL_PATH = runtime_path
    _emit(progress_cb, "Model ready.")
    return runtime_path
