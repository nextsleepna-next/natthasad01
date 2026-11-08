# SPDX-License-Identifier: GPL-3.0-or-later
"""3D -> 2D: a model's plans and elevations, laid out on ONE drawing.

``python -m yotathai.convert.views_to_dxf model.igz sheet.dxf
[--cuts 1.2,4.65] [--no-roof] [--no-elevations]``

* a floor plan per cut level (a horizontal section through the model, the
  cut walls drawn heavy and filled grey, what lies below in thin line);
* the roof plan (the model seen from above);
* the four elevations (front, right, back, left).

Hidden-line removal is the 3D engine's own (core.hlr, the same pass its
sheet composer uses), so what comes out is what the model really shows.
Units: metres, $INSUNITS = 6 — the 2D engine opens it at true size. Thai
labels use Tahoma (on every Mac and Windows PC); the font is named, never
copied.

The sheet carries NO background (no dark fill): it is plain lines, hatches
and text, so it prints white. ``--layout A3`` (or A4/A2/A1/A0) also adds a
paper Layout with one viewport at a round scale, ready to plot on white.

``--room-fill off|presentation|construction`` (bare ``--room-fill`` =
presentation) colours the floor of each labelled room on the plans, from the
room labels kept in the model (``room-import`` / ``room-add``): a flat pastel
hatch on layer ``Y-ROOM-FILL`` under the section lines, the room's name and
area, and a legend of the kinds used. Default ``off``: a sheet is then exactly
what it was before room labels existed. ``construction`` mixes the colours
12% with white so they stay behind the lines.

The Yotathai 3D window calls :func:`export_sheet` on its live scene, so an
unsaved model can be sent too.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from yotathai.convert._common import run, use_3d_engine

#: (camera view, Thai title) for the elevations, in reading order.
ELEVATIONS = [("front", "รูปด้านหน้า"), ("right", "รูปด้านขวา"),
              ("back", "รูปด้านหลัง"), ("left", "รูปด้านซ้าย")]

LAYERS = [  # name, ACI colour, lineweight (1/100 mm)
    ("Y-EDGE", 7, 18),
    ("Y-PROFILE", 7, 35),
    ("Y-CUT", 7, 50),
    ("Y-CUT-FILL", 8, 0),
    ("Y-TEXT", 7, 25),
]
FONT = "Tahoma.ttf"


def _camera(view: str):
    from core.camera import OrbitCamera
    cam = OrbitCamera()
    cam.set_view(view)
    if cam.perspective:
        cam.toggle_projection()
    return cam


def _z_range(scene, geometry):
    """Lowest and highest point of the model (world z)."""
    import numpy as np
    tris = geometry[0]
    pts = np.asarray(tris, dtype=float).reshape(-1, 3) if len(tris) else None
    if pts is None or not len(pts):
        raise ValueError("the model is empty — nothing to draw")
    return float(pts[:, 2].min()), float(pts[:, 2].max())


def _drawing(scene, view, geometry, cut_z=None):
    """The hidden-line drawing of one view; with ``cut_z`` a plan cut by a
    temporary horizontal section plane (the model is left as it was)."""
    from core.hlr import hlr_drawing
    if cut_z is None:
        saved = getattr(scene, "show_section_cuts", True)
        scene.show_section_cuts = False        # elevations see the whole model
        try:
            return hlr_drawing(scene, _camera(view), geometry=geometry)
        finally:
            scene.show_section_cuts = saved
    from PySide6.QtGui import QVector3D
    from core.section import SectionPlane
    plane = SectionPlane(QVector3D(0.0, 0.0, cut_z), QVector3D(0.0, 0.0, 1.0),
                         name="Yotathai plan cut", symbol="", active=False)
    before = scene.active_section()
    saved = getattr(scene, "show_section_cuts", True)
    scene.section_planes.append(plane)
    try:
        scene.set_active_section(plane)
        scene.show_section_cuts = True
        return hlr_drawing(scene, _camera(view), geometry=geometry)
    finally:
        scene.section_planes.remove(plane)
        scene.set_active_section(before)
        scene.show_section_cuts = saved


def default_cut(zmin: float, zmax: float) -> float:
    """1.20 m above the floor: level 0 when the model stands on it (a slab
    hanging below 0 must not lower the cut), else its lowest point."""
    base = 0.0 if zmin <= 0.0 < zmax else zmin
    return min(base + 1.20, (zmin + zmax) / 2) if zmax - base < 1.4 else base + 1.20


class _Drawing:
    """The parts of a core.hlr drawing the sheet needs — picklable, so a
    worker process can hand it back."""

    def __init__(self, segs, kinds, loops):
        self.segs, self.kinds, self.loops = segs, kinds, loops


def _view_job(model: str, view: str, cut_z):
    """Worker: load the model and draw one view (runs in its own process —
    the hidden-line pass is pure Python, ~10 s per elevation on a big
    building, and the views do not depend on each other)."""
    use_3d_engine()
    from core.hlr import collect_geometry
    from core.scene import Scene
    from formats.igz import load_into
    scene = Scene()
    load_into(scene, Path(model))
    tris, hard, soft = collect_geometry(scene)
    d = _drawing(scene, view, (tris, hard, soft, None), cut_z=cut_z)
    return _Drawing(d.segs, d.kinds, d.loops)


#: Above this many triangles a model's views are drawn in parallel.
PARALLEL_FROM = 3000


ROOM_FILL_MODES = ("off", "presentation", "construction")


def export_sheet(scene, out: Path, cuts=None, roof: bool = True,
                 elevations: bool = True, title: str = "",
                 model_path: Path | None = None, workers: int | None = None,
                 progress=None, layout: str = "", room_fill: str = "off",
                 rooms: dict | None = None) -> dict:
    """Write the sheet to ``out``; return a report. ``cuts`` are absolute
    levels in metres (default: 1.20 m above the lowest point). With
    ``model_path`` (the .igz the scene came from) a big model's views are
    drawn by ``workers`` processes at once. ``room_fill`` colours the labelled
    rooms on the plans (see the module doc); ``rooms`` = a room-label book
    (default: the one stored in the scene)."""
    if room_fill not in ROOM_FILL_MODES:
        raise ValueError(f"--room-fill must be one of {', '.join(ROOM_FILL_MODES)}")
    import os

    from core.hlr import collect_geometry

    tris, hard, soft = collect_geometry(scene)
    geometry = (tris, hard, soft, None)
    zmin, zmax = _z_range(scene, geometry)
    if cuts is None:
        cuts = [default_cut(zmin, zmax)]
    cuts = sorted(float(c) for c in cuts)
    jobs = []   # (title, view, cut_z, row)
    for z in cuts:
        if not (zmin < z < zmax):
            raise ValueError(f"cut level {z:+.2f} is outside the model "
                             f"({zmin:+.2f} … {zmax:+.2f} m)")
        jobs.append((f"ผังพื้น ตัดที่ระดับ {z:+.2f} ม.", "top", z, 0))
    if roof:
        jobs.append(("ผังหลังคา (มองจากด้านบน)", "top", None, 0))
    if elevations:
        for view, name in ELEVATIONS:
            jobs.append((name, view, None, 1))
    if workers is None:
        workers = max(1, min(len(jobs), (os.cpu_count() or 2) - 1))
    drawings = []
    if model_path is not None and workers > 1 and len(tris) >= PARALLEL_FROM:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_view_job, str(model_path), view, z)
                       for _t, view, z, _r in jobs]
            for n, fut in enumerate(futures, 1):
                drawings.append(fut.result())
                if progress is not None:
                    progress(n, len(jobs))
    else:
        for n, (_t, view, z, _r) in enumerate(jobs, 1):
            drawings.append(_drawing(scene, view, geometry, cut_z=z))
            if progress is not None:
                progress(n, len(jobs))
    keep = [n for n, d in enumerate(drawings) if len(d.segs)]
    views = [(jobs[n][0], drawings[n], jobs[n][3]) for n in keep]
    if not views:
        raise ValueError("no lines came out of the model")
    room_plans, room_notes = None, []
    if room_fill != "off":
        from yotathai.rooms import fill, store
        book = store.normalize(rooms) if rooms is not None else store.book_of_scene(scene)
        if not book["rooms"]:
            room_notes.append("ไม่มีป้ายห้องในโมเดล — แบบออกมาเหมือนเดิม")
        else:
            room_plans = []
            for n in keep:
                z = jobs[n][2]
                if z is None:
                    room_plans.append(None)
                    continue
                plan = fill.room_fills(book, cut_z=z, mode=room_fill)
                if plan["level"] is None:
                    room_notes.append(f"ระดับตัด {z:+.2f} ม. ไม่อยู่ในชั้นใดของป้ายห้อง — ไม่ลงสี")
                plan["cut_z"] = z
                room_plans.append(plan)
    report = write_sheet(views, out, title, layout=layout, room_plans=room_plans,
                         room_fill=room_fill, room_notes=room_notes)
    report.update({"z_range": [round(zmin, 3), round(zmax, 3)],
                   "cuts": [round(c, 3) for c in cuts]})
    return report


PAPER_MM = {"A4": (297.0, 210.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0),
            "A1": (841.0, 594.0), "A0": (1189.0, 841.0)}   # landscape
SCALES = (10, 20, 25, 50, 75, 100, 125, 150, 200, 250, 300, 400, 500, 750,
          1000, 2000)
PAPER_BORDER_MM = 10.0


def add_paper_layout(doc, msp, paper: str):
    """A Layout named ``paper`` (e.g. "A3") with one viewport showing the
    whole modelspace at the largest round 1:N that fits, margins 0 so the
    sheet is (0, 0, w, h). Returns (layout name, scale denominator)."""
    from ezdxf import bbox

    if paper not in PAPER_MM:
        raise ValueError(f"--layout must be one of {', '.join(PAPER_MM)}")
    w, h = PAPER_MM[paper]
    box = bbox.extents(msp)
    if not box.has_data:
        raise ValueError("nothing to put on a layout")
    mw = box.extmax.x - box.extmin.x
    mh = box.extmax.y - box.extmin.y
    aw, ah = w - 2 * PAPER_BORDER_MM, h - 2 * PAPER_BORDER_MM
    # 1 paper mm = N model mm = N / 1000 m
    scale = next((n for n in SCALES if mw * 1000.0 / n <= aw
                  and mh * 1000.0 / n <= ah), SCALES[-1])
    layout = doc.layouts.new(paper)
    layout.page_setup(size=(w, h), margins=(0, 0, 0, 0), units="mm",
                      offset=(0, 0), rotation=0, scale=0, name=paper)
    layout.add_viewport(
        center=(w / 2, h / 2), size=(aw, ah),
        view_center_point=((box.extmin.x + box.extmax.x) / 2,
                           (box.extmin.y + box.extmax.y) / 2),
        view_height=ah * scale / 1000.0)
    return paper, scale


PAD_LAYER = "Y-PAD"


def add_edge_room(doc, msp, share: float = 0.045) -> None:
    """Leave an empty margin round the sheet when it is plotted to a page.

    The 2D engine fits the bounding box of everything drawn to the page with
    no margin, and a text line's box is its cap height only: Thai vowels and
    tone marks above it (two stacked reach ~0.45 of the height) land on the
    printer's clip at the top edge and are cut off — "ชั้น" prints as "ชัน" —
    and the tails below touch the bottom edge. Two zero-length white marks at
    the corners of a box ``share`` of the sheet's size larger on every side
    make the fit leave that margin. They print as nothing on paper. Only a sheet
    with room colours gets them: without room colours a sheet is exactly what it
    was before room labels existed."""
    from ezdxf import bbox
    box = bbox.extents(msp)
    if not box.has_data:
        return
    pad = share * max(box.extmax.x - box.extmin.x, box.extmax.y - box.extmin.y)
    if PAD_LAYER not in doc.layers:
        doc.layers.add(PAD_LAYER, color=7).dxf.lineweight = 0
    for x, y in ((box.extmin.x - pad, box.extmin.y - pad), (box.extmax.x + pad, box.extmax.y + pad)):
        msp.add_line((x, y), (x, y), dxfattribs={"layer": PAD_LAYER, "true_color": 0xFFFFFF})


def write_sheet(views, out: Path, title: str = "", layout: str = "",
                room_plans=None, room_fill: str = "off", room_notes=()) -> dict:
    """Lay ``views`` = [(title, drawing, row)] out on one DXF: plans on
    row 0, elevations on row 1 below, each row left to right.
    ``room_plans`` (one entry per view, from ``rooms.fill.room_fills``, or
    None) colours the rooms of those plans."""
    import ezdxf
    import numpy as np
    from ezdxf.enums import TextEntityAlignment

    from core.hlr import KIND_CUT, KIND_PROFILE

    def bounds(d):
        xs = d.segs[:, [0, 2]]
        ys = d.segs[:, [1, 3]]
        return float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())

    sizes = [bounds(d) for _t, d, _r in views]
    big = max(max(b[2] - b[0], b[3] - b[1]) for b in sizes)
    gap = max(2.0, 0.25 * big)
    text_h = min(max(big * 0.022, 0.20), 1.20)

    doc = ezdxf.new("R2018", setup=True)
    doc.units = ezdxf.units.M
    doc.header["$INSUNITS"] = 6
    doc.header["$MEASUREMENT"] = 1
    doc.styles.add("TH", font=FONT)
    for name, color, lw in LAYERS:
        layer = doc.layers.add(name, color=color)
        if lw:
            layer.dxf.lineweight = lw
    msp = doc.modelspace()

    rows = {r for _t, _d, r in views}
    row_h = {r: max((b[3] - b[1]) for (_t, _d, rr), b in zip(views, sizes) if rr == r)
             for r in rows}
    # Row 0 stands on y = 0; row 1 hangs from a line below it.
    row_y = {0: 0.0, 1: -1.5 * gap} if 0 in rows else {1: 0.0}
    cursor = {r: 0.0 for r in rows}
    report_views = []
    room_report = {"mode": room_fill, "plans": [], "notes": list(room_notes)}
    legend_used = []
    for vi, ((vtitle, d, r), (x0, y0, x1, y1)) in enumerate(zip(views, sizes)):
        dx = cursor[r] - x0
        dy = row_y[r] - y0 if r == 0 else row_y[r] - y1
        k = d.kinds
        rplan = room_plans[vi] if room_plans else None
        if rplan and rplan["fills"]:
            # the colour goes down first: the section lines and the grey wall
            # fill of this plan are drawn after it, so the walls lie on top
            from yotathai.rooms import draw as room_draw
            room_draw.ensure_layers(doc)
            room_draw.add_fills(msp, rplan["fills"], dx, dy)
            # labels are placed now, so the thin lines can be cut away under them
            placements = room_draw.plan_labels(
                rplan["fills"], d.segs, d.segs[(k == KIND_CUT) | (k == KIND_PROFILE)], text_h * 0.85)
            label_rects = [pl["rect"] for pl in placements]
        else:
            placements, label_rects = None, None
        for layer, mask in (("Y-CUT", k == KIND_CUT), ("Y-PROFILE", k == KIND_PROFILE),
                            ("Y-EDGE", (k != KIND_CUT) & (k != KIND_PROFILE))):
            segs_ = d.segs[mask]
            if layer == "Y-EDGE" and label_rects:
                segs_ = room_draw.clip_thin(segs_, label_rects)
            for sx, sy, ex, ey in segs_:
                msp.add_line((sx + dx, sy + dy), (ex + dx, ey + dy),
                             dxfattribs={"layer": layer})
        fills = 0
        for loop in d.loops or []:
            pts = np.asarray(loop, dtype=float)
            if len(pts) < 3:
                continue
            hatch = msp.add_hatch(color=8, dxfattribs={"layer": "Y-CUT-FILL"})
            hatch.paths.add_polyline_path([(x + dx, y + dy) for x, y in pts[:, :2]],
                                          is_closed=True)
            fills += 1
        if rplan and rplan["fills"]:
            lab = room_draw.draw_labels(msp, placements, dx, dy)
            legend_used += [(f["legend"], f["legend_kind"], f["rgb"], f["legend_short"], f["kind_order"], f["aci"])
                            for f in rplan["fills"]]
            room_report["plans"].append({
                "title": vtitle, "level": rplan["level"]["id"], "hatches": len(rplan["fills"]),
                "labels": lab["labels"], "labels_on_lines": lab["unclean"],
                "labels_below_standard": lab["small"],
                "skipped": [f"{s_['id']} {s_['name']} ({s_['reason']})" for s_ in rplan["skipped"]]})
        cx = (x0 + x1) / 2 + dx
        base = (y0 + dy) - 1.0 * text_h
        msp.add_text(vtitle, height=text_h,
                     dxfattribs={"layer": "Y-TEXT", "style": "TH"}
                     ).set_placement((cx, base), align=TextEntityAlignment.TOP_CENTER)
        cursor[r] += (x1 - x0) + gap
        report_views.append({"title": vtitle, "lines": int(len(d.segs)),
                             "cut_fills": fills,
                             "size_m": [round(x1 - x0, 3), round(y1 - y0, 3)]})

    if legend_used:
        room_report["legend_rows"] = room_draw.add_legend(
            msp, legend_used, cursor[0] - gap + 0.7 * text_h * 2, (row_h[0] if 0 in rows else 0.0),
            text_h, room_fill)
    heading = title or "แบบจากโมเดล 3 มิติ"
    top = (row_h[0] if 0 in rows else 0.0) + 0.7 * gap
    msp.add_text(heading, height=text_h * 1.6,
                 dxfattribs={"layer": "Y-TEXT", "style": "TH"}
                 ).set_placement((0.0, top), align=TextEntityAlignment.BOTTOM_LEFT)
    msp.add_text("หน่วย: เมตร · ส่งจาก Yotathai Plan", height=text_h * 0.8,
                 dxfattribs={"layer": "Y-TEXT", "style": "TH"}
                 ).set_placement((0.0, top - 0.6 * text_h),
                                 align=TextEntityAlignment.TOP_LEFT)
    report_layout = {}
    if layout:
        if legend_used:              # only a sheet that carries room colours gets the margin
            add_edge_room(doc, msp)
        name, scale = add_paper_layout(doc, msp, layout)
        report_layout = {"layout": name, "layout_scale": f"1:{scale}"}
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(out)
    extra = {"room_fill": room_report} if room_fill != "off" else {}
    return {"drawing": str(out), "views": report_views, **report_layout, **extra}


def main(argv) -> dict:
    ap = argparse.ArgumentParser(description="3D model -> 2D plans and elevations (DXF)")
    ap.add_argument("model", type=Path, help=".igz model")
    ap.add_argument("out", type=Path, help="DXF to write")
    ap.add_argument("--cuts", default="", help="plan cut levels in metres, e.g. 1.65,5.65")
    ap.add_argument("--no-roof", action="store_true")
    ap.add_argument("--no-elevations", action="store_true")
    ap.add_argument("--title", default="")
    ap.add_argument("--layout", default="", choices=["", *PAPER_MM],
                    help="also add a paper Layout (A4..A0, landscape) with one "
                         "viewport at a round scale")
    ap.add_argument("--room-fill", nargs="?", const="presentation", default="off",
                    choices=ROOM_FILL_MODES, dest="room_fill",
                    help="colour the floor of each labelled room on the plans: presentation "
                         "(clear pastel) or construction (paler, behind the lines); "
                         "default off; bare --room-fill = presentation")
    ap.add_argument("--workers", type=int, default=None,
                    help="processes for a big model (default: one per view)")
    a = ap.parse_args(argv)
    use_3d_engine()
    from core.scene import Scene
    from formats.igz import load_into
    scene = Scene()
    load_into(scene, a.model)
    cuts = [float(c) for c in a.cuts.replace(" ", "").split(",") if c] or None
    return export_sheet(scene, a.out, cuts=cuts, roof=not a.no_roof,
                        elevations=not a.no_elevations,
                        title=a.title or a.model.stem, model_path=a.model,
                        workers=a.workers, layout=a.layout, room_fill=a.room_fill,
                        progress=lambda n, total: print(f"view {n}/{total}",
                                                        flush=True))


if __name__ == "__main__":
    sys.exit(run(main))
