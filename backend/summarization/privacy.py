# backend/summarization/privacy.py

from __future__ import annotations

import re
from typing import Tuple

_RE_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_RE_PHONE = re.compile(r"\b(?:\+?\d[\d\s().-]{7,}\d)\b")
_RE_POSTCODE = re.compile(r"\b\d{4}\s?[A-Z]{2}\b", re.IGNORECASE)
_RE_BSN = re.compile(r"\b\d{9}\b")
_RE_PARKET = re.compile(r"\b\d{2}[./-]\d{6}[/-]\d{2}\b")
_RE_PL = re.compile(r"(?i)\bPL\d{4}-\d{6,}\b")

# Common Dutch address formats.
# 1) Multi-word + (straat/laan/weg/...) + house number
_RE_STREET_WITH_SUFFIX = re.compile(
    r"\b[A-ZÀ-ÿ][\wÀ-ÿ .'-]{1,50}\s(?:straat|laan|weg|plein|dijk|kade|singel|hof|steeg|gracht|allee|pad|boulevard|park|wal|plaats|baan|brug)\s+\d+[a-zA-Z]?\b",
    re.IGNORECASE,
)

# 2) Single-token street/place name + house number, ONLY when preceded by a location preposition.
#    This catches cases like: "op Smidswater 11" / "in Nassauhaven 247".
#    It avoids false positives like "iPhone 14" by requiring (op|in|te|aan|bij|naar) before it.
_RE_ADDRESS_PREP = re.compile(
    r"(?i)\b(op|in|te|aan|bij|naar)\s+([A-ZÀ-ÿ][A-Za-zÀ-ÿ'’-]{2,}(?:[-\s][A-ZÀ-ÿ][A-Za-zÀ-ÿ'’-]{2,}){0,2}\s+\d{1,4}[a-zA-Z]?)\b"
)
_RE_AGE_PHRASE = re.compile(r"\b\d{1,3}\s*-\s*jarige\b", re.IGNORECASE)
_RE_AGE_WORD = re.compile(r"\b\d{1,3}\s*jarige\b", re.IGNORECASE)
_RE_DOB_CONTEXT = re.compile(r"(?i)\b(geboortedatum|geb\.?|geboren(?:\s+op)?|geboren te)\b")

_RE_INIT_SURNAME = re.compile(r"\b(?:[A-Z]\.){1,4}\s*[A-Z][a-zà-ÿ]+(?:[-\s][A-Z][a-zà-ÿ]+){0,2}\b")
# Initials + Dutch surname prefixes (van/de/der/ten/ter/te...) + surname
_RE_INIT_PREFIX_SURNAME = re.compile(
    r"\b(?:[A-Z]\.){1,4}\s*(?:van|de|der|den|ten|ter|te)\s+[A-Z][a-zà-ÿ]+(?:[-\s][A-Z][a-zà-ÿ]+){0,2}\b",
    re.IGNORECASE,
)
_RE_CAP_NAME = re.compile(r"\b[A-Z][a-zà-ÿ]{2,}(?:\s+[A-Z][a-zà-ÿ]{2,}){1,3}\b")
_RE_GENAAAMD_NAME = re.compile(r"(?i)\bgenaamd\s+[A-Z][a-zà-ÿ]{1,}(?:\s+[A-Z][a-zà-ÿ]{1,}){0,3}\b")
_RE_ROLE_NUMBER = re.compile(r"(?i)\b(betrokkene|aangever|aangeefster|getuige)\s+\d+\b")

# Role + name (common leakage in summaries)
_RE_ROLE_NAME = re.compile(
    r"(?i)\b(aangever|aangeefster|getuige|betrokkene)\s+([A-Z][a-zà-ÿ]{2,}(?:[-\s][A-Z][a-zà-ÿ]{2,}){0,3})\b"
)

