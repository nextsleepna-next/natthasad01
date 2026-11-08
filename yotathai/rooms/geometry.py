# SPDX-License-Identifier: GPL-3.0-or-later
"""Small plan geometry for room labels: polygons are lists of (x, y) metres.

Pure Python (Qt only for the polygon intersection), so labels can be read,
checked and drawn without the 3D engine being loaded.
"""
from __future__ import annotations

import math


def area_signed(poly) -> float:
    s = 0.0
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return s / 2.0


def area(poly) -> float:
    return abs(area_signed(poly))


def ccw(poly) -> list:
    """The polygon turning counter-clockwise (a copy)."""
    pts = [(float(x), float(y)) for x, y in poly]
    return pts if area_signed(pts) >= 0 else pts[::-1]


def centroid(poly) -> tuple:
    a = area_signed(poly)
    if abs(a) < 1e-12:
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        return sum(xs) / len(xs), sum(ys) / len(ys)
    cx = cy = 0.0
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        f = x0 * y1 - x1 * y0
        cx += (x0 + x1) * f
        cy += (y0 + y1) * f
    return cx / (6 * a), cy / (6 * a)


def bbox(poly) -> tuple:
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def contains(poly, pt, eps: float = 0.0) -> bool:
    """Point in polygon (ray casting); points on an edge count as inside."""
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if _on_segment((x, y), (x0, y0), (x1, y1), 1e-9 + eps):
            return True
        if (y0 > y) != (y1 > y):
            xin = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
            if xin > x:
                inside = not inside
    return inside


def _on_segment(p, a, b, tol) -> bool:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(p[0] - ax, p[1] - ay) <= tol
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy)) <= tol


def _ccw3(a, b, c) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _cross(a, b, c, d) -> bool:
    """Segments ab and cd cross properly (not just touch)."""
    d1, d2 = _ccw3(a, b, c), _ccw3(a, b, d)
    d3, d4 = _ccw3(c, d, a), _ccw3(c, d, b)
    return (d1 * d2 < -1e-12) and (d3 * d4 < -1e-12)


def is_simple(poly) -> bool:
    """No two non-adjacent edges cross."""
    n = len(poly)
    if n < 3:
        return False
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        for j in range(i + 1, n):
            if j == i or (j + 1) % n == i or (i + 1) % n == j:
                continue
            c, d = poly[j], poly[(j + 1) % n]
            if _cross(a, b, c, d):
                return False
    return True


def dedupe(poly, tol: float = 1e-9) -> list:
    out = []
    for p in poly:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > tol:
            out.append((float(p[0]), float(p[1])))
    if len(out) > 1 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) <= tol:
        out.pop()
    return out


def intersection_area(a, b) -> float:
    """Area shared by two polygons (Qt's polygon clipper)."""
    ax0, ay0, ax1, ay1 = bbox(a)
    bx0, by0, bx1, by1 = bbox(b)
    if ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0:
        return 0.0
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QPolygonF
    pa = QPolygonF([QPointF(x, y) for x, y in a])
    pb = QPolygonF([QPointF(x, y) for x, y in b])
    inter = pa.intersected(pb)
    pts = [(p.x(), p.y()) for p in inter]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    return area(pts) if len(pts) >= 3 else 0.0


def simplify_collinear(poly, tol: float = 1e-6) -> list:
    """Drop vertices that lie on the line between their neighbours."""
    pts = dedupe(poly)
    changed = True
    while changed and len(pts) > 3:
        changed = False
        n = len(pts)
        for i in range(n):
            a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
            if abs(_ccw3(a, b, c)) <= tol * max(1.0, math.hypot(c[0] - a[0], c[1] - a[1])):
                del pts[i]
                changed = True
                break
    return pts


def rect(x0, y0, x1, y1) -> list:
    x0, x1 = sorted((float(x0), float(x1)))
    y0, y1 = sorted((float(y0), float(y1)))
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def parse_rect(text: str) -> list:
    try:
        v = [float(t) for t in text.replace(" ", "").split(",")]
    except ValueError:
        v = []
    if len(v) != 4:
        raise ValueError("--rect ต้องเป็น x0,y0,x1,y1 (เมตร)")
    return rect(*v)


def parse_poly(text: str) -> list:
    pts = []
    for chunk in text.replace(" ", "").split(";"):
        if not chunk:
            continue
        try:
            x, y = (float(t) for t in chunk.split(","))
        except ValueError:
            raise ValueError("--poly ต้องเป็น x,y;x,y;x,y (เมตร)") from None
        pts.append((x, y))
    if len(pts) < 3:
        raise ValueError("--poly ต้องมีอย่างน้อย 3 จุด")
    return pts


def parse_point(text: str) -> tuple:
    try:
        x, y = (float(t) for t in text.replace(" ", "").split(","))
    except ValueError:
        raise ValueError("--at ต้องเป็น x,y (เมตร)") from None
    return x, y


def text_width(text: str, height: float, factor: float = 0.55) -> float:
    """Rough advance by character count: marks that take no room (upper and
    lower vowels, tone marks — Unicode category Mn) are not counted."""
    import unicodedata
    n = sum(1 for ch in text if unicodedata.category(ch) != "Mn")
    return n * height * factor


#: advance of a character as a share of the text height — only used when the
#: font cannot be read (the sheet is drawn in Tahoma; measured 0.60–0.80)
CHAR_EM = 0.72
_FONT = []


def measure(text: str, height: float, factor: float = CHAR_EM) -> float:
    """Width of ``text`` set at ``height`` in the sheet's own font, from the
    same glyph advances the PDF writer uses (ezdxf's TrueType reader on
    ``Tahoma.ttf``; where the machine has no Tahoma the substitute that the
    writer would take there). Falls back to a per-character estimate."""
    if not _FONT:
        try:
            from ezdxf.fonts import fonts
            _FONT.append(fonts.make_font("Tahoma.ttf", 1.0))
        except Exception:  # noqa: BLE001 — never stop a drawing for a font
            _FONT.append(None)
    f = _FONT[0]
    if f is not None:
        try:
            return float(f.text_width(text)) * height
        except Exception:  # noqa: BLE001
            pass
    return text_width(text, height, factor)
