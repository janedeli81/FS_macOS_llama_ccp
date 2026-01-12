# backend/classifiers.py

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def _normalize(s: str) -> str:
    """
    Lowercase + strip accents (e.g. justitiële -> justitiele).
    """
    s = (s or "").lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s


def _prep_for_search(s: str) -> str:
    """
    Normalize + make separators consistent so that:
      - "pv_vgl", "pv-vgl", "pv.vgl" become searchable
      - "vord.ibs" becomes "vord ibs"
    """
    s = _normalize(s)
    s = re.sub(r"[_\-.]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _token_match(haystack: str, token: str) -> bool:
    """
    Match abbreviations as standalone tokens:
      pv, vc, vgc, pj, ujd, tll, recl, ibs, ...
    """
    token = re.escape(token)
    return re.search(rf"(?<![a-z0-9]){token}(?![a-z0-9])", haystack) is not None


def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for it in items:
        it = (it or "").strip()
        if not it:
            continue
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


def _get_allowed_types_from_config() -> List[str]:
    """
    Allowed types are driven by PROMPT_FILES keys (project truth).
    UNKNOWN is always allowed as fallback but not used as a detection target.
    """
    try:
        from backend.config import PROMPT_FILES  # local import to avoid import-time issues
        keys = [k for k in PROMPT_FILES.keys() if k and k.upper() != "UNKNOWN"]
        keys = sorted(set(k.upper() for k in keys))
        return keys
    except Exception:
        # Fallback if config cannot be imported for some reason
        return ["PJ", "VC", "PV", "RECLASS", "UJD", "TLL"]


def _default_rules() -> Dict[str, Dict[str, List[str]]]:
    """
    Default keyword rules based on the client's nomenclature screenshots (previous chat),
    kept minimal and clean (no duplicates).

    You can extend/override these via backend/nomenclature_rules.json.
    """
    return {
        "TLL": {
            "phrases": [
                "vordering tot inbewaringstelling",
                "vordering inbewaringstelling",
                "inbewaringstelling",
                "in bewaringstelling",
                "vordering ibs",
                "vord ibs",
                "vordibs",
            ],
            "tokens": ["tll", "ibs"],
        },
        "UJD": {
            "phrases": [
                "uittreksel justitiele documentatie",
                "justitiele documentatie",
                "uittreksel",
            ],
            "tokens": ["ujd"],
        },
        "RECLASS": {
            "phrases": [
                "reclasseringsrapport",
                "reclasseringsadvies",
                "adviesrapportage toezicht",
                "voortgangsrapportage",
                "vroeghulp",
                "reclassering",
                "adviesrapportage",
                "reclasserings",
            ],
            "tokens": ["recl", "reclass"],
        },
        "VC": {
            "phrases": [
                "voorgeleidingsconsult",
                "voor geleidingsconsult",
                "voor geleidings consult",
                "voorgeleiding rc",
                "voor geleiding rc",
                "voor geleiding rechter commissaris",
                "voor geleiding rechter-commissaris",
                "voorgeleiding rechter commissaris",
                "voorgeleiding rechter-commissaris",
                "verhoor raadkamer",
                "stukken rc",
                "pro justitia consult",
                "projustitia consult",
                "projustitiaconsult",
                "nifp consult",
                "nifpconsult",
                "trajectconsult",
                "traject consult",
                "voorgeleiding",
                "voor geleiding",
            ],
            "tokens": ["vc", "vgc"],
        },
        "PV": {
            "phrases": [
                "proces verbaal",
                "proces-verbaal",
                "procesverbaal",
                "pv vgl",
                "pvvgl",
                "nazending",
                "verhoor",
            ],
            "tokens": ["pv"],
        },
        "PJ": {
            "phrases": [
                "oude pj",
                "oud pj",
                "rapport pro justitia",
                "pro justitia",
                "projustitia",
                "nifp",
            ],
            "tokens": ["pj"],
        },
    }


def _load_external_rules_json() -> Dict[str, Dict[str, List[str]]]:
    """
    Optional external rules file:
      backend/nomenclature_rules.json

    Format:
    {
      "PV": {"phrases": ["..."], "tokens": ["pv"]},
      "VC": {"phrases": ["..."], "tokens": ["vc", "vgc"]}
    }
    """
    rules_path = Path(__file__).resolve().parent / "nomenclature_rules.json"
    if not rules_path.exists():
        return {}

    try:
        data = json.loads(rules_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        out: Dict[str, Dict[str, List[str]]] = {}
        for k, v in data.items():
            if not isinstance(v, dict):
                continue
            phrases = v.get("phrases", [])
            tokens = v.get("tokens", [])
            if not isinstance(phrases, list):
                phrases = []
            if not isinstance(tokens, list):
                tokens = []
            out[str(k).upper()] = {
                "phrases": [str(x) for x in phrases],
                "tokens": [str(x) for x in tokens],
            }
        return out
    except Exception:
        return {}


def _merge_rules(
    base: Dict[str, Dict[str, List[str]]],
    extra: Dict[str, Dict[str, List[str]]],
    allowed_types: List[str],
) -> Dict[str, Dict[str, List[str]]]:
    merged: Dict[str, Dict[str, List[str]]] = {}
    allowed = set(t.upper() for t in allowed_types)

    for t in allowed:
        base_t = base.get(t, {"phrases": [], "tokens": []})
        extra_t = extra.get(t, {"phrases": [], "tokens": []})

        phrases = _dedupe_keep_order(list(base_t.get("phrases", [])) + list(extra_t.get("phrases", [])))
        tokens = _dedupe_keep_order(list(base_t.get("tokens", [])) + list(extra_t.get("tokens", [])))

        merged[t] = {"phrases": phrases, "tokens": tokens}

    return merged


def _detect_type_from_filename_prefix(filename: str, allowed_types: List[str]) -> Optional[str]:
    """
    If filename starts with a known type code, return it.
    Examples: "PV_...", "VC-...", "UJD ...", "RECLASS...."
    """
    prepared = _prep_for_search(Path(filename).stem)
    parts = prepared.split()
    if not parts:
        return None
    first = parts[0].upper()
    if first in set(allowed_types):
        return first
    return None


def _best_match(haystack: str, rules: Dict[str, Dict[str, List[str]]], priority: List[str]) -> Tuple[int, str, str]:
    """
    Returns (score, doc_type, matched_keyword).

    Scoring:
      - phrase match: 100 + len(phrase)  (phrases are more specific)
      - token match:  10 + len(token)
    """
    best_score = 0
    best_type = ""
    best_kw = ""

    priority_index = {t: i for i, t in enumerate(priority)}

    for doc_type, rule in rules.items():
        # phrases
        for p in rule.get("phrases", []):
            p2 = _prep_for_search(p)
            if p2 and p2 in haystack:
                score = 100 + len(p2)
                if (score > best_score) or (
                    score == best_score and priority_index.get(doc_type, 10**9) < priority_index.get(best_type, 10**9)
                ):
                    best_score = score
                    best_type = doc_type
                    best_kw = p

        # tokens
        for t in rule.get("tokens", []):
            t2 = _prep_for_search(t)
            if t2 and _token_match(haystack, t2):
                score = 10 + len(t2)
                if (score > best_score) or (
                    score == best_score and priority_index.get(doc_type, 10**9) < priority_index.get(best_type, 10**9)
                ):
                    best_score = score
                    best_type = doc_type
                    best_kw = t

    return best_score, best_type, best_kw


def classify_document(path: Path, text: str, *, verbose: bool = False) -> str:
    """
    Classify document by:
      1) filename prefix code (if present)
      2) keyword rules on filename
      3) keyword rules on content

    Returns a type that exists in PROMPT_FILES (or UNKNOWN).
    """
    allowed_types = _get_allowed_types_from_config()

    # 1) filename prefix (strong signal)
    by_prefix = _detect_type_from_filename_prefix(path.name, allowed_types)
    if by_prefix:
        if verbose:
            print(f"Detected type from filename prefix: {by_prefix}")
        return by_prefix

    # Prepare searchable strings
    name_search = _prep_for_search(path.name)
    content_search = _prep_for_search((text or "")[:8000])

    # Load + merge rules (default + optional external json)
    base = _default_rules()
    extra = _load_external_rules_json()

    # Only keep rules for types that actually exist in the project prompts
    rules = _merge_rules(base, extra, allowed_types)

    # Priority order for tie-breaks
    # (Types not listed fall after the listed ones; UNKNOWN is never a target here.)
    priority = [
        "VC",
        "PJ",
        "PV",
        "RECLASS",
        "UJD",
        "TLL",
    ] + [t for t in allowed_types if t not in {"VC", "PJ", "PV", "RECLASS", "UJD", "TLL"}]

    # 2) keyword rules on filename
    score, dtype, kw = _best_match(name_search, rules, priority)
    if score > 0 and dtype:
        if verbose:
            print(f"Detected type from filename keywords: {dtype} (keyword: '{kw}')")
        return dtype

    # 3) keyword rules on content
    score, dtype, kw = _best_match(content_search, rules, priority)
    if score > 0 and dtype:
        if verbose:
            print(f"Detected type from content keywords: {dtype} (keyword: '{kw}')")
        return dtype

    if verbose:
        print("No type detected -> UNKNOWN")
    return "UNKNOWN"