# IMEI and other technical identifiers
_RE_IMEI = re.compile(r"(?i)\bIMEI\b\s*(?:[:=#]?\s*)?(\d{14,17})\b")
_RE_IMEI_BARE_CTX = re.compile(r"(?i)\bIMEI\b[^\n\r0-9]{0,20}(\d{14,17})")
_RE_BVHKENMERK = re.compile(r"(?i)\b(BVH|SKN|ZK|ZKN|PV|zaak|parket)\s*(?:nr\.?|nummer)?\s*[:=#]?\s*[A-Z0-9][A-Z0-9-]{4,}\b")
_RE_DEVICE_ID = re.compile(r"(?i)\b(serial|serienummer|documentnummer|id(?:-)?nummer|registratienummer)\b\s*[:=#]?\s*[A-Z0-9][A-Z0-9-]{4,}\b")

_RE_SALUTATION = re.compile(
    r"(?i)\b(de heer|mevrouw|dhr\.?|mw\.?|mr\.?|dr\.?|prof\.?)\s+"
    r"([A-Z][a-zà-ÿ]+(?:[-\s][A-Z][a-zà-ÿ]+){0,3})\b"
)
_RE_NAAM_LABEL = re.compile(
    r"(?im)(naam\s*[:/]\s*)([A-Z][a-zà-ÿ]{2,}(?:\s+[A-Z][a-zà-ÿ]{2,}){0,3})"
)
_RE_DATE_NUMERIC = re.compile(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b")
_RE_DATE_WRITTEN = re.compile(
    r"\b\d{1,2}\s+(?:januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december)\s+\d{4}\b",
    re.IGNORECASE,
)
_RE_DOB_LINE = re.compile(r"(?im)^[^\n]*(geboortedatum|geb\.|geboren)[^\n]*$")

_RE_KV_LABEL = re.compile(
    r"(?im)^\s*(voornamen|achternaam|geslachtsnaam|geboorteplaats|nationaliteit|"
    r"skn|id(?:-)?nummer|documentnummer|paspoortnummer|rijbewijsnummer|"
    r"onderzoeksnummer|proces-?verbaal(?:-)?nummer|pv-?nummer|"
    r"zaak(?:-)?nummer|parket(?:-)?nummer|kenmerk|documentkenmerk)\s*:\s*.*$"
)


def _redact_kv_label_lines(t: str) -> str:
    """Redact common 'Label: value' lines before sending text to the LLM."""
    if not t:
        return ""

    def _repl(m: re.Match) -> str:
        line = m.group(0)
        m2 = re.match(r"(?im)^\s*([^:]+)\s*:\s*(.*)$", line)
        if not m2:
            return "[gegevens verwijderd]"

        label = (m2.group(1) or "").strip()
        label_l = label.lower()

        if label_l in {"voornamen", "achternaam", "geslachtsnaam"}:
            return f"{label}: [naam verwijderd]"

        if label_l in {"geboorteplaats", "nationaliteit"}:
            return f"{label}: [gegevens verwijderd]"

        if "nummer" in label_l or "kenmerk" in label_l or "skn" in label_l:
            return f"{label}: [kenmerk verwijderd]"

        return f"{label}: [gegevens verwijderd]"

    return _RE_KV_LABEL.sub(_repl, t)


def pre_anonymize(text: str, doc_type: str) -> str:
    """Replace obvious PII in raw text BEFORE sending it to the LLM."""
    t = text or ""

    # 0) Redact common key-value PII/identifier lines (Voornamen:, SKN:, Zaaknummer:, ...)
    t = _redact_kv_label_lines(t)

    # 0b) Redact PV internal identifiers (PLxxxx-xxxxxx)
    t = _RE_PL.sub("[PV-kenmerk verwijderd]", t)

    # 1) Full lines with geboortedatum / geboren
    t = _RE_DOB_LINE.sub("[geboortedatum verwijderd]", t)

    # 2) Within-line DOB contexts: replace date-like strings only if DOB keyword present
    out_lines = []
    for ln in t.splitlines():
        if _RE_DOB_CONTEXT.search(ln):
            ln = _RE_DATE_NUMERIC.sub("[geboortedatum verwijderd]", ln)
            ln = _RE_DATE_WRITTEN.sub("[geboortedatum verwijderd]", ln)
        out_lines.append(ln)
    t = "\n".join(out_lines)

    # 3) Salutations + name: keep salutation, redact name
    t = _RE_SALUTATION.sub(r"\1 [naam verwijderd]", t)

    # 4) "naam: Firstname Lastname"
    t = _RE_NAAM_LABEL.sub(r"\1[naam verwijderd]", t)

    # 5) Initials + surname
    t = _RE_INIT_PREFIX_SURNAME.sub("[naam verwijderd]", t)
    t = _RE_INIT_SURNAME.sub("[naam verwijderd]", t)

    # 6) BSN (9-digit numbers)
    t = _RE_BSN.sub("[BSN verwijderd]", t)

    # 7) Email addresses
    t = _RE_EMAIL.sub("[e-mail verwijderd]", t)

    # 8) Phone numbers
    def _phone_repl_pre(m: re.Match) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        return "[telefoon verwijderd]" if len(digits) >= 9 else m.group(0)

    t = _RE_PHONE.sub(_phone_repl_pre, t)

    # 9) Postcodes
    t = _RE_POSTCODE.sub("[postcode verwijderd]", t)

    # 10) Street addresses
    t = _RE_STREET_WITH_SUFFIX.sub("[adres verwijderd]", t)
    t = _RE_ADDRESS_PREP.sub(lambda m: f"{m.group(1)} [adres verwijderd]", t)

    # 11) Parket/zaaknummers
    t = _RE_PARKET.sub("[zaaknummer verwijderd]", t)

    # 11b) Extra PV/export identifiers
    t = _RE_PL.sub("[PV-kenmerk verwijderd]", t)

    # 11c) IMEI / technical IDs
    t = _RE_IMEI.sub("IMEI [kenmerk verwijderd]", t)
    t = _RE_IMEI_BARE_CTX.sub("IMEI [kenmerk verwijderd]", t)
    t = _RE_DEVICE_ID.sub("[kenmerk verwijderd]", t)
    t = _RE_BVHKENMERK.sub("[kenmerk verwijderd]", t)

    # 12) Remove "genaamd <n>" fragments
    t = _RE_GENAAAMD_NAME.sub("genaamd [naam verwijderd]", t)

    # 13) Remove role numbering like "betrokkene 11"
    t = _RE_ROLE_NUMBER.sub(lambda m: m.group(1).lower(), t)

    return t


def scrub_names_best_effort(s: str) -> str:
    """Conservative scrub of obvious name patterns that leak through."""
    t = s or ""

    t = _RE_INIT_PREFIX_SURNAME.sub("[naam verwijderd]", t)
    t = _RE_INIT_SURNAME.sub("[naam verwijderd]", t)

    # Role + surname leakage (e.g., "aangever Fortmann")
    t = _RE_ROLE_NAME.sub(lambda m: m.group(1).lower(), t)

    t = re.sub(
        r"(?im)\bbetrokkene[, ]+\b[A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+){0,3}\b",
        "betrokkene",
        t,
    )

    # "officier van justitie <name>" and similar title+name patterns
    t = re.sub(
        r"(?im)\b(officier\s+van\s+justitie|rechter-commissaris|raadsman|advocaat|verbalisant)\b\s+(?:mr\.?\s+)?(?:[A-Z]\.){1,4}\s*(?:van|de|der|den|ten|ter|te)?\s*[A-Z][a-zà-ÿ]+(?:[-\s][A-Z][a-zà-ÿ]+){0,2}\b",
        r"\1 [naam verwijderd]",
        t,
    )

    t = re.sub(r"(?im)\bnaam\s*:\s*" + _RE_CAP_NAME.pattern, "naam: [naam verwijderd]", t)

    return t


def post_scrub_pv_style(s: str) -> str:
    """PV-specific safety scrub (without changing semantics)."""
    t = s or ""

    t = _RE_GENAAAMD_NAME.sub("genaamd [naam verwijderd]", t)
    t = _RE_ROLE_NUMBER.sub(lambda m: m.group(1).lower(), t)

    t = re.sub(r"(?i)\been\s+(man|vrouw|persoon)\s*,?\s*betrokkene\b", "betrokkene", t)
    t = re.sub(
        r"(?i)\b(aangever|aangeefster|getuige|betrokkene)\s*,?\s*een\s+(man|vrouw|persoon)\b",
        r"\1",
        t,
    )

    t = re.sub(r"(?i)\been\s+(man|vrouw|persoon)\b", "een derde", t)
    t = re.sub(r"(?i)\bdoor\s+een\s+(man|vrouw|persoon)\b", "door een derde", t)

    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def redact_pii(summary: str, doc_type: str) -> Tuple[str, bool]:
    """Post-generation PII redaction on the final summary text."""
    s = summary or ""
    original = s

    s = re.sub(r"(?i)\bverdachte\b", "betrokkene", s)
    s = re.sub(r"(?i)\bonderzochte\b", "betrokkene", s)

    # Replace with placeholders (never drop to empty, to preserve grammar/structure).
    s = _RE_EMAIL.sub("[e-mail verwijderd]", s)
    s = _RE_BSN.sub("[BSN verwijderd]", s)

    def _phone_repl(m: re.Match) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        return "[telefoon verwijderd]" if len(digits) >= 9 else m.group(0)

    s = _RE_PHONE.sub(_phone_repl, s)

    s = _RE_POSTCODE.sub("[postcode verwijderd]", s)
    s = _RE_STREET_WITH_SUFFIX.sub("[adres verwijderd]", s)
    s = _RE_ADDRESS_PREP.sub(lambda m: f"{m.group(1)} [adres verwijderd]", s)

    # Always remove PV/export identifiers
    s = _RE_PL.sub("[PV-kenmerk verwijderd]", s)
    s = _RE_PARKET.sub("[zaaknummer verwijderd]", s)

    # IMEI / technical IDs
    s = _RE_IMEI.sub("IMEI [kenmerk verwijderd]", s)
    s = _RE_IMEI_BARE_CTX.sub("IMEI [kenmerk verwijderd]", s)
    s = _RE_DEVICE_ID.sub("[kenmerk verwijderd]", s)
    s = _RE_BVHKENMERK.sub("[kenmerk verwijderd]", s)

    s = re.sub(r"(?im)^\s*(geboortedatum|geb\.|geboren)\b.*$", "[geboortedatum verwijderd]", s)

    s = re.sub(
        r"\b(\d{1,3})\s*-\s*jarige\s+(man|vrouw|persoon)\b",
        r"een \2",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"\b(\d{1,3})\s*jarige\s+(man|vrouw|persoon)\b",
        r"een \2",
        s,
        flags=re.IGNORECASE,
    )
    s = _RE_AGE_PHRASE.sub("", s)
    s = _RE_AGE_WORD.sub("", s)

    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"\s+\n", "\n", s)
    s = s.strip()

    return s, (s != original)


