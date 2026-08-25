from typing import Optional, List, Tuple
from pydantic import BaseModel


class ScheduleBItem(BaseModel):
    item_no: int
    exception_type: str
    affects_text: str
    plottable: bool
    non_plottable_reason: Optional[str] = None
    granted_to: Optional[str] = None
    recorded_ref: Optional[str] = None  # e.g. "Book 8685, Page 166, O.R."
    source_document_url: Optional[str] = None  # hyperlink found in the PDF, if any


class ParcelGeometry(BaseModel):
    apn: str
    source: str  # "gis_lookup" | "manual" | "approximate"
    vertices: List[Tuple[float, float]]  # local plane coords, feet
    edge_labels: List[str]  # compass label per edge, same length as vertices
    confidence_notes: Optional[str] = None


class PlatRequest(BaseModel):
    apn: str
    county_fips: Optional[str] = None  # helps disambiguate the statewide layer
    schedule_b_items: List[ScheduleBItem]
    front_compass: str = "N"  # which compass direction the street frontage is on
