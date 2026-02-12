from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# -----------------------------
# Normalization helpers
# -----------------------------
def _normalize(s: str) -> str:
    s = (s or "").lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s


def _prep_for_search(s: str) -> str:
    s = _normalize(s)
    s = re.sub(r"[_\-.]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _sanitize_for_classifier(s: str) -> str:
    """
    Light cleanup so headers/footers don't hide real signals.
    (Keep it conservative: we only remove very common boilerplate.)
    """
    t = (s or "").replace("\r\n", "\n")
    t = re.sub(r"(?i)Pagina\s+\d+\s+van\s+\d+\s*", " ", t)
    t = re.sub(r"(?im)^\s*Retouradres.*$", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _token_match(haystack: str, token: str) -> bool:
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


# -----------------------------
# Config-driven allowed types
# -----------------------------
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
        return ["PJ", "VC", "PV", "RECLASS", "UJD", "TLL"]


# -----------------------------
# Rules (defaults)
# -----------------------------
def _default_rules() -> Dict[str, Dict[str, List[str]]]:
    """
    Default keyword rules.
    Keep phrases reasonably specific to avoid false positives.
    """
    return {
        "TLL": {
            "phrases": [
                "ervan verdacht wordt",
                "tenlastelegging",
                "ten laste gelegd",
                "vordering tot inbewaringstelling",
                "vordering inbewaringstelling",
                "inbewaringstelling",
                "in bewaringstelling",
                "vordering bewaring",
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
                "openstaande zaken betreffende misdrijven",
                "volledig afgedane zaken betreffende misdrijven",
            ],
            "tokens": ["ujd"],
        },
        "RECLASS": {
            "phrases": [
                "reclasseringsrapport",
                "reclasseringsadvies",
                "reclassering nederland",
                "ggz reclassering",
                "toezicht",
                "meldplicht",
                "voortgangsrapportage",
                "adviesrapportage",
                "risic",
                "risc",
                "vroeghulp",
            ],
            "tokens": ["reclass", "recl"],
        },
        "VC": {
            "phrases": [
                "voorgeleidingsconsult",
                "voor geleidingsconsult",
                "voorgeleiding",
                "voor geleiding",
                "nifp consult",
                "nifpconsult",
                "nifp consulent",
                "consulent",
                "pro justitia consult",
                "projustitia consult",
                "trajectconsult",
                "verhoor raadkamer",
                "stukken rc",
                "rechter commissaris",
                "rechter-commissaris",
                "psychiatrisch consult",
                "psychologisch consult",
                "gz psycholoog",
                "psychiater",
                "psycholoog",
            ],
            "tokens": ["vc", "vgc"],
        },
        "PV": {
            "phrases": [
                "proces verbaal",
                "proces-verbaal",
                "procesverbaal",
                "proces verbaal van bevindingen",
                "proces verbaal van aangifte",
                "proces verbaal van verhoor",
                "proces verbaal van voorgeleiding",
                "pv vgl",
                "pvvgl",
                "aangifte",
                "verbalisant",
                "getuige",
            ],
            "tokens": ["pv"],
        },
        "PJ": {
            "phrases": [
                "rapport pro justitia",
                "rapportage pro justitia",
                "pro justitia rapport",
                "projustitia rapport",
                "dubbellrapport pro justitia",
                "monorapportage pro justitia",
                "toerekeningsvatbaarheid",
                "toerekeningsvatbaar",
                "risicotaxatie",
                "recidiverisico",
                "dsm",
                "wais",
                "pcl r",
            ],
            "tokens": ["pj"],
        },
    }


def _load_external_rules_json() -> Dict[str, Dict[str, List[str]]]:
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


def _fallback_base_rule_for_type(doc_type: str, base: Dict[str, Dict[str, List[str]]]) -> Dict[str, List[str]]:
    """
    If PROMPT_FILES has variant keys (e.g. OUD_PJ), inherit the closest base rule.
    """
    u = (doc_type or "").upper()
    if u in base:
        return base[u]
    if "RECLASS" in u or u.startswith("RECL"):
        return base.get("RECLASS", {"phrases": [], "tokens": []})
    if "UJD" in u:
        return base.get("UJD", {"phrases": [], "tokens": []})
    if "TLL" in u or "IBS" in u:
        return base.get("TLL", {"phrases": [], "tokens": []})
    if "PV" in u:
        return base.get("PV", {"phrases": [], "tokens": []})
    if "VC" in u or "VGC" in u:
        return base.get("VC", {"phrases": [], "tokens": []})
    if "PJ" in u:
        return base.get("PJ", {"phrases": [], "tokens": []})
    return {"phrases": [], "tokens": []}


def _merge_rules(
    base: Dict[str, Dict[str, List[str]]],
    extra: Dict[str, Dict[str, List[str]]],
    allowed_types: List[str],
) -> Dict[str, Dict[str, List[str]]]:
    merged: Dict[str, Dict[str, List[str]]] = {}
    allowed = set(t.upper() for t in allowed_types)

    for t in allowed:
        base_t = _fallback_base_rule_for_type(t, base)
        extra_t = extra.get(t, {"phrases": [], "tokens": []})

        phrases = _dedupe_keep_order(list(base_t.get("phrases", [])) + list(extra_t.get("phrases", [])))
        tokens = _dedupe_keep_order(list(base_t.get("tokens", [])) + list(extra_t.get("tokens", [])))

        merged[t] = {"phrases": phrases, "tokens": tokens}

    return merged


# -----------------------------
# Strong-pattern detection
# -----------------------------
_RE_PL = re.compile(r"\bpl\d{4}-\d{6,}\b")  # normalized text => lowercase
_RE_TLL_BLOCK = re.compile(r"\bervan verdacht wordt\b")
_RE_UJD_OPEN = re.compile(r"\bopenstaande zaken betreffende misdrijven\b")
_RE_UJD_AF = re.compile(r"\bvolledig afgedane zaken betreffende misdrijven\b")
_RE_PJ_TOER = re.compile(r"\btoerekeningsvat\b")
_RE_VC = re.compile(r"\bvoorgeleidingsconsult\b")
_RE_RECLASS = re.compile(r"\breclassering\b")


def _detect_strong(content_search: str, allowed_types: List[str]) -> Optional[str]:
    allowed = set(t.upper() for t in allowed_types)

    # UJD: very distinctive headings
    if "UJD" in allowed and (_RE_UJD_OPEN.search(content_search) or _RE_UJD_AF.search(content_search)):
        return "UJD"

    # TLL: distinctive block marker
    if "TLL" in allowed and _RE_TLL_BLOCK.search(content_search):
        return "TLL"

    # PV: PL-number + proces-verbaal is a strong combo
    if "PV" in allowed:
        if _RE_PL.search(content_search) and "proces verbaal" in content_search:
            return "PV"

    # PJ: toerekeningsvat* is very PJ-specific
    if "PJ" in allowed and _RE_PJ_TOER.search(content_search):
        return "PJ"

    # VC: voorgeleid* consult is very distinctive
    if "VC" in allowed and _RE_VC.search(content_search):
        return "VC"

    # RECLASS: reclassering + toezicht/voorwaarden-ish markers
    if "RECLASS" in allowed and _RE_RECLASS.search(content_search):
        if ("toezicht" in content_search) or ("meldplicht" in content_search) or ("risc" in content_search) or ("risic" in content_search):
            return "RECLASS"

    return None


# -----------------------------
# Scoring (sum of matches)
# -----------------------------
def _score_matches(haystack: str, rule: Dict[str, List[str]]) -> Tuple[int, List[str]]:
    score = 0
    hits: List[str] = []

    for p in rule.get("phrases", []):
        p2 = _prep_for_search(p)
        if p2 and p2 in haystack:
            score += 100 + len(p2)
            hits.append(p)

    for t in rule.get("tokens", []):
        t2 = _prep_for_search(t)
        if t2 and _token_match(haystack, t2):
            score += 10 + len(t2)
            hits.append(t)

    return score, hits


def _detect_type_from_filename_prefix(filename: str, allowed_types: List[str]) -> Optional[str]:
    prepared = _prep_for_search(Path(filename).stem)
    parts = prepared.split()
    if not parts:
        return None

    # try first token (old behavior)
    first = parts[0].upper()
    if first in set(allowed_types):
        return first

    # NEW: also try second token (helps for "Oud PJ_1" style names)
    if len(parts) >= 2:
        second = parts[1].upper()
        if second in set(allowed_types):
            return second

    return None


def classify_document(path: Path, text: str, *, verbose: bool = False) -> str:
    allowed_types = _get_allowed_types_from_config()

    # 1) filename prefix (strong)
    by_prefix = _detect_type_from_filename_prefix(path.name, allowed_types)
    if by_prefix:
        if verbose:
            print(f"Detected type from filename prefix: {by_prefix}")
        return by_prefix

    # Prepare searchable strings (light sanitize + normalize)
    name_search = _prep_for_search(path.name)
    content_raw = _sanitize_for_classifier((text or "")[:20000])  # NEW: look a bit deeper than 8000
    content_search = _prep_for_search(content_raw)

    base = _default_rules()
    extra = _load_external_rules_json()
    rules = _merge_rules(base, extra, allowed_types)

    # Tie-break priority
    priority = [
        "VC",
        "PJ",
        "PV",
        "RECLASS",
        "UJD",
        "TLL",
    ] + [t for t in allowed_types if t not in {"VC", "PJ", "PV", "RECLASS", "UJD", "TLL"}]

    priority_index = {t: i for i, t in enumerate(priority)}

    # 1.5) strong patterns (content)
    strong = _detect_strong(content_search, allowed_types)
    if strong:
        if verbose:
            print(f"Detected type from STRONG content pattern: {strong}")
        return strong

    # 2) score by filename + content (sum of all matches)
    scored: List[Tuple[int, str, List[str], List[str]]] = []
    for dtype, rule in rules.items():
        s_name, h_name = _score_matches(name_search, rule)
        s_cont, h_cont = _score_matches(content_search, rule)

        # Weight filename a bit higher (often reliable)
        total = int(s_name * 1.3) + s_cont
        if total > 0:
            scored.append((total, dtype, h_name, h_cont))

    if not scored:
        if verbose:
            print("No type detected -> UNKNOWN")
        return "UNKNOWN"

    # choose best; tie-break by priority
    scored.sort(key=lambda x: (x[0], -10_000_000 + -priority_index.get(x[1], 10**9)), reverse=True)
    best_total, best_type, best_hn, best_hc = scored[0]

    second_total = scored[1][0] if len(scored) > 1 else 0

    # 3) ambiguity handling: if top-2 are too close, prefer UNKNOWN
    # (reduces wrong prompts; UNKNOWN prompt is safer)
    if second_total > 0:
        # close if within 15% OR within 40 points
        if (best_total <= int(second_total * 1.15)) or ((best_total - second_total) < 40):
            if verbose:
                print(f"Ambiguous top-2: {best_type}={best_total} vs second={second_total} -> UNKNOWN")
            return "UNKNOWN"

    if verbose:
        print(f"Detected type: {best_type} (score={best_total})")
        if best_hn:
            print(f"  filename hits: {best_hn}")
        if best_hc:
            print(f"  content hits: {best_hc}")

    return best_type