def needs_repair(summary: str) -> bool:
    t = (summary or "").strip()
    if not t:
        return False

    if "[TEKST]" in t or "</TEKST>" in t or "DEELSAMENVATTING" in t.upper():
        return True
    if re.search(r"(?i)\bdeze\s+samenvatting\s+is\s+gebaseerd\b", t):
        return True

    if _RE_EMAIL.search(t) or _RE_BSN.search(t) or _RE_POSTCODE.search(t):
        return True
    if _RE_STREET_WITH_SUFFIX.search(t) or _RE_ADDRESS_PREP.search(t) or _RE_PARKET.search(t):
        return True
    if _RE_PL.search(t):
        return True

    if _RE_IMEI.search(t) or _RE_IMEI_BARE_CTX.search(t):
        return True

    if _RE_DEVICE_ID.search(t) or _RE_BVHKENMERK.search(t):
        return True
    if _RE_DOB_CONTEXT.search(t):
        return True
    if _RE_AGE_PHRASE.search(t) or _RE_AGE_WORD.search(t):
        return True
    if _RE_INIT_PREFIX_SURNAME.search(t) or _RE_INIT_SURNAME.search(t):
        return True

    if _RE_GENAAAMD_NAME.search(t) or _RE_ROLE_NUMBER.search(t):
        return True

    if re.search(r"(?i)\b(betrokkene|aangever|aangeefster|getuige)\s+de\b", t):
        return True
    if re.search(r"(?i)\b(betrokkene|aangever|aangeefster|getuige)\s+computer\b", t):
        return True

    sentences = re.split(r"(?<=[.!?])\s+", t)
    if sentences:
        last = sentences[-1].strip()
        if 0 < len(last.split()) <= 5:
            return True

    return False


