# SPDX-License-Identifier: GPL-3.0-or-later
"""room-suggest and ``room-add --at``: spaces the walls enclose.

This is a helper that PROPOSES. It reads the walls cut at the level (doors
shut), finds the enclosed spaces and writes them to a proposal file — it never
touches the model, and nothing in a proposal is drawn on a sheet. A person or
an AI must name each space (name, kind), mark it ``"confirmed": true`` and
bring it back with ``room-import --from-suggest``. Why it is not used on its
own: the walls give an outline, never a name or a kind; spaces that are open
to each other merge into one; a wall that is not tagged is invisible.
"""
from __future__ import annotations

import statistics

from . import geometry as geo
from . import model, store

BIG_M2 = 40.0
BIG_RATIO = 3.0


def propose(scene, book: dict, level: dict) -> dict:
    """Proposals for one level — both with doors shut and with inside doors
    open (the second only to tell how much the house is one open volume)."""
    closed, cut = model.floor_walls(scene, level, "closed")
    opened, _ = model.floor_walls(scene, level, "open")
    spaces = closed.spaces()
    areas = [geo.area(s) for s in spaces]
    med = statistics.median(areas) if areas else 0.0
    labelled = [r for r in book["rooms"] if r.get("level") == level["id"] and r.get("confirmed", True)]
    proposals = []
    for i, sp in enumerate(spaces, 1):
        a = geo.area(sp)
        inside = []
        for r in labelled:
            p = geo.dedupe([tuple(q) for q in r["poly"]])
            c = geo.centroid(p)
            if geo.contains(sp, c):
                inside.append(r["name"])
        flags, notes = [], []
        if a > BIG_M2 or (len(areas) >= 3 and a > BIG_RATIO * med):
            flags.append("many-rooms")
            notes.append(f"พื้นที่ {a:.1f} ตร.ม. ใหญ่ผิดปกติ — น่าจะหลายห้องที่โล่งต่อกัน")
        if len(inside) >= 2:
            flags.append("many-labels")
            notes.append(f"มีป้ายอยู่ข้างใน {len(inside)} ห้อง: {', '.join(inside)} — น่าจะหลายห้อง")
        if not inside and labelled:
            flags.append("no-label")
            notes.append("ยังไม่มีป้ายอยู่ข้างใน")
        proposals.append({"id": f"s{i:02d}", "level": level["id"],
                          "poly": [[round(x, 3), round(y, 3)] for x, y in sp],
                          "area_m2": round(a, 2), "labels_inside": inside, "flags": flags, "notes": notes,
                          "name": "", "kind": "", "confirmed": False})
    return {"v": 1, "kind": "room-suggest", "level": dict(level), "cut_z": round(cut, 3),
            "doors_shut": len(spaces), "doors_open": len(opened.spaces()),
            "proposals": proposals,
            "howto": "ตั้ง name และ kind ของแต่ละช่องที่ใช่ แล้วเปลี่ยน confirmed เป็น true ก่อน "
                     "room-import MODEL.igz --from-suggest ไฟล์นี้ · ช่องที่ confirmed=false ไม่ถูกนำเข้า"}


def space_at(scene, level: dict, point):
    """The enclosed space (doors shut) holding ``point``, or an error telling
    where the walls leak. -> (polygon or None, leak dict or None)."""
    fw, _cut = model.floor_walls(scene, level, "closed")
    for sp in fw.spaces():
        if geo.contains(sp, point):
            return sp, None
    return None, model.find_leak(fw, point)
