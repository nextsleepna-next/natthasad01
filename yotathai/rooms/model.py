# SPDX-License-Identifier: GPL-3.0-or-later
"""What the model itself says about a floor: the walls cut by a plan section.

Used by ``room-check`` (do the labels still sit on the walls?) and by
``room-suggest`` / ``room-add --at`` (which enclosed spaces do the walls make?).
Nothing here writes to the model.
"""
from __future__ import annotations

import math
from pathlib import Path

from . import geometry as geo

#: a door/window box thinner than this is widened to span a wall (m)
THIN = 0.30
SPAN = 0.04
MIN_ROOM_M2 = 0.5
EPS = 0.003


def load_scene(path: Path):
    from yotathai.convert._common import use_3d_engine
    use_3d_engine()
    from core.scene import Scene
    from formats.igz import load_into
    scene = Scene()
    load_into(scene, Path(path))
    return scene


def level_cut(level: dict) -> float:
    """The z of the plan cut used for a level: 1.20 m above its floor, kept
    inside the level."""
    z0, z1 = float(level["z0"]), float(level["z1"])
    return min(z0 + 1.20, (z0 + z1) / 2.0) if z1 - z0 < 1.4 else z0 + 1.20


def _group_boxes(scene, classes, cut_z):
    """XY boxes (x0, y0, x1, y1) of the groups of IFC ``classes`` that the
    plane z = cut_z passes through (doors and windows in a cut wall)."""
    import numpy as np
    from core.group import world_mesh
    out = []
    for g in scene.groups:
        if (getattr(g, "ifc", None) or {}).get("class") not in classes:
            continue
        wm = world_mesh(g)
        verts = wm.vertices.values() if isinstance(wm.vertices, dict) else wm.vertices
        pts = np.array([[v.position.x(), v.position.y(), v.position.z()] for v in verts])
        if not len(pts):
            continue
        lo, hi = pts.min(0), pts.max(0)
        if lo[2] - 1e-6 <= cut_z <= hi[2] + 1e-6:
            out.append((float(lo[0]), float(lo[1]), float(hi[0]), float(hi[1])))
    return out


def cut_loops(scene, cut_z: float, geometry=None):
    """The section loops of the model at ``cut_z`` — the same loops the plan
    sheet fills grey. World xy (the plan view is the identity on xy)."""
    from core.hlr import collect_geometry

    from yotathai.convert import views_to_dxf as v2d
    if geometry is None:
        tris, hard, soft = collect_geometry(scene)
        geometry = (tris, hard, soft, None)
    d = v2d._drawing(scene, "top", geometry, cut_z=cut_z)
    return [[(float(p[0]), float(p[1])) for p in loop] for loop in (d.loops or []) if len(loop) >= 3]


class FloorWalls:
    """Walls of one floor at one cut: loops, door/window boxes, and the
    rings of their union (outer boundaries and the enclosed spaces).

    ``doors`` = "closed" (default) bars every door and window opening with a
    thin strip, so a space counts as enclosed when its doors are shut;
    "open" takes the door leaves away too, so doorways are real openings."""

    def __init__(self, loops, doors, windows, doors_mode: str = "closed"):
        self.loops = loops
        self.doors, self.windows = doors, windows
        self.mode = doors_mode
        keep = loops
        bars = list(windows) + list(doors)
        if doors_mode == "open":
            # inside doors are open; a door on the outer face of the building
            # stays shut (an open front door would make the whole house leak)
            outers = [r for r, d in _union_rings([geo.ccw(lp) for lp in loops]) if d % 2 == 0]
            inside = [b for b in doors if not _on_rings(b, outers)]
            keep = [lp for lp in loops if not _inside_any(lp, inside)]
            bars = list(windows) + [b for b in doors if b not in inside]
        self.solids = [geo.ccw(lp) for lp in keep]
        for x0, y0, x1, y1 in bars:
            if x1 - x0 < THIN:
                c = (x0 + x1) / 2
                x0, x1 = c - SPAN / 2, c + SPAN / 2
            if y1 - y0 < THIN:
                c = (y0 + y1) / 2
                y0, y1 = c - SPAN / 2, c + SPAN / 2
            # a hair larger: a box whose edge lies exactly on a wall's edge
            # makes Qt's polygon union drop the whole building
            self.solids.append(geo.rect(x0 - EPS, y0 - EPS, x1 + EPS, y1 + EPS))
        self.rings = _union_rings(self.solids)           # [(ring, depth)]
        self._envelope = None

    def outers(self):
        return [r for r, depth in self.rings if depth % 2 == 0]

    def spaces(self):
        """Enclosed spaces (rings at odd depth), largest first, no slivers."""
        sp = [geo.simplify_collinear(r) for r, depth in self.rings if depth % 2 == 1]
        sp = [r for r in sp if len(r) >= 3 and geo.area(r) >= MIN_ROOM_M2]
        return sorted(sp, key=geo.area, reverse=True)

    def envelope_area(self) -> float:
        """Area inside the outer face of the cut walls (walls and doors as
        they are cut, nothing added)."""
        if self._envelope is None:
            rings = _union_rings([geo.ccw(lp) for lp in self.loops])
            self._envelope = sum(geo.area(r) for r, depth in rings if depth % 2 == 0)
        return self._envelope


