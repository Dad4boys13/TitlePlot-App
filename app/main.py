from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import Response
from typing import Optional

from .gis_client import fetch_parcel_geometry
from .pdf_ingest import extract_hyperlinks, extract_text
from .schedule_b_parser import parse_schedule_b
from .renderer import render_plat_svg
from .models import ParcelGeometry

app = FastAPI(title="Title Report Easement Plotter")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/parcels/lookup", response_model=ParcelGeometry)
def parcel_lookup(apn: str, county: Optional[str] = None):
    try:
        return fetch_parcel_geometry(apn, county)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/reports/parse")
async def parse_report(file: UploadFile = File(...)):
    pdf_bytes = await file.read()
    links = extract_hyperlinks(pdf_bytes)
    text = extract_text(pdf_bytes)
    try:
        items = parse_schedule_b(text)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {
        "hyperlinks": [l.__dict__ for l in links],
        "schedule_b_items": [i.model_dump() for i in items],
    }


@app.post("/plats/build")
async def build_plat(
    apn: str = Form(...),
    county: Optional[str] = Form(None),
    front_compass: str = Form("N"),
    file: UploadFile = File(...),
):
    """
    End-to-end: given an APN and the prelim report PDF, fetch real
    parcel geometry from GIS, parse Schedule B, and render the plat.
    Returns SVG directly (image/svg+xml) for easy preview; swap for a
    JSON envelope with a stored file URL once this is wired to real
    storage/a frontend.
    """
    pdf_bytes = await file.read()

    try:
        geometry = fetch_parcel_geometry(apn, county)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=f"Parcel geometry: {e}")

    text = extract_text(pdf_bytes)
    try:
        items = parse_schedule_b(text)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Schedule B parsing: {e}")

    svg = render_plat_svg(geometry, items, front_compass=front_compass)
    return Response(content=svg, media_type="image/svg+xml")
