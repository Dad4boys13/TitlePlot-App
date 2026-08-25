import re
from typing import List

from .models import ScheduleBItem
from .geometry import parse_affects_clause

# Matches the start of a numbered Schedule B item, e.g. "7. Easement(s)..."
ITEM_START_RE = re.compile(r"\n\s*(\d{1,3})\.\s+")

AFFECTS_RE = re.compile(r"Affects\s*:?\s*(.+?)(?:\n\s*\n|\n[A-Z][a-z]+\s*:|$)", re.DOTALL)
GRANTED_TO_RE = re.compile(r"Granted to\s*:?\s*(.+?)(?:\n|$)")
RECORDED_RE = re.compile(r"Recorded\s*:?\s*(.+?)(?:\n|$)")
PURPOSE_RE = re.compile(r"Purpose\s*:?\s*(.+?)(?:\n|$)")

NON_PLOTTABLE_MARKERS = [
    ("not specifically delineated", "Explicitly stated as not specifically delineated"),
    ("un-locatable", "Explicitly stated as un-locatable"),
    ("unlocatable", "Explicitly stated as un-locatable"),
    ("blanket", "Blanket easement/restriction, no specific location given"),
]


def split_schedule_b(full_text: str) -> List[str]:
    """
    Isolate the Schedule B section and split it into per-item text blocks.

    Anchors deliberately avoid matching on the heading text alone
    ('Schedule "B"' / 'Schedule B') -- that phrase, in plain form with no
    quote characters, also appears later inside CLTA/ALTA boilerplate
    policy exclusions (e.g. "CALIFORNIA LAND TITLE ASSOCIATION STANDARD
    COVERAGE POLICY - 1990 Schedule B EXCEPTIONS FROM COVERAGE"), and PDF
    text extraction often turns the heading's typographic quotes into
    characters that won't match a literal '"B"' search. Confirmed this
    silently mismatches on a real report -- caught by testing against
    an actual document, not assumed to be correct.

    Instead anchor on the much more specific, single-occurrence phrase
    that follows the real heading, and the specific end-of-exceptions
    marker. If a different title company's template doesn't use these
    exact phrases, this will raise rather than silently grab the wrong
    section -- adjust the anchors for that template.
    """
    start_anchor = "AT THE DATE HEREOF, EXCEPTIONS TO COVERAGE"
    start = full_text.upper().find(start_anchor)
    if start == -1:
        raise ValueError(
            "Could not locate the Schedule B section (expected anchor phrase "
            f"'{start_anchor}' not found) -- this template may differ; "
            "verify the anchor phrase against the actual document."
        )

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


def classify_and_parse(item_no: int, text: str) -> ScheduleBItem:
    lowered = text.lower()

    non_plottable_reason = None
    for marker, reason in NON_PLOTTABLE_MARKERS:
        if marker in lowered:
            non_plottable_reason = reason
            break

    affects_match = AFFECTS_RE.search(text)
    affects_text = affects_match.group(1).strip() if affects_match else ""

    clauses = parse_affects_clause(affects_text) if affects_text else []
    plottable = bool(clauses) and non_plottable_reason is None

    if not plottable and non_plottable_reason is None:
        non_plottable_reason = (
            "No dimensional offset parsed from the Affects clause -- "
            "needs manual review, may require metes-and-bounds or "
            "curve parsing instead of simple edge offsets."
        )

    granted_match = GRANTED_TO_RE.search(text)
    recorded_match = RECORDED_RE.search(text)
    purpose_match = PURPOSE_RE.search(text)

    exception_type = purpose_match.group(1).strip() if purpose_match else text.split(".")[0][:80].strip()

    return ScheduleBItem(
        item_no=item_no,
        exception_type=exception_type,
        affects_text=affects_text or text[:200].strip(),
        plottable=plottable,
        non_plottable_reason=non_plottable_reason,
        granted_to=granted_match.group(1).strip() if granted_match else None,
        recorded_ref=recorded_match.group(1).strip() if recorded_match else None,
    )


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


def is_easement_relevant(exception_type: str, affects_text: str, raw_text: str) -> bool:
    """
    Decide whether a Schedule B item belongs on an easement plat at all.
    Most exceptions in a prelim (tax liens, deeds of trust, judgments,
    trust/vesting issues) are real title matters but have nothing to do
    with physical land location -- they shouldn't appear on the map or
    its legend just because they also happen to lack a directional
    offset clause. Only easement/restriction/encumbrance-type items are
    candidates for the plat (whether or not they end up plottable).
    """
    text = f"{exception_type} {affects_text} {raw_text}".lower()
    if any(kw in text for kw in NOT_RELEVANT_KEYWORDS):
        return False
    return any(kw in text for kw in EASEMENT_RELEVANT_KEYWORDS)


def parse_schedule_b(full_text: str) -> List[ScheduleBItem]:
    raw_items = split_schedule_b(full_text)
    all_items = [classify_and_parse(no, text) for no, text in raw_items]
    raw_by_no = dict(raw_items)
    return [
        item for item in all_items
        if is_easement_relevant(item.exception_type, item.affects_text, raw_by_no[item.item_no])
    ]