def _union_rings(polys):
    """Union of CCW polygons -> every boundary ring with its nesting depth."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QPainterPath, QPolygonF
    path = QPainterPath()
    path.setFillRule(Qt.WindingFill)
    for p in polys:
        path.addPolygon(QPolygonF([QPointF(x, y) for x, y in p]))
        path.closeSubpath()
    rings = []
    for poly in path.simplified().toSubpathPolygons():
        pts = [(q.x(), q.y()) for q in poly]
        if len(pts) > 1 and pts[0] == pts[-1]:
            pts.pop()
        pts = geo.dedupe(pts)
        if len(pts) >= 3 and geo.area(pts) > 1e-6:
            rings.append(pts)
    out = []
    for i, r in enumerate(rings):
        probe = _inside_probe(r)
        depth = sum(1 for j, o in enumerate(rings)
                    if j != i and geo.area(o) > geo.area(r) and geo.contains(o, probe))
        out.append((r, depth))
    return out


def _inside_probe(ring):
    """A point strictly inside ``ring`` (centroid, else a vertex nudged in)."""
    c = geo.centroid(ring)
    if geo.contains(ring, c):
        return c
    for i in range(len(ring)):
        a, b, d = ring[i - 1], ring[i], ring[(i + 1) % len(ring)]
        mx, my = (a[0] + d[0]) / 2, (a[1] + d[1]) / 2
        q = ((b[0] + mx) / 2, (b[1] + my) / 2)
        if geo.contains(ring, q):
            return q
    return ring[0]


def _on_rings(box, rings, tol: float = 0.25) -> bool:
    """The centre of ``box`` lies within ``tol`` of one of the rings."""
    c = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
    for ring in rings:
        for i in range(len(ring)):
            if geo._on_segment(c, ring[i - 1], ring[i], tol):
                return True
    return False


def _inside_any(loop, boxes, tol: float = 0.02) -> bool:
    x0, y0, x1, y1 = geo.bbox(loop)
    return any(x0 >= bx0 - tol and y0 >= by0 - tol and x1 <= bx1 + tol and y1 <= by1 + tol
               for bx0, by0, bx1, by1 in boxes)


def floor_walls(scene, level: dict, doors: str = "closed", geometry=None):
    cut = level_cut(level)
    loops = cut_loops(scene, cut, geometry)
    return FloorWalls(loops, _group_boxes(scene, ("IfcDoor",), cut),
                      _group_boxes(scene, ("IfcWindow",), cut), doors), cut


# --- leaks ---------------------------------------------------------------------

def find_leak(fw: FloorWalls, point, step: float = 0.05, reach: float = 6.0):
    """Where a space around ``point`` leaks out of the building: rasterise
    the walls, flood from the point, and if the flood escapes to the edge of
    the picture, return the narrowest place on the way out as
    ``{"at": (x, y), "width": metres}``. ``None`` if it does not escape."""
    import numpy as np
    from PySide6.QtGui import QColor, QImage, QPainter, QPolygonF
    from PySide6.QtCore import QPointF
    xs = [p[0] for s in fw.solids for p in s] + [point[0]]
    ys = [p[1] for s in fw.solids for p in s] + [point[1]]
    pad = 1.0
    x0, y0 = min(xs) - pad, min(ys) - pad
    W = int(math.ceil((max(xs) + pad - x0) / step))
    H = int(math.ceil((max(ys) + pad - y0) / step))
    img = QImage(W, H, QImage.Format_Grayscale8)
    img.fill(QColor(0, 0, 0))
    qp = QPainter(img)
    qp.setPen(QColor(255, 255, 255))
    qp.setBrush(QColor(255, 255, 255))
    for s in fw.solids:
        qp.drawPolygon(QPolygonF([QPointF((x - x0) / step, (y - y0) / step) for x, y in s]))
    qp.end()
    ptr = img.constBits()
    arr = np.frombuffer(ptr, dtype=np.uint8, count=img.bytesPerLine() * H).reshape(H, img.bytesPerLine())[:, :W]
    wall = arr > 127
    sx, sy = int((point[0] - x0) / step), int((point[1] - y0) / step)
    if not (0 <= sx < W and 0 <= sy < H) or wall[sy, sx]:
        return None
    from collections import deque
    parent = {(sx, sy): None}
    dq = deque([(sx, sy)])
    exit_cell = None
    while dq:
        cx, cy = dq.popleft()
        if cx in (0, W - 1) or cy in (0, H - 1):
            exit_cell = (cx, cy)
            break
        for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
            if (nx, ny) not in parent and not wall[ny, nx]:
                parent[(nx, ny)] = (cx, cy)
                dq.append((nx, ny))
    if exit_cell is None:
        return None
    path = []
    c = exit_cell
    while c is not None:
        path.append(c)
        c = parent[c]
    r = int(reach / step)
    best = None
    for cx, cy in path:
        xa, xb = max(0, cx - r), min(W, cx + r + 1)
        ya, yb = max(0, cy - r), min(H, cy + r + 1)
        ww = np.argwhere(wall[ya:yb, xa:xb])
        if not len(ww):
            continue
        d = np.hypot(ww[:, 1] + xa - cx, ww[:, 0] + ya - cy).min() * step
        if best is None or d < best[0]:
            best = (d, cx, cy)
    if best is None:
        return {"at": (point[0], point[1]), "width": None}
    d, cx, cy = best
    return {"at": (round(x0 + (cx + 0.5) * step, 2), round(y0 + (cy + 0.5) * step, 2)),
            "width": round(2 * d, 2)}
