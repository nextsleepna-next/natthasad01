# SPDX-License-Identifier: GPL-3.0-or-later
"""Drawing room colours on a model-to-2d sheet (ezdxf).

Layers (created only when a sheet really gets room colours):

* ``Y-ROOM-FILL`` — one flat SOLID hatch per room, true-colour, added BEFORE
  the section lines and grey wall fill of its plan, so the walls lie on top;
* ``Y-ROOM-LINE`` — a hairline round each room (it shows where two rooms meet
  with no wall between them; under walls it is hidden);
* ``Y-ROOM-TEXT`` — name and area of each room, and the words of the legend, in
  the sheet's own Thai text style (``TH``, Tahoma — named, never copied);
* ``Y-ROOM-KEY`` — the frame of the legend and its colour chips (which stand
  just right of the plans).

A thin line (a beam above the cut, a grid line) that runs through a label is
cut away under the letters when the sheet is drawn (:func:`clip_thin`); the
stubs that would be left beside the label are dropped. Section lines and walls
are never touched: a label is always set clear of them.
"""
from __future__ import annotations

import numpy as np

from . import geometry as geo
from . import kinds

FILL_LAYER = "Y-ROOM-FILL"
LINE_LAYER = "Y-ROOM-LINE"
KEY_LAYER = "Y-ROOM-KEY"
TEXT_LAYER = "Y-ROOM-TEXT"
#: how a mode is named on the sheet (the same words everywhere)
MODE_TH = {"presentation": "ชุดนำเสนอ", "construction": "ชุดก่อสร้าง"}
#: a label is never set smaller than this share of the sheet's label height
#: unless nothing else fits (then it is reported)
STANDARD_MIN = 0.85
LINE_PITCH = 1.5            # distance between the lines of a label, in text heights
CLEAR = 0.10                # clear space kept round a label (m)
TIGHT = 0.05                # the least clear space, tried before a label is made smaller
#: share of its advance that a line of text really inks (a legend frame is cut to the advance)
INK = 0.995
#: a piece of a thin line left beside a label shorter than this is dropped (m) —
#: about 4 mm on the paper at 1:75
STUB = 0.30
#: space under the last legend row, in text heights (the title has 1.0 above it)
BOTTOM_GAP = 0.85


def ensure_layers(doc) -> None:
    for name, color, lw in ((FILL_LAYER, 8, 0), (LINE_LAYER, 8, 9), (KEY_LAYER, 7, 25), (TEXT_LAYER, 7, 25)):
        if name not in doc.layers:
            layer = doc.layers.add(name, color=color)
            if lw:
                layer.dxf.lineweight = lw


def _rgb255(rgb):
    return tuple(int(round(c * 255)) for c in rgb)


def _hatch(msp, layer, rgb, path, aci=None):
    """A flat SOLID hatch in true colour; its AutoCAD colour index (``aci``,
    else the nearest standard colour) serves viewers that do not read true colour."""
    h = msp.add_hatch(color=aci if aci else kinds.nearest_aci(rgb), dxfattribs={"layer": layer})
    h.rgb = _rgb255(rgb)
    h.paths.add_polyline_path(path, is_closed=True)
    return h


def add_fills(msp, fills, dx: float, dy: float) -> int:
    """One SOLID hatch and one hairline outline per room."""
    for f in fills:
        pts = [(x + dx, y + dy) for x, y in f["poly"]]
        _hatch(msp, FILL_LAYER, f["rgb"], pts, f.get("aci"))
        msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": LINE_LAYER})
    return len(fills)


def _obstacle_points(segs, box, step: float = 0.04):
    """Points along the plan's lines that fall inside ``box``."""
    x0, y0, x1, y1 = box
    pts = []
    for sx, sy, ex, ey in np.asarray(segs, dtype=float).reshape(-1, 4):
        if max(sx, ex) < x0 or min(sx, ex) > x1 or max(sy, ey) < y0 or min(sy, ey) > y1:
            continue
        n = max(1, int(np.hypot(ex - sx, ey - sy) / step))
        t = np.linspace(0.0, 1.0, n + 1)
        pts.append(np.column_stack((sx + (ex - sx) * t, sy + (ey - sy) * t)))
    if not pts:
        return np.empty((0, 2))
    p = np.vstack(pts)
    return p[(p[:, 0] >= x0) & (p[:, 0] <= x1) & (p[:, 1] >= y0) & (p[:, 1] <= y1)]


def _wrap(name: str):
    """The name broken in two at a space, hyphen or slash, as evenly as it can
    be — or None if it has no place to break."""
    best = None
    for i, ch in enumerate(name):
        if ch in " -/" and 0 < i < len(name) - 1:
            a = name[:i + 1].rstrip() if ch == " " else name[:i + 1]
            b = name[i + 1:].lstrip()
            if a and b:
                score = abs(geo.measure(a, 1.0) - geo.measure(b, 1.0))
                if best is None or score < best[0]:
                    best = (score, [a, b])
    return best[1] if best else None


