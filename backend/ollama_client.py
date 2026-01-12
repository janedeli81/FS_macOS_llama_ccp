# backend/ollama_client.py

import json
import requests
from typing import Generator

from backend.config import OLLAMA_HOST, OLLAMA_MODEL


def generate(prompt: str) -> str:
    """
    Simple wrapper around Ollama /generate endpoint.
    """
    url = f"{OLLAMA_HOST}/api/generate"
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    resp = requests.post(url, json=payload, timeout=600)
    resp.raise_for_status()
    data = resp.json()
    return data.get("response", "")
