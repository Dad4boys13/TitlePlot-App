from typing import List
from .geometry import Parcel, DIRECTION_MAP
from .models import ParcelGeometry, ScheduleBItem

PALETTE = [
    {"stroke": "#2e7d32", "pattern_lines": "diag", "hex": "#2e7d32"},
    {"stroke": "#c62828", "pattern_lines": "diag_r", "hex": "#c62828"},
    {"stroke": "#1565c0", "pattern_lines": "dots", "hex": "#1565c0"},
    {"stroke": "#ef6c00", "pattern_lines": "diag2", "hex": "#ef6c00"},
    {"stroke": "#6a1b9a", "pattern_lines": "diag3", "hex": "#6a1b9a"},
    {"stroke": "#00838f", "pattern_lines": "dots2", "hex": "#00838f"},
]

REAR_OPPOSITE = {"N": "S", "S": "N", "E": "W", "W": "E"}


def _pattern_defs():
    return '''
  <pattern id="diag" patternUnits="userSpaceOnUse" width="8" height="8" patternTransform="rotate(45)">
    <rect width="8" height="8" fill="white"/><line x1="0" y1="0" x2="0" y2="8" stroke="#2e7d32" stroke-width="2"/>
  </pattern>
  <pattern id="diag_r" patternUnits="userSpaceOnUse" width="8" height="8" patternTransform="rotate(-45)">
    <rect width="8" height="8" fill="white"/><line x1="0" y1="0" x2="0" y2="8" stroke="#c62828" stroke-width="2"/>
  </pattern>
  <pattern id="dots" patternUnits="userSpaceOnUse" width="10" height="10">
    <rect width="10" height="10" fill="white"/><circle cx="2" cy="2" r="1.4" fill="#1565c0"/>
  </pattern>
  <pattern id="diag2" patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)">
    <rect width="6" height="6" fill="white"/><line x1="0" y1="0" x2="0" y2="6" stroke="#ef6c00" stroke-width="1.5"/>
  </pattern>
  <pattern id="diag3" patternUnits="userSpaceOnUse" width="7" height="7" patternTransform="rotate(20)">
    <rect width="7" height="7" fill="white"/><line x1="0" y1="0" x2="0" y2="7" stroke="#6a1b9a" stroke-width="1.5"/>
  </pattern>
  <pattern id="dots2" patternUnits="userSpaceOnUse" width="9" height="9">
    <rect width="9" height="9" fill="white"/><circle cx="2" cy="2" r="1.2" fill="#00838f"/>
  </pattern>
'''


def render_plat_svg(geometry: ParcelGeometry, items: List[ScheduleBItem], front_compass: str = "N") -> str:
    parcel = Parcel(geometry.vertices, geometry.edge_labels)

    scale = 4.5
    margin = 60
    xs = [p[0] for p in parcel.vertices]
    ys = [p[1] for p in parcel.vertices]
    maxy = max(ys)
    minx = min(xs)

    def to_svg(pt):
        x, y = pt
        return (margin + (x - minx) * scale, margin + (maxy - y) * scale)

    def poly_points(pts):
        return " ".join(f"{p[0]:.1f},{p[1]:.1f}" for p in pts)

    parts = [f'<svg viewBox="0 0 620 700" xmlns="http://www.w3.org/2000/svg" '
             f'font-family="Helvetica, Arial, sans-serif"><defs>{_pattern_defs()}</defs>'
             f'<rect width="620" height="700" fill="white"/>']

    svg_pts = [to_svg(v) for v in parcel.vertices]
    parts.append(f'<polygon points="{poly_points(svg_pts)}" fill="#fff3b0" stroke="black" stroke-width="2"/>')

    for i in range(parcel.n):
        v1, v2 = parcel.edge(i)
        dist = ((v2[0] - v1[0]) ** 2 + (v2[1] - v1[1]) ** 2) ** 0.5
        (x1, y1), (x2, y2) = to_svg(v1), to_svg(v2)
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        dx, dy = x2 - x1, y2 - y1
        ln = (dx ** 2 + dy ** 2) ** 0.5 or 1
        nx, ny = -dy / ln, dx / ln
        lx, ly = mx + nx * 14, my + ny * 14
        parts.append(f'<text x="{lx:.1f}" y="{ly:.1f}" font-size="12" fill="#333" '
                     f'text-anchor="middle">{dist:.2f}\'</text>')

    legend_entries = []
    color_i = 0
    for item in items:
        n = item.item_no
        if not item.plottable:
            legend_entries.append((n, item, None))
            continue

        clauses = _parse_clauses(item.affects_text, front_compass)
        widths = {}
        for compass, dist in clauses:
            idx = parcel.edge_index_by_label(compass)
            if idx is not None:
                widths[idx] = dist
        if not widths:
            legend_entries.append((n, item, None))
            continue

        style = PALETTE[color_i % len(PALETTE)]
        color_i += 1
        strips = parcel.strips_for_widths(widths)
        for edge_idx, quad in strips.items():
            pts = [to_svg(v) for v in quad]
            parts.append(f'<polygon points="{poly_points(pts)}" fill="url(#{style["pattern_lines"]})" '
                         f'stroke="{style["hex"]}" stroke-width="1.5" opacity="0.9"/>')
        legend_entries.append((n, item, style))

    parts.append('<g transform="translate(560,50)"><line x1="0" y1="30" x2="0" y2="0" stroke="black" '
                 'stroke-width="2"/><polygon points="0,-8 6,6 -6,6" fill="black"/>'
                 '<text x="0" y="46" font-size="14" text-anchor="middle">N</text></g>')

    ly = 500
    parts.append(f'<text x="30" y="{ly}" font-size="15" font-weight="bold">LEGEND</text>')
    ly += 14
    parts.append(f'<rect x="30" y="{ly}" width="18" height="14" fill="#fff3b0" stroke="black"/>'
                 f'<text x="55" y="{ly+11}" font-size="12">Fee, APN {geometry.apn}</text>')
    ly += 22
    for n, item, style in legend_entries:
        if style:
            swatch = f'<rect x="30" y="{ly}" width="18" height="14" fill="url(#{style["pattern_lines"]})" stroke="{style["hex"]}"/>'
            note = ""
        else:
            swatch = f'<rect x="30" y="{ly}" width="18" height="14" fill="white" stroke="#999" stroke-dasharray="2,2"/>'
            note = f" (not plotted{': ' + item.non_plottable_reason if item.non_plottable_reason else ''})"
        parts.append(swatch)
        parts.append(f'<text x="55" y="{ly+11}" font-size="11">Item {n} - {item.exception_type}{note}</text>')
        parts.append(f'<text x="55" y="{ly+24}" font-size="10" fill="#555">{item.affects_text[:90]}</text>')
        ly += 36

    if geometry.confidence_notes:
        parts.append(f'<text x="30" y="{ly+10}" font-size="10" fill="#c62828">{geometry.confidence_notes[:110]}</text>')

    parts.append("</svg>")
    return "\n".join(parts)


def _parse_clauses(affects_text: str, front_compass: str):
    from .geometry import parse_affects_clause
    clauses = parse_affects_clause(affects_text)
    resolved = []
    rear_compass = REAR_OPPOSITE[front_compass]
    for code, dist in clauses:
        if code == "FRONT":
            code = front_compass
        elif code == "REAR":
            code = rear_compass
        resolved.append((code, dist))
    return resolved