def _variants(name: str, area_txt: str):
    out = [[name, area_txt]]
    w = _wrap(name)
    if w:
        out.append([*w, area_txt])
    return out


def _box(lines, hh, pad):
    """(width, height) of the text box of ``lines`` set at ``hh`` (the last
    line, the area, is set at 0.9)."""
    w = max(geo.measure(t, hh * (0.9 if i == len(lines) - 1 else 1.0))
            for i, t in enumerate(lines)) + 2 * pad
    return w, LINE_PITCH * hh * len(lines) + 2 * pad


def place_label(poly, name: str, area_txt: str, h: float, segs, taken=(), heavy=None):
    """Where to put the label of a room (its name over its area).

    The text box lies inside the room's outline and clear of every heavy
    (section / profile) line. In order of preference:

    1. standard height, clear of ALL lines, close to the middle of the room;
    2. standard height, the middle of the room, clear of the heavy lines only
       (thin lines under the label are cut away when the sheet is drawn);
    3. the same at 0.85 of the standard height;
    4. smaller (0.7, 0.6, 0.5) — last resorts the caller reports.

    At each step a long name is first tried on one line, then broken in two.
    A tall narrow room takes the label turned 90 degrees (reading from the
    bottom up) only where it cannot lie flat. The place found is then moved
    to the middle of the clear space between what bounds it on either side.
    -> dict(x, y, h, lines, rot, w, hgt, masked, scale) — w, hgt are the box
    as it lies on the plan."""
    bx0, by0, bx1, by1 = geo.bbox(poly)
    cx, cy = geo.centroid(poly)
    if not geo.contains(poly, (cx, cy)):
        cx, cy = poly[0]
    margin = CLEAR + 0.05
    box = (bx0 - margin, by0 - margin, bx1 + margin, by1 + margin)
    obst_all = _obstacle_points(segs, box)
    obst_heavy = _obstacle_points(heavy if heavy is not None else segs, box)
    step = max(0.05, min(0.12, min(bx1 - bx0, by1 - by0) / 25))
    xs = np.arange(bx0, bx1 + step / 2, step)
    ys = np.arange(by0, by1 + step / 2, step)
    tall = (by1 - by0) > 2.2 * (bx1 - bx0)
    near = 0.1 * max(bx1 - bx0, by1 - by0) + 0.25

    def ok(x, y, w, ht, obst, clear=CLEAR):
        corners = [(x - w / 2, y - ht / 2), (x + w / 2, y - ht / 2), (x + w / 2, y + ht / 2),
                   (x - w / 2, y + ht / 2), (x, y - ht / 2), (x, y + ht / 2),
                   (x - w / 2, y), (x + w / 2, y), (x, y)]
        if not all(geo.contains(poly, c) for c in corners):
            return False
        if len(obst) and np.any((np.abs(obst[:, 0] - x) <= w / 2 + clear)
                                & (np.abs(obst[:, 1] - y) <= ht / 2 + clear)):
            return False
        return not any(abs(x - tx) < (w + tw) / 2 and abs(y - ty) < (ht + th) / 2 for tx, ty, tw, th in taken)

    def search(lines, hh, obst, max_dist, rot, clear=CLEAR):
        w0, h0 = _box(lines, hh, 0.04)
        w, ht = (w0, h0) if rot == 0 else (h0, w0)
        best = None
        for y in ys:
            for x in xs:
                d2 = (x - cx) ** 2 + (y - cy) ** 2
                if best is not None and d2 >= best[0]:
                    continue
                if max_dist is not None and d2 > max_dist ** 2:
                    continue
                if ok(x, y, w, ht, obst, clear):
                    best = (d2, x, y, w, ht)
        return best

    def gaps(x, y, w, ht, obst):
        """Free distance on each side of the box up to what stops it: the
        room's outline or a line."""
        gl = x - w / 2 - bx0
        gr = bx1 - (x + w / 2)
        gb = y - ht / 2 - by0
        gt = by1 - (y + ht / 2)
        if len(obst):
            band_y = np.abs(obst[:, 1] - y) <= ht / 2
            band_x = np.abs(obst[:, 0] - x) <= w / 2
            left = obst[band_y & (obst[:, 0] < x - w / 2), 0]
            right = obst[band_y & (obst[:, 0] > x + w / 2), 0]
            below = obst[band_x & (obst[:, 1] < y - ht / 2), 1]
            above = obst[band_x & (obst[:, 1] > y + ht / 2), 1]
            if len(left):
                gl = min(gl, x - w / 2 - left.max())
            if len(right):
                gr = min(gr, right.min() - (x + w / 2))
            if len(below):
                gb = min(gb, y - ht / 2 - below.max())
            if len(above):
                gt = min(gt, above.min() - (y + ht / 2))
        return gl, gr, gb, gt

    def recentre(x, y, w, ht, obst, clear=CLEAR):
        """Slide the box (at most 0.4 m each way) to where the free space on
        its two sides is equal."""
        for axis in (0, 1):
            best = None
            for k in range(-20, 21):
                dx_, dy_ = (k * 0.02, 0.0) if axis == 0 else (0.0, k * 0.02)
                nx, ny = x + dx_, y + dy_
                if k and not ok(nx, ny, w, ht, obst, clear):
                    continue
                g = gaps(nx, ny, w, ht, obst)
                a, b = (g[0], g[1]) if axis == 0 else (g[2], g[3])
                score = (round(min(a, b), 3), -abs(k))
                if best is None or score > best[0]:
                    best = (score, nx, ny)
            x, y = best[1], best[2]
        return x, y

    steps = [(1.0, obst_all, near, False, CLEAR), (1.0, obst_heavy, None, True, CLEAR),
             # the full height with a tighter margin to what is in the way, before any shrinking
             (1.0, obst_heavy, None, True, TIGHT),
             (STANDARD_MIN, obst_all, near, False, CLEAR), (STANDARD_MIN, obst_heavy, None, True, CLEAR),
             (0.7, obst_heavy, None, True, CLEAR), (0.6, obst_heavy, None, True, CLEAR), (0.5, obst_heavy, None, True, CLEAR)]
    for scale, obst, max_dist, masked, clear in steps:
        hh = h * scale
        for lines in _variants(name, area_txt):
            for rot in ((0, 90) if tall else (0,)):
                got = search(lines, hh, obst, max_dist, rot, clear)
                if got is not None:
                    x, y = recentre(got[1], got[2], got[3], got[4], obst, clear)
                    return {"x": x, "y": y, "h": hh, "lines": lines, "rot": rot, "w": got[3],
                            "hgt": got[4], "masked": masked, "scale": scale}
    hh = h * 0.5
    lines = [name, area_txt]
    w, ht = _box(lines, hh, 0.04)
    return {"x": cx, "y": cy, "h": hh, "lines": lines, "rot": 0, "w": w, "hgt": ht, "masked": False,
            "scale": 0.0}


