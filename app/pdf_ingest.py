"""
PDF ingestion.

Two jobs:
  1. Extract embedded link annotations (URI targets) from the PDF --
     this is how we found the real hyperlinked exhibits (tract map,
     easement grant deeds, etc.) in the 26-13059-KBJ example. Confirmed
     working via pypdf's /Annots inspection.
  2. Extract text for the Schedule B parser to run against. Falls back
     to OCR (pytesseract) for scanned pages with no embedded text layer.

NOTE: following the extracted hyperlinks (actually downloading the
linked documents) is NOT done here. Those links point at a specific
title company's closing platform (e.g. Qualia) and are typically
session-scoped / authenticated -- see the conversation history for why
an anonymous fetch won't work. That's a separate, per-platform
integration (API key or authenticated session) to build once you know
which platforms your source reports come from.
"""
from dataclasses import dataclass
from typing import List, Optional
from io import BytesIO

from pypdf import PdfReader

try:
    import pytesseract
    from pdf2image import convert_from_bytes
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False


@dataclass
class ExtractedLink:
    page: int
    uri: Optional[str]
    dest: Optional[str]  # internal document destination, if not an external URI


def extract_hyperlinks(pdf_bytes: bytes) -> List[ExtractedLink]:
    reader = PdfReader(BytesIO(pdf_bytes))
    links = []
    for i, page in enumerate(reader.pages):
        annots = page.get("/Annots")
        if not annots:
            continue
        for a in annots:
            obj = a.get_object()
            if obj.get("/Subtype") != "/Link":
                continue
            action = obj.get("/A")
            if not action:
                continue
            action = action.get_object()
            uri = action.get("/URI")
            dest = action.get("/D")
            if uri or dest:
                links.append(ExtractedLink(page=i + 1, uri=uri, dest=str(dest) if dest else None))
    return links


def extract_text(pdf_bytes: bytes, ocr_if_needed: bool = True, min_chars_per_page: int = 40) -> str:
    """
    Extract text page by page. If a page has almost no embedded text
    (typical of a scanned/flattened page), OCR it -- if pytesseract and
    pdf2image (+ poppler + tesseract binaries) are installed.
    """
    reader = PdfReader(BytesIO(pdf_bytes))
    full_text_parts = []
    pages_needing_ocr = []

    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if len(text.strip()) < min_chars_per_page:
            pages_needing_ocr.append(i)
            full_text_parts.append(None)  # placeholder, filled below if OCR runs
        else:
            full_text_parts.append(text)

    if pages_needing_ocr and ocr_if_needed:
        if not OCR_AVAILABLE:
            raise RuntimeError(
                "Some pages appear to be scanned (little/no embedded text) and "
                "would need OCR, but pytesseract/pdf2image aren't installed. "
                "Install them (plus the tesseract-ocr and poppler-utils system "
                "packages) -- see README."
            )
        images = convert_from_bytes(pdf_bytes)
        for i in pages_needing_ocr:
            full_text_parts[i] = pytesseract.image_to_string(images[i])

    return "\n".join(p or "" for p in full_text_parts)
