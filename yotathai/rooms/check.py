# SPDX-License-Identifier: GPL-3.0-or-later
"""room-check: are the labels sound, and do they still sit on the model's walls?

Errors (the sheet would be wrong): unknown level or kind, a bad or
self-crossing outline, two rooms of one level sharing more than 0.01 m².
Warnings (the sheet is drawn, a person should look): a label not confirmed
(never filled), a repeated name on a level, a label with (almost) no wall
around it, a label whose centre is outside the building, an enclosed space of
the model that no label covers, sums of rooms far from the building's area.
Nothing is changed in the model.
"""
from __future__ import annotations

from . import geometry as geo
from . import kinds, model

OVERLAP_M2 = 0.01
UNCOVERED_M2 = 1.0           # an enclosed space left bare by labels
UNCOVERED_SHARE = 0.03
COVERAGE_WARN = 0.25         # share of a room's outline that has a wall on it
SUM_MIN, SUM_MAX = 0.90, 1.00


def _issue(level, code, msg, room=None, **extra):
    d = {"level": level, "code": code, "msg": msg}
    if room:
        d["room"] = room
    d.update(extra)
    return d


def check_structure(book: dict) -> list:
    """Checks that need no model."""
    out = []
    levels = {lv["id"]: lv for lv in book["levels"]}
    seen_ids = set()
    good = []                                   # rooms with a usable outline
    for r in book["rooms"]:
        rid = r.get("id") or "?"
        label = f"{rid} {r.get('name', '')}".strip()
        if rid in seen_ids:
            out.append(_issue("error", "dup-id", f"{label}: รหัสห้องซ้ำ", rid))
        seen_ids.add(rid)
        if not r.get("name"):
            out.append(_issue("error", "no-name", f"{rid}: ไม่มีชื่อห้อง", rid))
        if r.get("level") not in levels:
            out.append(_issue("error", "bad-level", f"{label}: ไม่รู้จักชั้น {r.get('level')!r}", rid))
        if not r.get("color") and not kinds.has_kind(r.get("kind")):
            out.append(_issue("error", "bad-kind", f"{label}: ไม่รู้จักชนิดห้อง {r.get('kind')!r}", rid))
        if not r.get("confirmed", True):
            out.append(_issue("warn", "unconfirmed", f"{label}: ยังไม่ยืนยัน — จะไม่ถูกลงสี", rid))
        try:
            poly = geo.dedupe([(float(x), float(y)) for x, y in (r.get("poly") or [])])
        except (TypeError, ValueError):
            poly = []
        if len(poly) < 3:
            out.append(_issue("error", "bad-poly", f"{label}: ขอบเขตมีน้อยกว่า 3 จุด", rid))
            continue
        if geo.area(poly) <= 1e-6:
            out.append(_issue("error", "bad-poly", f"{label}: ขอบเขตไม่มีพื้นที่", rid))
            continue
        if not geo.is_simple(poly):
            out.append(_issue("error", "self-cross", f"{label}: ขอบเขตตัดกันเอง", rid))
            continue
        good.append((r, poly))
    # overlaps and repeated names, per level
    for i, (a, pa) in enumerate(good):
        for b, pb in good[i + 1:]:
            if a.get("level") != b.get("level") or not (a.get("confirmed", True) and b.get("confirmed", True)):
                continue
            ov = geo.intersection_area(pa, pb)
            if ov > OVERLAP_M2:
                out.append(_issue("error", "overlap",
                                  f"{a['id']} {a['name']} ซ้อนกับ {b['id']} {b['name']} {ov:.2f} ตร.ม. (เกิน {OVERLAP_M2} ตร.ม.)",
                                  a["id"], other=b["id"], area=round(ov, 3)))
    names = {}
    for r, _p in good:
        names.setdefault((r.get("level"), r.get("name")), []).append(r["id"])
    for (lv, nm), ids in names.items():
        if len(ids) > 1:
            out.append(_issue("warn", "dup-name", f"ชั้น {lv}: ชื่อ {nm!r} ซ้ำ {len(ids)} ห้อง ({', '.join(ids)})", ids[0]))
    return out


def _coverage(poly, solids, step: float = 0.1, probe: float = 0.12) -> float:
    """Share of the outline of ``poly`` that has a wall on it (a solid of the
    cut within ``probe`` of the outline)."""
    boxes = [(geo.bbox(s), s) for s in solids]
    pts = []
    n = len(poly)
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        L = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        k = max(1, int(L / step))
        pts += [(x0 + (x1 - x0) * t / k, y0 + (y1 - y0) * t / k) for t in range(k)]
    hit = 0
    for x, y in pts:
        for dx, dy in ((0, 0), (probe, 0), (-probe, 0), (0, probe), (0, -probe)):
            q = (x + dx, y + dy)
            if any(bx0 <= q[0] <= bx1 and by0 <= q[1] <= by1 and geo.contains(s, q)
                   for (bx0, by0, bx1, by1), s in boxes):
                hit += 1
                break
    return hit / len(pts) if pts else 0.0


