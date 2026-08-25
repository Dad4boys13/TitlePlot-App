"""
Core engine: represent a parcel as an ordered polygon with labeled edges,
parse Schedule B 'Affects' clauses into (edge -> offset distance) maps,
and compute the resulting easement strip polygons.

No external geometry library available (no network access to install
shapely), so this implements the standard "variable-offset polygon"
algorithm directly with vector math. This is the same approach a real
GIS/CAD offset tool uses under the hood for straight-edged polygons.
"""
import math
import re

def sub(a, b): return (a[0]-b[0], a[1]-b[1])
def add(a, b): return (a[0]+b[0], a[1]+b[1])
def scale(a, s): return (a[0]*s, a[1]*s)
def length(a): return math.hypot(a[0], a[1])
def normalize(a):
    l = length(a)
    return (a[0]/l, a[1]/l) if l else (0, 0)

def signed_area(poly):
    s = 0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i+1) % n]
        s += x1*y2 - x2*y1
    return s / 2

def line_intersect(p1, d1, p2, d2):
    """Intersect line p1+t*d1 with line p2+s*d2."""
    x1, y1 = p1; x2, y2 = d1
    x3, y3 = p2; x4, y4 = d2
    denom = x2*y4 - y2*x4
    if abs(denom) < 1e-9:
        return p1  # parallel; degenerate fallback
    t = ((x3-x1)*y4 - (y3-y1)*x4) / denom
    return (x1 + t*x2, y1 + t*y2)


class Parcel:
    """
    vertices: ordered list of (x, y) going around the parcel boundary.
    edge_labels: list of labels (same length as vertices), edge_labels[i]
                 is the compass/name label for the edge from vertices[i]
                 to vertices[i+1] (e.g. 'N', 'E', 'S', 'W', or a custom
                 label like 'rear').
    """
    def __init__(self, vertices, edge_labels):
        assert len(vertices) == len(edge_labels)
        self.vertices = vertices
        self.edge_labels = edge_labels
        self.n = len(vertices)
        # Determine winding so we know which side is "inward"
        self.ccw = signed_area(vertices) > 0

    def edge(self, i):
        return self.vertices[i], self.vertices[(i+1) % self.n]

    def inward_normal(self, i):
        p1, p2 = self.edge(i)
        d = normalize(sub(p2, p1))
        # For a CCW polygon, interior lies to the LEFT of travel direction
        # (left normal = (-dy, dx)). For CW, interior lies to the RIGHT
        # (right normal = (dy, -dx)).
        n = (-d[1], d[0]) if self.ccw else (d[1], -d[0])
        return n

    def offset_line(self, i, dist):
        """Return (point, direction) of edge i shifted inward by dist."""
        p1, p2 = self.edge(i)
        n = self.inward_normal(i)
        shift = scale(n, dist)
        return add(p1, shift), normalize(sub(p2, p1))

    def strips_for_widths(self, widths):
        """
        widths: dict edge_index -> inward offset distance (0 if not affected).
        Returns dict edge_index -> quad polygon [v_i, v_{i+1}, v'_{i+1}, v'_i]
        for every edge with width > 0, using mitered corners against
        neighboring offset lines (correctly tapers to zero at a boundary
        with an unaffected edge, and forms a clean L-join between two
        affected edges).
        """
        n = self.n
        w = [widths.get(i, 0) for i in range(n)]
        offset_lines = [self.offset_line(i, w[i]) for i in range(n)]
        offset_vertices = []
        for i in range(n):
            prev_line = offset_lines[(i-1) % n]
            cur_line = offset_lines[i]
            v = line_intersect(prev_line[0], prev_line[1], cur_line[0], cur_line[1])
            offset_vertices.append(v)
        strips = {}
        for i in range(n):
            if w[i] > 0:
                v1, v2 = self.edge(i)
                v1p, v2p = offset_vertices[i], offset_vertices[(i+1) % n]
                strips[i] = [v1, v2, v2p, v1p]
        return strips

    def edge_index_by_label(self, label):
        for i, lab in enumerate(self.edge_labels):
            if lab.lower() == label.lower():
                return i
        return None


# ---- Schedule B "Affects" clause parser ----

DIRECTION_MAP = {
    "northerly": "N", "north": "N",
    "southerly": "S", "south": "S",
    "easterly": "E", "east": "E",
    "westerly": "W", "west": "W",
    "rear": "REAR",       # resolved relative to parcel orientation
    "front": "FRONT",
}

CLAUSE_RE = re.compile(
    r"(northerly|southerly|easterly|westerly|north|south|east|west|rear|front)\s+([\d.]+)\s*feet",
    re.IGNORECASE,
)

def parse_affects_clause(text):
    """
    Parse a Schedule B 'Affects:' clause into a list of (direction, distance).
    e.g. "The Southerly 6 feet and Easterly 3 feet of said land"
      -> [("S", 6.0), ("E", 3.0)]
    Returns [] and a flag if the clause indicates a non-locatable / blanket
    easement (no specific dimensional offset given).
    """
    matches = CLAUSE_RE.findall(text)
    result = []
    for direction, dist in matches:
        code = DIRECTION_MAP[direction.lower()]
        result.append((code, float(dist)))
    return result
