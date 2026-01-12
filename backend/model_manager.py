# backend/model_manager.py

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Callable, Optional

import certifi
import requests

from backend.config import MODEL_PATH, MODEL_URL, MODEL_SHA256

ProgressCb = Optional[Callable[[str], None]]


def _fmt_bytes(n: int) -> str:
    gb = 1024**3
    mb = 1024**2
    if n >= gb:
        return f"{n / gb:.2f} GB"
    return f"{n / mb:.1f} MB"


def ensure_model_ready(progress_cb: ProgressCb = None) -> Path:
    """
    Ensure the GGUF model exists at MODEL_PATH (user-writable dir).
    Downloads it on first run into a safe location (NOT inside .app bundle).

    Uses requests + certifi to avoid macOS .app SSL issues (CERTIFICATE_VERIFY_FAILED).

    Set FS_OFFLINE=1 to prevent auto-download and raise an error instead.
    """
    model_path = Path(MODEL_PATH)
    model_path.parent.mkdir(parents=True, exist_ok=True)

    # If already present and non-trivial size, return
    if model_path.exists() and model_path.stat().st_size > 10 * 1024 * 1024:
        return model_path

    if os.environ.get("FS_OFFLINE", "").strip() == "1":
        raise RuntimeError(
            f"Model not found at {model_path}. Auto-download disabled (FS_OFFLINE=1)."
        )

    # Ensure CA bundle is available (PyInstaller: certifi is usually bundled when imported)
    ca_path = certifi.where()
    os.environ.setdefault("SSL_CERT_FILE", ca_path)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_path)

    tmp_path = model_path.with_suffix(model_path.suffix + ".part")

    if progress_cb:
        progress_cb(f"LLM model not found. Downloading to: {model_path}")

    # Clean stale partial file
    try:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
    except Exception:
        pass

    headers = {"User-Agent": "ForensicSummarizer/1.0 (model-downloader)"}

    hasher = hashlib.sha256() if MODEL_SHA256 else None
    downloaded = 0
    last_update = 0.0
    started = time.time()

    # Use streaming download
    try:
        with requests.get(
            MODEL_URL,
            headers=headers,
            stream=True,
            timeout=(10, 300),
            verify=ca_path,
        ) as resp:
            resp.raise_for_status()

            total = resp.headers.get("Content-Length")
            total_int = int(total) if total and total.isdigit() else None

            with open(tmp_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=4 * 1024 * 1024):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)

                    if hasher:
                        hasher.update(chunk)

                    now = time.time()
                    if progress_cb and (now - last_update) > 0.5:
                        last_update = now
                        if total_int:
                            pct = int(downloaded * 100 / total_int)
                            progress_cb(
                                f"Downloading model... {pct}% ({_fmt_bytes(downloaded)} / {_fmt_bytes(total_int)})"
                            )
                        else:
                            progress_cb(f"Downloading model... {_fmt_bytes(downloaded)}")

    except requests.exceptions.SSLError as e:
        # This is the exact error your client sees (CERTIFICATE_VERIFY_FAILED).
        # Provide a clean message that helps debugging without requiring the user to be technical.
        raise RuntimeError(
            "SSL verification failed while downloading the model. "
            "This can happen in packaged macOS apps if the CA certificates are not available, "
            "or if a corporate proxy intercepts HTTPS traffic. "
            f"Details: {e}"
        ) from e
    except Exception as e:
        raise RuntimeError(f"Failed to download model: {e}") from e

    # Verify checksum if provided
    if hasher and MODEL_SHA256:
        digest = hasher.hexdigest().lower()
        expected = MODEL_SHA256.strip().lower()
        if digest != expected:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise RuntimeError(
                "Downloaded model checksum mismatch. "
                f"Expected {expected}, got {digest}."
            )

    # Atomic replace
    tmp_path.replace(model_path)

    if progress_cb:
        elapsed = time.time() - started
        progress_cb(f"Model download complete. Size: {_fmt_bytes(downloaded)}. Time: {elapsed:.1f}s")

    return model_path
