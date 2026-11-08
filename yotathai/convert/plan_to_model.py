# SPDX-License-Identifier: GPL-3.0-or-later
"""2D -> 3D: raise a floor plan drawn in CAD into walls, openings, columns
and a floor slab.

``python -m yotathai.convert.plan_to_model plan.dxf model.igz
[--height 3.0] [--door-height 2.1] [--sill 0.9] [--head 2.1]
[--wall-layers A,B] [--door-layers ..] [--window-layers ..]
[--column-layers ..] [--glb out.glb] [--ifc out.ifc]``

What it reads, the way Thai drafters draw a plan:

* walls on layers named WALL / ผนัง / กำแพง… — either the usual two
  parallel lines per wall (the pair's distance is the thickness), or one
  centre line per wall (then ``--thickness``); decided per drawing;
* a gap between two pieces of the same wall is an opening: a door when a
  door-layer entity (leaf, swing arc) sits at it, a window when a
  window-layer entity (glazing lines) lies in it, else a plain opening
  (with the beam above it at door height);
* columns: closed outlines or circles on COL / เสา layers;
* the floor slab: the outline the walls enclose; the rooms inside it are
  reported with their areas (and names, from the text in them).

Units come from $INSUNITS (mm/cm/m…); a drawing without it is judged by its
size. Layers that are off or frozen are skipped. Everything goes into
groups on Thai layers (ผนัง ประตู หน้าต่าง เสา พื้น), tagged for IFC.
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

from yotathai.convert._common import run, save_model, use_3d_engine

ROLE_PATTERNS = {
    "wall": r"WALL|ผนัง|กำแพง|^A-WAL|MURO|\bMUR\b",
    "door": r"DOOR|ประตู|^A-DR\b|PUERTA",
    "window": r"WIN|GLAZ|หน้าต่าง|WDW|VENTANA",
    "column": r"COLUMN|(^|[-_ ])COLS?($|[-_ ])|เสา|PILLAR",
}
#: Layer names that carry those words but are not the thing itself.
ROLE_EXCLUDE = r"HATCH|PATT|FILL|DIM|TEXT|ANNO|TAG|IDEN|NOTE|ข้อความ|มิติ|ลาย"

INSUNITS_TO_M = {1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0, 14: 0.1}

COLORS = {
    "wall": (0.93, 0.91, 0.86), "slab": (0.72, 0.72, 0.70),
    "column": (0.80, 0.80, 0.78), "door": (0.55, 0.36, 0.20),
    "glass": (0.62, 0.80, 0.93),
}

# Geometry tolerances, metres.
T_MIN, T_MAX = 0.04, 0.60          # a wall's thickness
PARALLEL = 0.026                   # |sin| of 1.5°
MAX_OPENING = 3.6                  # wider gaps split the wall
MIN_PIECE = 0.05


def role_of(layer: str, overrides: dict) -> str | None:
    for role, names in overrides.items():
        if names is not None and layer in names:
            return role
    if re.search(ROLE_EXCLUDE, layer, re.IGNORECASE):
        return None
    for role, pattern in ROLE_PATTERNS.items():
        if overrides.get(role) is not None:
            continue                       # the user named this role's layers
        if re.search(pattern, layer, re.IGNORECASE):
            return role
    return None


# ---- reading the drawing ---------------------------------------------------------

def _flat_entities(doc, handles=None):
    """Model space with every block exploded; an entity on layer 0 inside a
    block takes the INSERT's layer (the CAD rule). Off/frozen layers out.
    ``handles``: only these top-level entities (the user's selection)."""
    hidden = {ly.dxf.name for ly in doc.layers if ly.is_off() or ly.is_frozen()}

    def walk(entities, parent_layer, depth):
        for e in entities:
            layer = e.dxf.get("layer", "0")
            if layer == "0" and parent_layer:
                layer = parent_layer
            if e.dxftype() == "INSERT":
                if depth > 8 or layer in hidden:
                    continue
                try:
                    yield from walk(e.virtual_entities(), layer, depth + 1)
                except Exception:          # noqa: BLE001 — a broken block is skipped
                    continue
            elif layer not in hidden:
                yield layer, e

    top = doc.modelspace()
    if handles:
        top = [e for e in top if e.dxf.handle in handles]
    yield from walk(top, "", 0)


def _unit_scale(doc, extent: float) -> float:
    code = int(doc.header.get("$INSUNITS", 0) or 0)
    if code in INSUNITS_TO_M:
        return INSUNITS_TO_M[code]
    # No units: a building is 3–100 m across. Judge by the walls' extent.
    if extent > 1500:
        return 0.001
    if extent > 150:
        return 0.01
    return 1.0


def _segments(entity, flat=0.02):
    """Straight pieces of a curve-like entity, in drawing units."""
    from ezdxf import path as ezpath
    try:
        p = ezpath.make_path(entity)
    except Exception:                      # noqa: BLE001 — not a curve
        return []
    pts = [(v.x, v.y) for v in p.flattening(distance=flat)]
    return [(a, b) for a, b in zip(pts, pts[1:])
            if (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 > 1e-12]


def _points(entity):
    """Characteristic points of a door/window entity (drawing units)."""
    kind = entity.dxftype()
    d = entity.dxf
    try:
        if kind == "LINE":
            return [(d.start.x, d.start.y), (d.end.x, d.end.y)]
        if kind == "ARC":
            c = d.center
            pts = [(c.x, c.y)]
            for ang in (d.start_angle, d.end_angle):
                a = math.radians(ang)
                pts.append((c.x + d.radius * math.cos(a), c.y + d.radius * math.sin(a)))
            return pts
        if kind == "CIRCLE":
            return [(d.center.x, d.center.y)]
    except Exception:                      # noqa: BLE001
        return []
    segs = _segments(entity, flat=0.05)
    return [s[0] for s in segs] + [s[1] for s in segs[-1:]]


def _closed_outlines(entity, flat=0.02):
    """Every column outline an entity holds: one for a closed polyline or
    circle, one per boundary loop for a HATCH (columns are often drawn as
    solid-filled squares)."""
    if entity.dxftype() == "HATCH":
        from ezdxf import path as ezpath
        out = []
        try:
            for p in ezpath.from_hatch(entity):
                pts = [(v.x, v.y) for v in p.flattening(distance=flat)]
                if len(pts) > 1 and pts[0] == pts[-1]:
                    pts.pop()
                if len(pts) >= 3:
                    out.append(pts)
        except Exception:                  # noqa: BLE001
            return []
        return out
    one = _closed_outline(entity, flat)
    return [one] if one else []


def _closed_outline(entity, flat=0.02):
    """A column's outline (drawing units), or None."""
    kind = entity.dxftype()
    if kind == "CIRCLE":
        c, r = entity.dxf.center, entity.dxf.radius
        return [(c.x + r * math.cos(2 * math.pi * i / 24),
                 c.y + r * math.sin(2 * math.pi * i / 24)) for i in range(24)]
    if kind in ("LWPOLYLINE", "POLYLINE") and entity.is_closed:
        segs = _segments(entity, flat)
        return [s[0] for s in segs] if len(segs) >= 3 else None
    return None


# ---- walls from lines ------------------------------------------------------------

def _subtract(intervals, a, b):
    """[a, b] minus a list of (lo, hi) intervals -> list of (lo, hi)."""
    out = [(a, b)]
    for lo, hi in intervals:
        nxt = []
        for x, y in out:
            if hi <= x or lo >= y:
                nxt.append((x, y))
                continue
            if lo > x:
                nxt.append((x, lo))
            if hi < y:
                nxt.append((hi, y))
        out = nxt
    return [(x, y) for x, y in out if y - x > MIN_PIECE]


def pair_walls(segs):
    """Double-line walls: pieces (p0, p1, thickness) on the centre line,
    plus the total length of lines that found a partner."""
    import numpy as np
    S = np.asarray(segs, dtype=float).reshape(-1, 4)
    if not len(S):
        return [], 0.0
    p0, p1 = S[:, 0:2].copy(), S[:, 2:4].copy()
    v = p1 - p0
    L = np.hypot(v[:, 0], v[:, 1])
    keep = L > 0.03
    p0, p1, v, L = p0[keep], p1[keep], v[keep], L[keep]
    u = v / L[:, None]
    flip = (u[:, 0] < -1e-9) | ((np.abs(u[:, 0]) <= 1e-9) & (u[:, 1] < 0))
    p0[flip], p1[flip] = p1[flip].copy(), p0[flip].copy()
    u[flip] *= -1
    n = np.stack([-u[:, 1], u[:, 0]], axis=1)
    N = len(L)

    cands = []
    for i in range(N - 1):
        j = np.arange(i + 1, N)
        cross = np.abs(u[i, 0] * u[j, 1] - u[i, 1] * u[j, 0])
        rel0 = p0[j] - p0[i]
        rel1 = p1[j] - p0[i]
        d0 = rel0 @ n[i]
        d1 = rel1 @ n[i]
        ok = (cross < PARALLEL) & (np.abs(d0 - d1) < 0.02)
        dist = (d0 + d1) / 2
        ok &= (np.abs(dist) >= T_MIN) & (np.abs(dist) <= T_MAX)
        t0 = rel0 @ u[i]
        t1 = rel1 @ u[i]
        lo = np.maximum(0.0, np.minimum(t0, t1))
        hi = np.minimum(L[i], np.maximum(t0, t1))
        ok &= (hi - lo) > 0.10
        for k in np.nonzero(ok)[0]:
            cands.append((abs(dist[k]), i, int(j[k]), float(lo[k]), float(hi[k]),
                          float(dist[k])))
    cands.sort()
    covered = [[] for _ in range(N)]
    pieces = []
    paired = np.zeros(N)
    for _ad, i, j, lo, hi, dist in cands:
        # j's covered intervals, in i's parameter
        mapped = []
        for a, b in covered[j]:
            ta = float((p0[j] + u[j] * a - p0[i]) @ u[i])
            tb = float((p0[j] + u[j] * b - p0[i]) @ u[i])
            mapped.append((min(ta, tb), max(ta, tb)))
        for a, b in _subtract(covered[i] + mapped, lo, hi):
            pa = p0[i] + u[i] * a + n[i] * dist / 2
            pb = p0[i] + u[i] * b + n[i] * dist / 2
            # Extend into a corner where one of the two lines carries on
            # (an L's outer line runs a thickness past the inner one).
            ja = float((p0[i] + u[i] * a - p0[j]) @ u[j])
            jb = float((p0[i] + u[i] * b - p0[j]) @ u[j])
            back = max(a, min(ja, jb))            # how far a line continues before a
            fwd = max(L[i] - b, L[j] - max(ja, jb))
            back = min(back, T_MAX, 1.5 * abs(dist))
            fwd = min(fwd, T_MAX, 1.5 * abs(dist))
            pa = pa - u[i] * max(back, 0.0)
            pb = pb + u[i] * max(fwd, 0.0)
            pieces.append((tuple(pa), tuple(pb), abs(dist)))
            covered[i].append((a, b))
            ja2, jb2 = sorted((ja, jb))
            covered[j].append((ja2, jb2))
            paired[i] += b - a
            paired[j] += b - a
    return pieces, float(np.minimum(paired, L).sum())


def merge_runs(pieces):
    """Collinear pieces of equal thickness -> runs, each a list of
    (s0, s1) intervals along one line: [(origin, u, n, t, [(s0, s1)...])]."""
    runs = []
    for a, b, t in pieces:
        ax, ay = a
        bx, by = b
        L = math.hypot(bx - ax, by - ay)
        if L < MIN_PIECE:
            continue
        ux, uy = (bx - ax) / L, (by - ay) / L
        if ux < -1e-9 or (abs(ux) <= 1e-9 and uy < 0):
            ux, uy, ax, ay, bx, by = -ux, -uy, bx, by, ax, ay
        nx, ny = -uy, ux
        for run in runs:
            (ox, oy), (rux, ruy), (rnx, rny), rt, items = run
            if abs(rux * uy - ruy * ux) > PARALLEL or abs(rt - t) > 0.03:
                continue
            if abs((ax - ox) * rnx + (ay - oy) * rny) > 0.03:
                continue
            s0 = (ax - ox) * rux + (ay - oy) * ruy
            s1 = (bx - ox) * rux + (by - oy) * ruy
            items.append((min(s0, s1), max(s0, s1)))
            break
        else:
            runs.append([(ax, ay), (ux, uy), (nx, ny), t, [(0.0, L)]])
    return runs


def _in_rect(pt, origin, u, n, s0, s1, half, pad):
    rx, ry = pt[0] - origin[0], pt[1] - origin[1]
    s = rx * u[0] + ry * u[1]
    d = rx * n[0] + ry * n[1]
    return (s0 - pad <= s <= s1 + pad) and abs(d) <= half + pad


def walls_with_openings(runs, doors, windows):
    """Each run -> walls [(a, b, t, [(offset, kind, width)])]: pieces closer
    than MAX_OPENING join across the gap, which becomes an opening."""
    walls = []
    for origin, u, n, t, items in runs:
        items.sort()
        merged = []
        for s0, s1 in items:
            if merged and s0 <= merged[-1][1] + 0.02:
                merged[-1][1] = max(merged[-1][1], s1)
            else:
                merged.append([s0, s1])
        groups = [[merged[0]]]
        for seg in merged[1:]:
            if seg[0] - groups[-1][-1][1] <= MAX_OPENING:
                groups[-1].append(seg)
            else:
                groups.append([seg])
        for g in groups:
            start, end = g[0][0], g[-1][1]
            openings = []
            for (_a0, a1), (b0, _b1) in zip(g, g[1:]):
                width = b0 - a1
                kind = "opening"
                if any(_in_rect(p, origin, u, n, a1 + 0.02, b0 - 0.02, t / 2, 0.01)
                       for p in windows):
                    kind = "window"
                elif any(_in_rect(p, origin, u, n, a1, b0, t / 2, 0.6 * t + 0.05)
                         for p in doors):
                    kind = "door"
                openings.append((a1 - start, kind, width))
            a = (origin[0] + u[0] * start, origin[1] + u[1] * start)
            b = (origin[0] + u[0] * end, origin[1] + u[1] * end)
            walls.append((a, b, t, openings))
    return walls


# ---- footprint and rooms ---------------------------------------------------------

def _rect(a, b, t):
    (ax, ay), (bx, by) = a, b
    L = math.hypot(bx - ax, by - ay)
    nx, ny = -(by - ay) / L * t / 2, (bx - ax) / L * t / 2
    return [(ax - nx, ay - ny), (bx - nx, by - ny), (bx + nx, by + ny), (ax + nx, ay + ny)]


def _area(poly):
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1)
                   in zip(poly, poly[1:] + poly[:1]))) / 2


