# backend/summarization/pipeline.py

"""Main summarization pipeline: MAP -> REDUCE -> post-process.

This module owns the top-level `summarize_document` function.
All heavy sub-tasks are delegated to the other modules in this package.
"""

from __future__ import annotations

import time
from typing import Callable, List, Optional

from backend.config import (
    MAX_CHARS_PER_CHUNK,
    AGGREGATE_GROUP_SIZE,
    AGGREGATE_MAX_PARTIALS,
)
from backend.summarization.settings import (
    FAST_MODE,
    FAST_MAX_CHUNKS,
    MAP_MAX_NEW,
    REDUCE_MAX_NEW,
    TARGET_CTX,
    ENABLE_REPAIR_PASS,
)
from backend.summarization.llm import generate
from backend.summarization.prompts import (
    mistral_inst,
    load_templates,
    fit_prompt_to_ctx,
    count_tokens_rough,
)
from backend.summarization.text_utils import (
    sanitize,
    chunk,
    strip_pv_boilerplate,
    compact_pv_qa_if_needed,
    compact_numeric_runs,
    extract_tll_relevant,
    extract_ujd_relevant,
)
from backend.summarization.output_utils import (
    normalize_bullets,
    normalize_reduce_text,
)
from backend.summarization.privacy import (
    pre_anonymize,
    redact_pii,
    scrub_names_best_effort,
    post_scrub_pv_style,
    dedupe_lines_and_paragraphs,
    trim_trailing_fragment,
    shorten_ujd,
    needs_repair,
    repair_pass,
)


_SYSTEM_MSG = (
    "Je bent een zorgvuldig forensisch samenvatter. "
    "Volg de regels strikt. Verzin niets. "
    "Als iets niet expliciet in de tekst staat, laat het weg."
)