def repair_pass(summary: str, doc_type: str, generate_fn) -> str:
    from backend.summarization.prompts import mistral_inst
    from backend.summarization.output_utils import normalize_reduce_text
    from backend.summarization.settings import REPAIR_MAX_NEW

    system_msg = (
        "Je bent een uiterst nauwkeurige forensisch-juridische redacteur. "
        "Je herschrijft tekst zonder nieuwe feiten toe te voegen."
    )

    user_msg = f"""
Herschrijf de onderstaande tekst tot een anonieme, formele tekst (Nederlands) voor een forensisch-psychiatrisch/juridisch verslag.

HARD REGELS
- Voeg GEEN nieuwe feiten toe. Laat GEEN inhoudelijke feiten weg.
- Verwijder uitsluitend persoonsgegevens (namen/initialen, geboortedatum/plaats, leeftijd, adressen, postcodes, telefoons, e-mail, BSN/ID, parket/zaaknummers).
- Gebruik consequente rollen: betrokkene / aangever(aangeefster) / getuige.
- Corrigeer grammatica en maak volledige zinnen (onderwerp + werkwoord). Behoud alle feiten.
- Geen meta-tekst (geen 'dit is een samenvatting', geen verwijzingen naar prompts/tags/bullets).
- Geen markdown-kopjes (geen ###, geen vetgedrukte titels), geen blokken met drie aanhalingstekens.
- Houd de tekst in de verleden tijd.

TEKST:
<<BEGIN_TEKST>>
{(summary or "").strip()}
<<EINDE_TEKST>>
""".strip()

    prompt = mistral_inst(system_msg, user_msg)
    out = generate_fn(prompt, max_new=REPAIR_MAX_NEW)
    return normalize_reduce_text(out)