def footprint_and_rooms(walls, columns):
    """Union of the walls (openings closed) -> outer outlines (the slab)
    and the enclosed holes (the rooms)."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QPainterPath, QPolygonF
    path = QPainterPath()
    path.setFillRule(Qt.WindingFill)
    for a, b, t, _ops in walls:
        if math.hypot(b[0] - a[0], b[1] - a[1]) < 1e-6:
            continue
        path.addPolygon(QPolygonF([QPointF(x, y) for x, y in _rect(a, b, t)]))
        path.closeSubpath()
    for outline in columns:
        path.addPolygon(QPolygonF([QPointF(x, y) for x, y in outline]))
        path.closeSubpath()
    rings = []
    for poly in path.simplified().toSubpathPolygons():
        pts = [(p.x(), p.y()) for p in poly]
        if len(pts) > 1 and pts[0] == pts[-1]:
            pts.pop()
        if len(pts) >= 3:
            rings.append(pts)

    def inside(ring, other):
        qp = QPolygonF([QPointF(x, y) for x, y in other])
        # a vertex of a hole may lie on the outer ring: test the centroid of
        # its first three vertices instead
        cx = sum(p[0] for p in ring[:3]) / 3
        cy = sum(p[1] for p in ring[:3]) / 3
        return qp.containsPoint(QPointF(cx, cy), Qt.OddEvenFill)
    outer, holes = [], []
    for i, r in enumerate(rings):
        if any(j != i and _area(o) > _area(r) and inside(r, o)
               for j, o in enumerate(rings)):
            holes.append(r)
        else:
            outer.append(r)
    return [r for r in outer if _area(r) > 0.5], [h for h in holes if _area(h) > 0.5]


# ---- the whole conversion ----------------------------------------------------------

def convert(dxf: Path, out: Path, height=3.0, door_height=2.1, sill=0.9,
            head=2.1, thickness=0.15, slab=0.10, layers=None, glb=None,
            ifc=None, handles=None) -> dict:
    import ezdxf
    from ezdxf import recover
    try:
        doc = ezdxf.readfile(dxf)
    except Exception:                      # noqa: BLE001 — real-world files
        doc, _auditor = recover.readfile(dxf)
    overrides = {r: (set(layers[r]) if layers and layers.get(r) else None)
                 for r in ROLE_PATTERNS}

    by_role = {r: [] for r in ROLE_PATTERNS}
    texts = []
    role_layers = {r: set() for r in ROLE_PATTERNS}
    for layer, e in _flat_entities(doc, handles):
        kind = e.dxftype()
        if kind in ("TEXT", "MTEXT"):
            try:
                txt = e.plain_text() if kind == "MTEXT" else e.dxf.text
                ins = e.dxf.insert
                texts.append((txt.strip(), (ins.x, ins.y)))
            except Exception:              # noqa: BLE001
                pass
            continue
        role = role_of(layer, overrides)
        if role is not None:
            by_role[role].append(e)
            role_layers[role].add(layer)
    if not by_role["wall"]:
        raise ValueError("no walls found — no layer named like WALL / ผนัง "
                         "(name the wall layers with --wall-layers)")

    raw = [s for e in by_role["wall"] for s in _segments(e, flat=1e6)]
    xs = [p[0] for s in raw for p in s]
    ys = [p[1] for s in raw for p in s]
    extent = max(max(xs) - min(xs), max(ys) - min(ys)) if raw else 0.0
    k = _unit_scale(doc, extent)
    # Re-flatten curves at a tolerance that means 1 cm in this drawing.
    raw = [s for e in by_role["wall"] for s in _segments(e, flat=0.01 / k)]
    segs = [((a[0] * k, a[1] * k), (b[0] * k, b[1] * k)) for a, b in raw]
    total_len = sum(math.dist(a, b) for a, b in segs)

    pieces, paired_len = pair_walls([(a[0], a[1], b[0], b[1]) for a, b in segs])
    mode = "double" if total_len and paired_len / total_len >= 0.4 else "single"
    if mode == "single":
        pieces = [(a, b, thickness) for a, b in segs if math.dist(a, b) >= 0.2]

    def scaled(points):
        return [(x * k, y * k) for x, y in points]
    door_pts = [p for e in by_role["door"] for p in scaled(_points(e))]
    window_pts = []
    for e in by_role["window"]:
        pts = scaled(_points(e))
        if pts:                     # the middle of each glazing element
            window_pts.append((sum(p[0] for p in pts) / len(pts),
                               sum(p[1] for p in pts) / len(pts)))
            window_pts.extend(pts)
    walls = walls_with_openings(merge_runs(pieces), door_pts, window_pts)
    columns = [scaled(o) for e in by_role["column"]
               for o in _closed_outlines(e, flat=0.01 / k)]
    outer, holes = footprint_and_rooms(walls, columns)

    # ---- build the model ----
    use_3d_engine()
    from PySide6.QtGui import QVector3D  # noqa: F401 — helpers need QtGui loaded
    from core import bim
    from core.ai import _recipe_helpers
    from core.layers import Layer
    from core.scene import Scene
    scene = Scene()
    h = _recipe_helpers(scene)
    have = {ly.name for ly in scene.layers}
    scene.layers += [Layer(n) for n in ("ผนัง", "ประตู", "หน้าต่าง", "เสา", "พื้น")
                     if n not in have]

    def tag(group, layer, ifc_class, name, info):
        group.layer = layer
        bim.tag_group(group, ifc_class, name)
        group.ext = {"yotathai": {"source": Path(dxf).name, **info}}

    counts = {"door": 0, "window": 0, "opening": 0}
    wall_len = 0.0
    for wi, (a, b, t, ops) in enumerate(walls, 1):
        L = math.dist(a, b)
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        nx, ny = -uy, ux
        base_a = (a[0] - nx * t / 2, a[1] - ny * t / 2)
        base_b = (b[0] - nx * t / 2, b[1] - ny * t / 2)
        holes_spec = []
        for off, kind, width in ops:
            counts[kind] += 1
            if kind == "window":
                holes_spec.append((off, sill, width, max(head - sill, 0.1)))
            else:
                holes_spec.append((off, 0.0, width, door_height))
        g = h["wall"](base_a, base_b, height=height, thickness=t,
                      openings=holes_spec, name=f"ผนัง {wi}", color=COLORS["wall"])
        tag(g, "ผนัง", "IfcWall", f"ผนัง {wi}",
            {"kind": "wall", "thickness_m": round(t, 3), "length_m": round(L, 3)})
        wall_len += L
        for off, kind, width in ops:
            c0 = (a[0] + ux * off, a[1] + uy * off)
            c1 = (a[0] + ux * (off + width), a[1] + uy * (off + width))
            if kind == "window":
                pane = 0.02
                z0, z1 = sill, head
                color, layer, ifc_class, label = COLORS["glass"], "หน้าต่าง", "IfcWindow", "หน้าต่าง"
            elif kind == "door":
                pane = min(0.04, t * 0.6)
                z0, z1 = 0.0, door_height
                color, layer, ifc_class, label = COLORS["door"], "ประตู", "IfcDoor", "ประตู"
            else:
                continue
            quad = [(c0[0] - nx * pane / 2, c0[1] - ny * pane / 2),
                    (c1[0] - nx * pane / 2, c1[1] - ny * pane / 2),
                    (c1[0] + nx * pane / 2, c1[1] + ny * pane / 2),
                    (c0[0] + nx * pane / 2, c0[1] + ny * pane / 2)]
            n_kind = counts[kind]
            g = h["extrude"](quad, z0, z1, name=f"{label} {n_kind}", color=color)
            tag(g, layer, ifc_class, f"{label} {n_kind}",
                {"kind": kind, "width_m": round(width, 3),
                 "height_m": round(z1 - z0, 3), "sill_m": round(z0, 3)})
    for ci, outline in enumerate(columns, 1):
        g = h["extrude"](outline, 0.0, height, name=f"เสา {ci}", color=COLORS["column"])
        tag(g, "เสา", "IfcColumn", f"เสา {ci}", {"kind": "column"})
    slab_area = 0.0
    for si, ring in enumerate(outer, 1):
        g = h["extrude"](ring, -slab, 0.0, name=f"พื้น {si}", color=COLORS["slab"])
        tag(g, "พื้น", "IfcSlab", f"พื้น {si}", {"kind": "slab"})
        slab_area += _area(ring)

    rooms = []
    if holes:
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QPolygonF
        for ring in holes:
            qp = QPolygonF([QPointF(x, y) for x, y in ring])
            names = [t for t, (x, y) in texts
                     if t and qp.containsPoint(QPointF(x * k, y * k), Qt.OddEvenFill)
                     and "ตร.ม" not in t and not re.fullmatch(r"[\d.,\s]+", t)]
            rooms.append({"name": names[0] if names else "",
                          "area_m2": round(_area(ring), 2)})
        rooms.sort(key=lambda r: -r["area_m2"])

    save_model(scene, out, glb)
    report = {
        "model": str(out), "mode": mode, "unit_to_m": k,
        "layers": {r: sorted(v) for r, v in role_layers.items() if v},
        "walls": len(walls), "wall_length_m": round(wall_len, 2),
        "doors": counts["door"], "windows": counts["window"],
        "openings": counts["opening"], "columns": len(columns),
        "slab_area_m2": round(slab_area, 2), "rooms": rooms,
        "height_m": height,
        "unpaired_m": round(total_len - paired_len, 2) if mode == "double" else 0.0,
    }
    if ifc is not None:
        from formats.ifc import save_ifc
        report["ifc_elements"] = save_ifc(scene, Path(ifc),
                                          project_name=f"Yotathai - {Path(dxf).stem}")
        report["ifc"] = str(ifc)
    return report


def main(argv) -> dict:
    ap = argparse.ArgumentParser(description="2D floor plan (DXF) -> 3D model (.igz)")
    ap.add_argument("plan", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--height", type=float, default=3.0, help="wall height, m")
    ap.add_argument("--door-height", type=float, default=2.1)
    ap.add_argument("--sill", type=float, default=0.9, help="window sill, m")
    ap.add_argument("--head", type=float, default=2.1, help="window head, m")
    ap.add_argument("--thickness", type=float, default=0.15,
                    help="wall thickness when walls are single centre lines")
    ap.add_argument("--slab", type=float, default=0.10, help="slab thickness, m")
    for role in ROLE_PATTERNS:
        ap.add_argument(f"--{role}-layers", default=None,
                        help=f"comma-separated layer names for {role}s")
    ap.add_argument("--handles", type=Path, default=None,
                    help="text file of entity handles: only those (a selection)")
    ap.add_argument("--glb", type=Path, default=None)
    ap.add_argument("--ifc", type=Path, default=None)
    a = ap.parse_args(argv)
    layers = {r: [x for x in getattr(a, f"{r}_layers").split(",") if x]
              for r in ROLE_PATTERNS if getattr(a, f"{r}_layers")}
    if a.plan.suffix.lower() == ".dwg":
        raise ValueError("open the DWG in Yotathai CAD first, or save it as DXF")
    handles = None
    if a.handles is not None:
        handles = set(a.handles.read_text(encoding="utf-8").split())
    return convert(a.plan, a.out, a.height, a.door_height, a.sill, a.head,
                   a.thickness, a.slab, layers, a.glb, a.ifc, handles)


if __name__ == "__main__":
    sys.exit(run(main))
