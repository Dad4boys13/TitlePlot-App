# Title Report Easement Plotter -- backend prototype

## Status honestly, as of this build

**Validated against a real report** (26-13059-KBJ, Lot 8 of Tract 6469,
Huntington Beach): the Schedule B parser correctly found all 16
exceptions, correctly identified Items 7/9/10/11 as plottable with the
exact right directions and distances, correctly flagged Item 8
(avigation) as non-plottable, and the offset-geometry engine correctly
produces mitered strip polygons (including a clean L-join for the
compound Item 10/11 clauses). Also confirmed embedded PDF hyperlink
extraction works and found the real linked exhibits in that report
(tract map, easement grant deeds, etc.).

**NOT yet validated / open items:**
- `gis_client.py`'s call to the CA DWR statewide parcel layer
  (`i15_Parcels_Assessor_Lightbox`) was written and the endpoint
  confirmed reachable/queryable via a browser-context search, but was
  **never actually queried** -- the dev sandbox this was built in has
  no network egress. **Test this first**, against a few real APNs,
  before trusting it. In particular verify: (a) it actually returns
  polygon geometry (not just points), (b) how it handles curved
  boundaries, (c) how current/accurate it is vs. the recorded map.
- Curved lot boundaries (very common -- this test lot had a
  compound/reverse curve frontage) are NOT handled by the geometry
  engine at all yet. `geometry.py`'s `Parcel` class assumes straight
  edges. If the GIS source returns dense-enough vertex sampling along
  curves, this may not matter (a polygon with many short straight
  segments approximates a curve fine for offsetting). If it returns
  true arc geometry, `Parcel` will need extending.
- OCR fallback (`pdf_ingest.py`) is wired but untested against an
  actual scanned prelim -- the one example used had a real text layer.
- Following the hyperlinked exhibits (actually downloading the linked
  documents, e.g. the tract map, grant deeds) is NOT implemented.
  Those links point at title-company-specific platforms (this example
  used Qualia) and are typically authenticated/session-scoped -- this
  needs a per-platform integration (API access or an authenticated
  session), not a generic fetch.
- The Item 6 vs Item 8 legend-inclusion judgment call (see project
  history) -- a real human plotter excluded a generic "whatever's on
  the tract map" catch-all but included a specific-but-un-locatable
  easement. Current filter includes both. Worth a "needs review" queue
  for ambiguous cases like this rather than a binary include/exclude.
- No auth, no persistence/database, no frontend. This is the parsing +
  geometry + rendering core only.

## Architecture

```
app/
  main.py            FastAPI routes
  models.py          Pydantic schemas
  gis_client.py       APN -> parcel geometry (CA DWR statewide layer;
                       structured for county-specific overrides)
  pdf_ingest.py       Hyperlink extraction + text extraction (+ OCR fallback)
  schedule_b_parser.py  Schedule B text -> structured, classified exceptions
  geometry.py          Polygon + per-edge offset engine (validated)
  renderer.py           Structured data -> SVG plat
```

## Endpoints

- `GET /parcels/lookup?apn=...&county=...` -- fetch parcel geometry
- `POST /reports/parse` -- upload a prelim PDF, get back hyperlinks + parsed Schedule B items
- `POST /plats/build` -- form fields `apn`, `county`, `front_compass` + PDF file -> SVG plat, end to end

## Running locally

```
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then, e.g.:
```
curl "http://localhost:8000/parcels/lookup?apn=146-551-21"
```
**This is the first thing to try** -- it'll tell you immediately
whether the GIS source is usable as-is.

## Deploying

Recommended starting point: Render or Railway (Docker deploy from this
repo, managed Postgres when you add persistence, cheap to start).
Add S3 or Cloudflare R2 for storing uploaded PDFs once this needs to
retain files rather than process them in-request.

## Known template dependency

The Schedule B parser's section anchors (`AT THE DATE HEREOF,
EXCEPTIONS TO COVERAGE` / `*END OF EXCEPTIONS`) matched this title
company's (Consumer's Title Co. of CA / Stewart) template exactly.
Different underwriters/title companies phrase this differently --
expect to add per-template anchor variants as you test against more
real reports, and treat "anchor not found" (which raises a clear
error) as the signal to add a new template rather than silently
guessing.