def plan_labels(fills, segs, heavy, text_h: float) -> list:
    """Place the label of every filled room of one plan (smallest room first,
    so the tight ones get their pick). -> list of placements, each the dict of
    :func:`place_label` plus ``fill`` (the room) and ``rect`` (x0, y0, x1, y1:
    the box on the plan)."""
    taken, out = [], []
    for f in sorted(fills, key=lambda r: r["area"]):
        area_txt = f"{f['area']:.2f} ตร.ม."
        pl = place_label(f["poly"], f["name"], area_txt, text_h, segs, taken, heavy)
        taken.append((pl["x"], pl["y"], pl["w"], pl["hgt"]))
        pl["fill"] = f
        pl["rect"] = (pl["x"] - pl["w"] / 2, pl["y"] - pl["hgt"] / 2, pl["x"] + pl["w"] / 2, pl["y"] + pl["hgt"] / 2)
        out.append(pl)
    return out


def clip_thin(segs, rects, stub: float = STUB):
    """The thin lines ``segs`` (N x 4) with the parts inside ``rects`` cut
    away, and any piece left over that is shorter than ``stub`` dropped.
    Lines that touch no rectangle come back exactly as they were."""
    out = []
    for sx, sy, ex, ey in np.asarray(segs, dtype=float).reshape(-1, 4):
        dxs, dys = ex - sx, ey - sy
        cuts = []
        for x0, y0, x1, y1 in rects:
            t0, t1 = 0.0, 1.0
            hit = True
            for p, q in ((-dxs, sx - x0), (dxs, x1 - sx), (-dys, sy - y0), (dys, y1 - sy)):
                if p == 0:
                    if q < 0:
                        hit = False
                        break
                else:
                    r = q / p
                    if p < 0:
                        t0 = max(t0, r)
                    else:
                        t1 = min(t1, r)
            if hit and t0 < t1:
                cuts.append((t0, t1))
        if not cuts:
            out.append((sx, sy, ex, ey))
            continue
        cuts.sort()
        merged = [list(cuts[0])]
        for a, b in cuts[1:]:
            if a <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        length = float(np.hypot(dxs, dys))
        pos = 0.0
        for a, b in merged + [[1.0, 1.0]]:
            if a - pos > 1e-9 and (a - pos) * length >= stub:
                out.append((sx + dxs * pos, sy + dys * pos, sx + dxs * a, sy + dys * a))
            pos = max(pos, b)
    return out


