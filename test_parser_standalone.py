"""
Standalone smoke test: run the actual parsing regex/logic from
schedule_b_parser.py against the real uploaded prelim report, without
needing pydantic/fastapi installed (this sandbox has no network access
to pip install them). Validates the parsing logic itself, which is
copy-pasted here to avoid the pydantic import in models.py.
"""
import re
from pypdf import PdfReader

ITEM_START_RE = re.compile(r"\n\s*(\d{1,3})\.\s+")
AFFECTS_RE = re.compile(r"Affects\s*:?\s*(.+?)(?:\n\s*\n|\n[A-Z][a-z]+\s*:|$)", re.DOTALL)
GRANTED_TO_RE = re.compile(r"Granted to\s*:?\s*(.+?)(?:\n|$)")
RECORDED_RE = re.compile(r"Recorded\s*:?\s*(.+?)(?:\n|$)")
PURPOSE_RE = re.compile(r"Purpose\s*:?\s*(.+?)(?:\n|$)")

DIRECTION_MAP = {
    "northerly": "N", "north": "N", "southerly": "S", "south": "S",
    "easterly": "E", "east": "E", "westerly": "W", "west": "W",
    "rear": "REAR", "front": "FRONT",
}
CLAUSE_RE = re.compile(
    r"(northerly|southerly|easterly|westerly|north|south|east|west|rear|front)\s+([\d.]+)\s*feet",
    re.IGNORECASE,
)
NON_PLOTTABLE_MARKERS = [
    ("not specifically delineated", "Explicitly stated as not specifically delineated"),
    ("un-locatable", "Explicitly stated as un-locatable"),
    ("unlocatable", "Explicitly stated as un-locatable"),
    ("blanket", "Blanket easement/restriction, no specific location given"),
]


def split_schedule_b(full_text):
    start_anchor = "AT THE DATE HEREOF, EXCEPTIONS TO COVERAGE"
    start = full_text.upper().find(start_anchor)
    if start == -1:
        raise ValueError(f"Could not locate Schedule B (anchor '{start_anchor}' not found)")
    end_markers = ["*END OF EXCEPTIONS", "END OF EXCEPTIONS"]
    end = len(full_text)
    for marker in end_markers:
        idx = full_text.find(marker, start)
        if idx != -1:
            end = min(end, idx)
    body = full_text[start:end]
    matches = list(ITEM_START_RE.finditer(body))
    items = []
    for i, m in enumerate(matches):
        item_no = int(m.group(1))
        seg_start = m.end()
        seg_end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        items.append((item_no, body[seg_start:seg_end].strip()))
    return items


def classify_and_parse(item_no, text):
    lowered = text.lower()
    non_plottable_reason = None
    for marker, reason in NON_PLOTTABLE_MARKERS:
        if marker in lowered:
            non_plottable_reason = reason
            break
    affects_match = AFFECTS_RE.search(text)
    affects_text = affects_match.group(1).strip() if affects_match else ""
    clauses = CLAUSE_RE.findall(affects_text) if affects_text else []
    plottable = bool(clauses) and non_plottable_reason is None
    if not plottable and non_plottable_reason is None:
        non_plottable_reason = "No dimensional offset parsed from the Affects clause"
    granted_match = GRANTED_TO_RE.search(text)
    recorded_match = RECORDED_RE.search(text)
    purpose_match = PURPOSE_RE.search(text)
    exception_type = purpose_match.group(1).strip() if purpose_match else text.split(".")[0][:80].strip()
    return {
        "item_no": item_no,
        "exception_type": exception_type,
        "affects_text": affects_text or text[:200].strip(),
        "plottable": plottable,
        "non_plottable_reason": non_plottable_reason,
        "granted_to": granted_match.group(1).strip() if granted_match else None,
        "recorded_ref": recorded_match.group(1).strip() if recorded_match else None,
        "parsed_clauses": clauses,
    }


EASEMENT_RELEVANT_KEYWORDS = [
    "easement", "right of way", "right-of-way", "encroachment",
    "covenant", "restriction", "reservation", "set-back", "setback",
    "avigation", "cc&r", "c.c.&r", "conditions and restrictions",
    "as shown on the map of said tract", "dedication",
]
NOT_RELEVANT_KEYWORDS = [
    "property taxes", "tax defaulted", "supplemental taxes",
    "deed of trust", "abstract of judgment", "statement of information",
    "owner's affidavit", "owner\u2019s affidavit", "invalidity or defect in the title",
    "water rights",
]


def is_easement_relevant(exception_type, affects_text, raw_text):
    text = f"{exception_type} {affects_text} {raw_text}".lower()
    if any(kw in text for kw in NOT_RELEVANT_KEYWORDS):
        return False
    return any(kw in text for kw in EASEMENT_RELEVANT_KEYWORDS)


if __name__ == "__main__":
    reader = PdfReader("/mnt/user-data/uploads/Prelim_Package__2_-_2026-08-18T132103_589.pdf")
    full_text = "\n".join(p.extract_text() or "" for p in reader.pages)

    raw_items = split_schedule_b(full_text)
    print(f"Found {len(raw_items)} total Schedule B items; filtering to easement-relevant ones\n")
    relevant_count = 0
    for item_no, text in raw_items:
        result = classify_and_parse(item_no, text)
        if not is_easement_relevant(result['exception_type'], result['affects_text'], text):
            continue
        relevant_count += 1
        print(f"Item {result['item_no']}: plottable={result['plottable']}")
        print(f"  type: {result['exception_type']}")
        print(f"  affects: {result['affects_text'][:100]!r}")
        if result['parsed_clauses']:
            print(f"  parsed clauses: {result['parsed_clauses']}")
        if result['non_plottable_reason']:
            print(f"  non-plottable reason: {result['non_plottable_reason']}")
        if result['granted_to']:
            print(f"  granted to: {result['granted_to']}")
        if result['recorded_ref']:
            print(f"  recorded: {result['recorded_ref']}")
        print()
