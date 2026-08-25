
"""
Parcel geometry lookup.

Primary source: the CA Dept. of Water Resources statewide assessor
parcel layer (i15_Parcels_Assessor_Lightbox), covering all 58 counties.

IMPORTANT, learned the hard way: filtering this layer by APN (even with
the correct field name, PARCEL_APN) times out. The service's own schema
shows only two indexes -- one on OBJECTID, one spatial index on SHAPE.
There is NO index on PARCEL_APN, so an attribute filter forces a full
scan across every parcel in California and gets rejected under load
(503 "Wait timeout for the request exceeded").

The fix: use the index that actually exists. Geocode the property
address to a lat/lon first (free, via the US Census geocoder), then run
a SPATIAL query (point-in-polygon) against this layer, which uses the
SHAPE index and should be fast regardless of table size. The returned
feature's PARCEL_APN is then used to cross-check against the expected
APN as a sanity check, not as the query key.
"""
import math
from typing import Optional
import requests

from .models import ParcelGeometry

DWR_STATEWIDE_LAYER = (
    "https://gis.water.ca.gov/arcgis/rest/services/"
    "Planning/i15_Parcels_Assessor_Lightbox/MapServer/0/query"
)

CENSUS_GEOCODER = (
    "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
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


def geocode_address(address: str):
    """
    Free, no-API-key geocoder (US Census Bureau), US addresses only.
    Returns (lon, lat) or raises ValueError if no match.
    """
    params = {
        "address": address,
        "benchmark": "Public_AR_Current",
        "format": "json",
    }
    try:
        resp = requests.get(CENSUS_GEOCODER, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        raise ValueError(f"Geocoding failed (network/service error): {e}")

    matches = data.get("result", {}).get("addressMatches", [])
    if not matches:
        raise ValueError(f"Could not geocode address: '{address}'")

    coords = matches[0]["coordinates"]
    return coords["x"], coords["y"]  # lon, lat


def fetch_parcel_geometry_by_address(
    address: str, expected_apn: Optional[str] = None
) -> ParcelGeometry:
    """
    Geocode the address, then run a spatial (point-in-polygon) query
    against the statewide parcel layer -- this uses the layer's actual
    spatial index, unlike an APN attribute filter (see module docstring).
    """
    lon, lat = geocode_address(address)

    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "f": "geojson",
    }
    try:
        resp = requests.get(DWR_STATEWIDE_LAYER, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.Timeout:
        raise ValueError(
            "GIS spatial lookup timed out after 30s -- unexpected, since "
            "this query should use the layer's spatial index. Investigate "
            "further before assuming this data source is unusable."
        )
    except requests.RequestException as e:
        raise ValueError(f"GIS lookup failed (network/service error): {e}")

    features = data.get("features", [])
    if not features:
        raise ValueError(
            f"No parcel found containing the geocoded point for '{address}' "
            f"({lon}, {lat}). The point may have geocoded slightly outside "
            "the actual parcel boundary -- consider a small search buffer."
        )

    feature = features[0]
    geometry = _feature_to_geometry(
        feature.get("properties", {}).get("PARCEL_APN", expected_apn or "unknown"),
        feature,
        "dwr_statewide_lightbox_spatial",
    )

    if expected_apn:
        found_apn = feature.get("properties", {}).get("PARCEL_APN", "")
        if found_apn and found_apn.replace("-", "") != expected_apn.replace("-", ""):
            geometry.confidence_notes = (
                f"{geometry.confidence_notes} WARNING: expected APN "
                f"'{expected_apn}' but the parcel found at this address is "
                f"APN '{found_apn}' -- verify the address/APN match."
            )

    return geometry


def fetch_parcel_geometry(apn: str, county: Optional[str] = None) -> ParcelGeometry:
    """
    DEPRECATED PATH: attribute-based APN lookup. Confirmed via testing
    that this times out (503) against the statewide layer regardless of
    correct field name, because PARCEL_APN has no index. Kept only for
    county overrides that might support it efficiently; the real lookup
    path is fetch_parcel_geometry_by_address(). Raises ValueError.
    """
    if county and county in COUNTY_OVERRIDES:
        feature = COUNTY_OVERRIDES[county](apn)
        source = f"county_override:{county}"
        if feature:
            return _feature_to_geometry(apn, feature, source)

    raise ValueError(
        "Attribute-based APN lookup against the statewide layer is known "
        "to time out (no index on PARCEL_APN). Use "
        "fetch_parcel_geometry_by_address(address, expected_apn=apn) "
        "instead."
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