def draw_labels(msp, placements, dx: float, dy: float, style: str = "TH") -> dict:
    """Write the labels. -> {"labels", "small": [names set below 0.85 of the
    standard height], "unclean": [names that found no clear place]}."""
    from ezdxf.enums import TextEntityAlignment
    small, unclean = [], []
    for pl in placements:
        x, y, hh, rot, lines = pl["x"], pl["y"], pl["h"], pl["rot"], pl["lines"]
        name = pl["fill"]["name"]
        if pl["scale"] < STANDARD_MIN:
            small.append(name)
        if pl["scale"] == 0.0:
            unclean.append(name)
        n = len(lines)
        for k, text in enumerate(lines):
            off = ((n - 1) / 2 - k) * LINE_PITCH * hh          # + = towards the text's "up"
            px, py = (x - off, y) if rot else (x, y + off)
            msp.add_text(text, height=hh * (0.9 if k == n - 1 else 1.0), rotation=rot,
                         dxfattribs={"layer": TEXT_LAYER, "style": style}
                         ).set_placement((px + dx, py + dy), align=TextEntityAlignment.MIDDLE_CENTER)
    return {"labels": len(placements), "small": small, "unclean": unclean}


def legend_rows(used) -> list:
    """Rows of the legend, in the table's fixed order. ``used`` = [(group
    text, the kind's own legend text, rgb, short name, kind order)] (the last
    two may be left out; a sixth, the fallback colour index, may follow). A group with one kind on the sheet is named by that
    kind; with several, by the short names of the kinds really present
    ("ศาลา / ชาน" — not the whole group, which may name a kind the sheet has
    not got)."""
    full = []
    for u in used:
        group, kind_text, rgb = u[0], u[1], u[2]
        short = u[3] if len(u) > 3 else kind_text
        order = u[4] if len(u) > 4 else 0
        full.append((group, kind_text, rgb, short, order, u[5] if len(u) > 5 else None))
    members = {}
    for group, kind_text, _rgb, short, order, _aci in full:
        members.setdefault(group, {})[kind_text] = (order, short)
    gorder = kinds.group_order()
    seen, rows = set(), []
    for group, kind_text, rgb, _short, _order, aci in sorted(full, key=lambda u: (gorder.index(u[0]) if u[0] in gorder else 99, u[4])):
        mem = members[group]
        if len(mem) > 1:
            label = " / ".join(sh for _o, sh in sorted(mem.values()))
        else:
            label = kind_text
        k = (label, tuple(round(c, 3) for c in rgb))
        if k not in seen:
            seen.add(k)
            rows.append((label, rgb, aci))
    return rows


def add_legend(msp, used, x: float, y_top: float, text_h: float, mode: str, style: str = "TH") -> int:
    """Colour chips for the kinds used, in a frame as wide as its widest line
    with the same margin on the left and the right."""
    from ezdxf.enums import TextEntityAlignment
    rows = legend_rows(used)
    if not rows:
        return 0
    title = f"สีห้อง ({MODE_TH.get(mode, mode)})"
    pitch = 1.7 * text_h
    cw, ch, gap = 2.2 * text_h, 1.2 * text_h, 0.6 * text_h
    margin = 0.7 * text_h
    wid = max(INK * geo.measure(title, text_h * 1.1),
              max(cw + gap + INK * geo.measure(lb, text_h) for lb, _, _a in rows))
    fx0, fy0 = x - margin, y_top + 1.0 * text_h     # room for the marks above the title
    fx1 = x + wid + margin
    fy1 = y_top - 2.0 * text_h - (len(rows) - 1) * pitch - ch - BOTTOM_GAP * text_h
    msp.add_lwpolyline([(fx0, fy1), (fx1, fy1), (fx1, fy0), (fx0, fy0)], close=True,
                       dxfattribs={"layer": KEY_LAYER})
    msp.add_text(title, height=text_h * 1.1, dxfattribs={"layer": TEXT_LAYER, "style": style}
                 ).set_placement((x, y_top), align=TextEntityAlignment.TOP_LEFT)
    y = y_top - 2.0 * text_h
    for label, rgb, aci in rows:
        chip = [(x, y - ch), (x + cw, y - ch), (x + cw, y), (x, y)]
        _hatch(msp, KEY_LAYER, rgb, chip, aci)                    # not FILL_LAYER: that holds the rooms only
        msp.add_lwpolyline(chip, close=True, dxfattribs={"layer": KEY_LAYER})
        msp.add_text(label, height=text_h, dxfattribs={"layer": TEXT_LAYER, "style": style}
                     ).set_placement((x + cw + gap, y - ch / 2), align=TextEntityAlignment.MIDDLE_LEFT)
        y -= pitch
    return len(rows)