def _reduce_group(
    summaries: List[str],
    target_ctx: int,
    reduce_template: str,
    *,
    extra: str = "",
) -> str:
    header = reduce_template.strip() or (
        "Combineer de onderstaande bullets tot één professionele tekst."
    )

    items = [s.strip() for s in summaries if (s or "").strip()]
    if not items:
        return ""

    def build_user(parts: List[str]) -> str:
        chunks = [f"{i})\n{p}" for i, p in enumerate(parts, start=1)]
        user = header + "\n\nDEELSAMENVATTINGEN:\n" + "\n\n".join(chunks)
        if extra:
            user += "\n\n" + extra.strip()
        return user.strip()

    parts = items[:]
    prompt = mistral_inst(_SYSTEM_MSG, build_user(parts))
    limit = int(target_ctx * 0.86)

    max_item_chars = max(len(x) for x in parts)
    while count_tokens_rough(prompt) > limit:
        if max_item_chars > 800:
            max_item_chars = int(max_item_chars * 0.85)
            parts = [x[:max_item_chars].strip() for x in parts]
        elif len(parts) > 1:
            parts = parts[: max(1, len(parts) // 2)]
        else:
            break
        prompt = mistral_inst(_SYSTEM_MSG, build_user(parts))

    out = generate(prompt, max_new=REDUCE_MAX_NEW)
    return normalize_reduce_text(out)


def summarize_document(
    doc_type: str,
    doc_text: Optional[str] = None,
    **kwargs,
) -> str:
    if doc_text is None:
        doc_text = kwargs.get("text") or kwargs.get("document_text") or ""

    progress_cb: Optional[Callable[[str], None]] = kwargs.get("progress_callback")
    doc_name: str = kwargs.get("doc_name", "")

    def emit(msg: str) -> None:
        if callable(progress_cb):
            try:
                progress_cb(msg)
            except Exception:
                pass

    dtype = (doc_type or "UNKNOWN").upper()
    map_template, reduce_template = load_templates(dtype)

    # --- Pre-process raw text ---
    text = sanitize(doc_text)
    text = pre_anonymize(text, dtype)

    if dtype == "TLL":
        text = extract_tll_relevant(text)
    elif dtype == "UJD":
        text = extract_ujd_relevant(text)

    if dtype == "PV":
        text = strip_pv_boilerplate(text)
        # Apply Q/A compaction only if the PV looks like a verhoor transcript.
        text = compact_pv_qa_if_needed(text)
        # Compress long numeric/table blocks (e.g., transaction exports) to protect chunking.
        text = compact_numeric_runs(text)

    chunks = chunk(text, MAX_CHARS_PER_CHUNK)
    if not chunks:
        emit("No text found after extraction/sanitize.")
        return "Geen tekst aangetroffen."

    emit(
        f"DocType={dtype} | chunks={len(chunks)} | max_chars_per_chunk={MAX_CHARS_PER_CHUNK} | "
        f"ctx={TARGET_CTX} | reduce={'yes' if reduce_template.strip() else 'no'}"
        + (f" | file={doc_name}" if doc_name else "")
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

    active_chunks = chunks
    if FAST_MODE:
        active_chunks = chunks[: max(1, FAST_MAX_CHUNKS)]
        emit(f"FAST_MODE enabled | processing first {len(active_chunks)} chunk(s)")
        map_extra += " Beperk je antwoord tot maximaal 10 bullets voor deze passage."
        reduce_extra += " Houd de eindtekst beknopt (ongeveer 8–12 zinnen)."

    # 1) MAP
    partials: List[str] = []
    total_chunks = len(active_chunks)

    for idx, ch in enumerate(active_chunks, start=1):
        emit(f"MAP {idx}/{total_chunks} started")
        t0 = time.time()

        prompt = fit_prompt_to_ctx(_SYSTEM_MSG, map_template, ch, TARGET_CTX, extra=map_extra)

        try:
            out = generate(prompt, max_new=MAP_MAX_NEW)
        except Exception as e:
            emit(f"MAP error: {e} | retrying with trimmed chunk")
            trimmed = ch[: max(800, int(len(ch) * 0.75))]
            prompt = fit_prompt_to_ctx(_SYSTEM_MSG, map_template, trimmed, TARGET_CTX, extra=map_extra)
            out = generate(prompt, max_new=MAP_MAX_NEW)

        partials.append(normalize_bullets(out))
        emit(f"MAP {idx}/{total_chunks} done ({time.time() - t0:.1f}s)")

    max_partials = int(AGGREGATE_MAX_PARTIALS)
    if max_partials > 0 and len(partials) > max_partials:
        emit(f"Trimming partials: {len(partials)} -> {max_partials}")
        partials = partials[:max_partials]

    # 2) REDUCE
    group_size = int(AGGREGATE_GROUP_SIZE) if int(AGGREGATE_GROUP_SIZE) > 0 else 4

    if reduce_template.strip():
        if len(partials) == 1:
            emit("REDUCE single-pass (1 partial)")
            partials = [
                _reduce_group(partials, TARGET_CTX, reduce_template, extra=reduce_extra)
            ]
        else:
            round_no = 0
            while len(partials) > 1:
                round_no += 1
                emit(
                    f"REDUCE round {round_no} started | partials={len(partials)} | group_size={group_size}"
                )
                t0 = time.time()
                grouped: List[str] = []
                for i in range(0, len(partials), group_size):
                    grouped.append(
                        _reduce_group(
                            partials[i : i + group_size],
                            TARGET_CTX,
                            reduce_template,
                            extra=reduce_extra,
                        )
                    )
                partials = grouped
                emit(
                    f"REDUCE round {round_no} done ({time.time() - t0:.1f}s) | new_partials={len(partials)}"
                )
    else:
        emit("No REDUCE template; returning merged MAP bullets.")
        partials = ["\n".join(p for p in partials if p.strip()).strip()]

    final = partials[0] if partials else ""
    final = normalize_reduce_text(final)

    # Keep a copy of the raw model output (after reduce normalization) so we can
    # recover if post-processing redacts too aggressively.
    raw_final = final

    # 3) Post-process
    final, _ = redact_pii(final, dtype)
    final = scrub_names_best_effort(final)

    if dtype == "PV":
        final = post_scrub_pv_style(final)

    final = dedupe_lines_and_paragraphs(final)
    final = trim_trailing_fragment(final)

    if dtype == "UJD":
        final = shorten_ujd(final)

    # Emergency fallback: if post-processing produced an empty/near-empty output,
    # retry from the raw (pre-redaction) summary using the same scrub pipeline.
    if not final.strip() or len(final.strip()) < 40:
        emit("Post-process produced empty/too short output; applying fallback from raw summary")
        fallback = raw_final
        fallback, _ = redact_pii(fallback, dtype)
        fallback = scrub_names_best_effort(fallback)
        if dtype == "PV":
            fallback = post_scrub_pv_style(fallback)
        fallback = dedupe_lines_and_paragraphs(fallback)
        fallback = trim_trailing_fragment(fallback)
        if dtype == "UJD":
            fallback = shorten_ujd(fallback)
        final = fallback

    # 4) Optional repair pass
    if ENABLE_REPAIR_PASS and needs_repair(final):
        emit("REPAIR pass: cleaning meta/PII leakage")
        try:
            repaired = repair_pass(final, dtype, generate)
            repaired, _ = redact_pii(repaired, dtype)
            repaired = scrub_names_best_effort(repaired)
            if dtype == "PV":
                repaired = post_scrub_pv_style(repaired)
            repaired = dedupe_lines_and_paragraphs(repaired)
            repaired = trim_trailing_fragment(repaired)
            if dtype == "UJD":
                repaired = shorten_ujd(repaired)
            final = repaired
        except Exception as e:
            emit(f"REPAIR pass failed: {e} (continuing with best-effort output)")

    # Final safety net: if still empty/too short, try repairing from raw output.
    if ENABLE_REPAIR_PASS and (not final.strip() or len(final.strip()) < 40):
        emit("Final output still empty/too short; REPAIR from raw summary")
        try:
            repaired = repair_pass(raw_final, dtype, generate)
            repaired, _ = redact_pii(repaired, dtype)
            repaired = scrub_names_best_effort(repaired)
            if dtype == "PV":
                repaired = post_scrub_pv_style(repaired)
            repaired = dedupe_lines_and_paragraphs(repaired)
            repaired = trim_trailing_fragment(repaired)
            if dtype == "UJD":
                repaired = shorten_ujd(repaired)
            final = repaired
        except Exception as e:
            emit(f"Emergency REPAIR failed: {e} (continuing with best-effort output)")

    final = normalize_reduce_text(final)
    emit("Summarization finished.")
    return final