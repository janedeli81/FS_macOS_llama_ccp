# backend/summarizer.py

"""Public summarization entry point.

The heavy summarization logic is implemented in backend/summarization/ so it can be
maintained and tuned more easily.

External modules should keep importing:
    from backend.summarizer import summarize_document
"""

from __future__ import annotations

from backend.summarization.pipeline import summarize_document

__all__ = ["summarize_document"]