def check_model(book: dict, scene) -> tuple:
    """Checks against the walls of the model. -> (issues, per-level report)."""
    out, report = [], {}
    import numpy as np
    from core.hlr import collect_geometry
    tris, hard, soft = collect_geometry(scene)
    pts = np.asarray(tris, dtype=float).reshape(-1, 3)
    zmin, zmax = (float(pts[:, 2].min()), float(pts[:, 2].max())) if len(pts) else (0.0, 0.0)
    geometry = (tris, hard, soft, None)
    for lv in sorted(book["levels"], key=lambda v: v["z0"]):
        rooms = [r for r in book["rooms"] if r.get("level") == lv["id"] and r.get("confirmed", True)]
        if lv["z1"] <= zmin or lv["z0"] >= zmax:
            out.append(_issue("warn", "level-outside",
                              f"{lv['id']}: ช่วงสูง {lv['z0']:g}..{lv['z1']:g} ม. อยู่นอกตัวโมเดล ({zmin:.2f}..{zmax:.2f})"))
            continue
        fw, cut = model.floor_walls(scene, lv, "closed", geometry)
        polys = {}
        for r in rooms:
            p = geo.dedupe([(float(x), float(y)) for x, y in (r.get("poly") or [])])
            if len(p) >= 3 and geo.area(p) > 0:
                polys[r["id"]] = p
        outers = fw.outers()
        walled_sum = 0.0
        cov_report = {}
        for r in rooms:
            p = polys.get(r["id"])
            if p is None:
                continue
            walled = kinds.is_walled(r.get("kind")) if kinds.has_kind(r.get("kind")) else True
            cov = _coverage(p, fw.solids)
            cov_report[r["id"]] = round(cov, 2)
            if not walled:
                continue
            walled_sum += geo.area(p)
            c = geo.centroid(p)
            if not geo.contains(p, c):
                c = p[0]
            if not any(geo.contains(o, c) for o in outers):
                out.append(_issue("warn", "outside-building",
                                  f"{r['id']} {r['name']}: จุดกลางห้องอยู่นอกอาคารตามผนังที่ระดับตัด {cut:+.2f} ม.", r["id"]))
            elif cov < COVERAGE_WARN:
                out.append(_issue("warn", "no-walls",
                                  f"{r['id']} {r['name']}: มีผนังบนขอบเขตเพียง {cov * 100:.0f}% — ผนังอาจถูกย้ายแต่ป้ายไม่ตาม",
                                  r["id"], coverage=round(cov, 2)))
        # enclosed spaces of the model that the labels leave bare
        spaces = fw.spaces()
        for sp in spaces:
            a = geo.area(sp)
            labelled = sum(geo.intersection_area(sp, p) for p in polys.values())
            bare = a - labelled
            if bare > UNCOVERED_M2 and bare > UNCOVERED_SHARE * a:
                c = geo.centroid(sp)
                if not geo.contains(sp, c):
                    c = sp[0]
                out.append(_issue("warn", "bare-space",
                                  f"{lv['id']}: ช่องปิดล้อม {a:.1f} ตร.ม. ใกล้ ({c[0]:.1f}, {c[1]:.1f}) ไม่มีป้ายคลุม {bare:.1f} ตร.ม. — ส่วนนั้นจะไม่ลงสี",
                                  at=[round(c[0], 2), round(c[1], 2)], bare_m2=round(bare, 2)))
        env = fw.envelope_area()
        ratio = walled_sum / env if env else None
        report[lv["id"]] = {"cut_z": round(cut, 2), "rooms": len(rooms), "rooms_m2": round(walled_sum, 2),
                            "envelope_m2": round(env, 2), "ratio": round(ratio, 3) if ratio is not None else None,
                            "enclosed_spaces": len(spaces), "wall_coverage": cov_report}
        if ratio is not None and walled_sum > 0 and not (SUM_MIN <= ratio <= SUM_MAX):
            out.append(_issue("warn", "area-sum",
                              f"{lv['id']}: ผลรวมห้องมีผนัง {walled_sum:.1f} ตร.ม. = {ratio * 100:.0f}% ของพื้นที่ในขอบนอกผนัง "
                              f"{env:.1f} ตร.ม. (ปกติ {SUM_MIN * 100:.0f}–{SUM_MAX * 100:.0f}%)"))
    return out, report


def run(book: dict, scene=None) -> dict:
    issues = check_structure(book)
    per_level = {}
    if scene is not None:
        extra, per_level = check_model(book, scene)
        issues += extra
    errors = [i for i in issues if i["level"] == "error"]
    warns = [i for i in issues if i["level"] == "warn"]
    return {"passed": not errors, "rooms": len(book["rooms"]), "levels": per_level,
            "errors": errors, "warnings": warns, "with_model": scene is not None}