def dedupe_lines_and_paragraphs(s: str) -> str:
    if not s or not s.strip():
        return s

    lines = s.splitlines()
    seen = set()
    out_lines = []
    for ln in lines:
        key = ln.strip()
        if not key:
            out_lines.append(ln)
            continue
        if key in seen:
            continue
        seen.add(key)
        out_lines.append(ln)

    t = "\n".join(out_lines)

    paras = [p.strip() for p in re.split(r"\n\s*\n", t) if p.strip()]
    out_paras = []
    prev = None
    for p in paras:
        if prev is not None and p == prev:
            continue
        out_paras.append(p)
        prev = p

    return "\n\n".join(out_paras).strip()


def trim_trailing_fragment(s: str) -> str:
    t = (s or "").strip()
    if not t:
        return t

    sentences = re.split(r"(?<=[.!?])\s+", t)
    if len(sentences) < 2:
        return t

    last = sentences[-1].strip()
    if not last:
        return t

    if len(last.split()) > 5:
        return t

    common_verbs = {
        "is", "was", "waren", "werd", "werden", "heeft", "hebben", "had", "hadden",
        "blijkt", "bleek", "bleken", "vond", "vonden", "kwam", "kwamen", "zei",
        "zeiden", "verklaarde", "verklaarden", "stuurde", "vroeg", "vroegen",
        "betaalde", "betaalden", "onderzocht", "onderzochten", "gevonden", "trof",
        "troffen", "opgenomen",
    }
    tokens = {re.sub(r"[^\wà-ÿ'-]+", "", w.lower()) for w in last.split()}
    if tokens.isdisjoint(common_verbs):
        return " ".join(sentences[:-1]).strip()

    return t


def shorten_ujd(s: str) -> str:
    t = s or ""

    t = re.sub(r"(?i)\b(primair|subsidiair|meer subsidiair)\b", "", t)
    t = re.sub(r"(?i)\bfeit\s*\d+\b", "", t)

    t = re.sub(
        r"(?i)\b(start-?\s*en\s*einddatum\s*proeftijd|startdatum\s*proeftijd|einddatum\s*proeftijd)\b.*",
        "",
        t,
    )

    t = re.sub(r"(?i)\bgijzeling\b.*", "", t)
    t = re.sub(r"€\s*\d{1,3}(?:\.\d{3})*(?:,\d{2})?", "", t)

    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()