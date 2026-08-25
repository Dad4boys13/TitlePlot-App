
"""
Parcel geometry lookup.

Primary source: the CA Dept. of Water Resources statewide assessor
parcel layer (i15_Parcels_Assessor_Lightbox), which is public and
covers all 58 counties. This was verified reachable and queryable
from a normal internet connection (see README) -- it could NOT be
tested from the dev sandbox that first wrote this code, since that
sandbox has no network egress. TEST THIS FIRST after deploying,
before trusting it for real parcels.

Fallback slots are structured in for county-specific authoritative
sources (e.g. Orange County's OC Landbase, which is derived from
recorded legal documents rather than assessor rolls and would be a
better source of truth where available) -- add these per-county as
you validate them.
"""
import math
from typing import Optional
import requests

from .models import ParcelGeometry

DWR_STATEWIDE_LAYER = (
    "https://gis.water.ca.gov/arcgis/rest/services/"
    "Planning/i15_Parcels_Assessor_Lightbox/MapServer/0/query"
)

# Register county-specific higher-quality sources here as they're
# validated. Key by county name (as it would appear in the prelim
# report) -> a callable(apn) -> Optional[dict] (raw geojson feature).
COUNTY_OVERRIDES = {
    # "Orange": query_oc_landbase,  # TODO: implement once validated
}


def _bearing_label(dx, dy):
    """Rough compass label for an edge vector, for offset-parser matching."""
    angle = (math.degrees(math.atan2(dx, dy)) + 360) % 360  # 0=N,90=E,...
    if 45 <= angle < 135:
        return "E"
    if 135 <= angle < 225:
        return "S"
    if 225 <= angle < 315:
        return "W"
    return "N"


def _lonlat_ring_to_local_feet(ring):
    """
    Project a WGS84 lon/lat ring onto a local flat-earth tangent plane
    centered on the ring's centroid, in feet. Fine at parcel scale;
    NOT valid for anything spanning more than a few hundred meters.
    """
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    lat0 = sum(lats) / len(lats)
    lon0 = sum(lons) / len(lons)
    meters_per_deg_lat = 111_320.0
    meters_per_deg_lon = 111_320.0 * math.cos(math.radians(lat0))
    feet_per_meter = 3.28084
    pts = []
    for lon, lat in ring:
        x_m = (lon - lon0) * meters_per_deg_lon
        y_m = (lat - lat0) * meters_per_deg_lat
        pts.append((x_m * feet_per_meter, y_m * feet_per_meter))
    return pts


def fetch_parcel_geometry(apn: str, county: Optional[str] = None) -> ParcelGeometry:
    """
    Look up a parcel's boundary geometry by APN.
    Raises ValueError if nothing is found or the service is unreachable.
    """
    if county and county in COUNTY_OVERRIDES:
        feature = COUNTY_OVERRIDES[county](apn)
        source = f"county_override:{county}"
        if feature:
            return _feature_to_geometry(apn, feature, source)

    # normalize common APN formatting differences (dashes/spaces)
    apn_variants = {apn, apn.replace("-", ""), apn.replace(" ", "")}
    for candidate in apn_variants:
        params = {
            "where": f"PARCEL_APN='{candidate}'",
            "outFields": "*",
            "f": "geojson",
        }
        try:
            resp = requests.get(DWR_STATEWIDE_LAYER, params=params, timeout=45)
            resp.raise_for_status()
            data = resp.json()
        except requests.Timeout:
            raise ValueError(
                "GIS lookup timed out after 45s. The statewide DWR layer may be "
                "slow for unfiltered APN queries at scale -- consider adding a "
                "county-specific filter/source, or a background job + cache "
                "instead of a synchronous request-time lookup."
            )
        except requests.RequestException as e:
            raise ValueError(f"GIS lookup failed (network/service error): {e}")

        features = data.get("features", [])
        if features:
            return _feature_to_geometry(apn, features[0], "dwr_statewide_lightbox")

    raise ValueError(
        f"No parcel found for APN '{apn}' in the statewide layer. "
        "Try a county-specific source, or fall back to manual/approximate geometry."
    )


def _feature_to_geometry(apn: str, feature: dict, source: str) -> ParcelGeometry:
    geom = feature.get("geometry", {})
    gtype = geom.get("type")
    if gtype == "Polygon":
        ring = geom["coordinates"][0]
    elif gtype == "MultiPolygon":
        ring = geom["coordinates"][0][0]
    else:
        raise ValueError(f"Unexpected geometry type from GIS source: {gtype}")

    # Drop the closing duplicate vertex GeoJSON rings include.
    if ring[0] == ring[-1]:
        ring = ring[:-1]

    local_pts = _lonlat_ring_to_local_feet(ring)
    n = len(local_pts)
    edge_labels = []
    for i in range(n):
        x1, y1 = local_pts[i]
        x2, y2 = local_pts[(i + 1) % n]
        edge_labels.append(_bearing_label(x2 - x1, y2 - y1))

    return ParcelGeometry(
        apn=apn,
        source=source,
        vertices=local_pts,
        edge_labels=edge_labels,
        confidence_notes=(
            "Geometry from public GIS parcel layer -- verify against the "
            "recorded map for anything relied on precisely; assessor/GIS "
            "parcel layers are not surveys."
        ),
    )