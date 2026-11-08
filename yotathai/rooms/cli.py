# SPDX-License-Identifier: GPL-3.0-or-later
"""The room-* commands of ``yotathai_ai`` (no window; everything by command).

  room-import  MODEL.igz --design design.json [--levels ..] [--kinds map.json] [--replace] [--out X.igz]
  room-import  MODEL.igz --from-suggest proposals.json [--out X.igz]
  room-add     MODEL.igz --name N --kind K --level 1 (--rect x0,y0,x1,y1 | --poly "x,y;x,y;.." | --at x,y --confirm)
  room-list    MODEL.igz [--level 1]
  room-check   MODEL.igz [--no-model]
  room-suggest MODEL.igz [--level 1] --out proposals.json        (never edits the model)
  room-remove  MODEL.igz (--id r03 | --name N [--level 1])

Commands that change labels write into the model (or into the copy given by
``--out``); the geometry of the model is never touched.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import check as chk
from . import geometry as geo
from . import importer, kinds, store, suggest


def _save(book, model, out):
    info = store.write_book(model, book, out)
    return {"saved": info["file"], **({"note": "ข้อความ JSON ของไฟล์ถูกจัดรูปใหม่ (เนื้อหาโมเดลเท่าเดิม)"} if info["reformatted"] else {})}


def _level_or_fail(book, ref):
    lv = store.level_of(book, ref)
    if lv is None:
        have = ", ".join(f"{v['id']} ({v.get('name', '')})" for v in book["levels"]) or "ยังไม่มีชั้น"
        raise ValueError(f"ไม่รู้จักชั้น {ref!r} — ที่มี: {have} · เพิ่มได้ด้วย --levels \"L1:ชั้น 1:0:3\"")
    return lv


def _merge_levels(book, spec):
    """Add the levels of ``--levels`` that the book lacks; refuse a clash."""
    for lv in store.parse_levels(spec):
        have = store.level_of(book, lv["id"])
        if have is None:
            book["levels"].append(lv)
        elif (have["z0"], have["z1"]) != (lv["z0"], lv["z1"]):
            raise ValueError(f"ชั้น {lv['id']} มีอยู่แล้วที่ {have['z0']:g}..{have['z1']:g} ม. ไม่ตรงกับ --levels")


def _row(book, r):
    p = [tuple(q) for q in r.get("poly", [])]
    return {"id": r.get("id"), "name": r.get("name"), "kind": r.get("kind"), "level": r.get("level"),
            "area_m2": round(geo.area(p), 2) if len(p) >= 3 else 0.0, "src": r.get("src"),
            "confirmed": r.get("confirmed", True)}


# --- commands ----------------------------------------------------------------

def cmd_import(argv):
    ap = argparse.ArgumentParser(prog="room-import")
    ap.add_argument("model", type=Path)
    ap.add_argument("--design", type=Path, help="design.json ของโครงการ (ห้องจากผังที่ AI ใช้สร้างโมเดล)")
    ap.add_argument("--from-suggest", type=Path, help="ไฟล์ข้อเสนอจาก room-suggest ที่ตั้งชื่อ+ยืนยันแล้ว")
    ap.add_argument("--levels", default="")
    ap.add_argument("--kinds", type=Path, help="แผนที่ ชื่อห้อง → ชนิด (JSON)")
    ap.add_argument("--replace", action="store_true", help="แทนที่ป้ายเดิมทั้งหมด")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    if bool(a.design) == bool(a.from_suggest):
        raise ValueError("ให้ระบุอย่างใดอย่างหนึ่ง: --design หรือ --from-suggest")
    book = store.read_book(a.model)
    if book["rooms"] and not a.replace and a.design:
        raise ValueError(f"ไฟล์นี้มีป้ายอยู่แล้ว {len(book['rooms'])} ห้อง — ใช้ --replace ถ้าจะแทนที่")
    rep = {}
    if a.design:
        design = json.loads(a.design.read_text(encoding="utf-8-sig"))
        kmap = json.loads(a.kinds.read_text(encoding="utf-8-sig")) if a.kinds else None
        levels, rooms, notes = importer.rooms_from_design(
            design, kmap, store.parse_levels(a.levels) if a.levels else None)
        book = store.empty_book() if a.replace else book
        book["levels"] = levels
        for r in rooms:
            book["rooms"].append({"id": store.next_id(book), **r})
        rep.update({"imported": len(rooms), "levels": notes})
    else:
        prop = json.loads(a.from_suggest.read_text(encoding="utf-8-sig"))
        if prop.get("kind") != "room-suggest":
            raise ValueError("ไฟล์นี้ไม่ใช่ข้อเสนอจาก room-suggest")
        if a.levels:
            _merge_levels(book, a.levels)
        lv = prop.get("level")
        if lv and store.level_of(book, lv["id"]) is None:
            book["levels"].append(lv)
        added, skipped = 0, []
        for p in prop.get("proposals", []):
            if not p.get("confirmed") or not p.get("name") or not p.get("kind"):
                skipped.append(p.get("id"))
                continue
            if not kinds.has_kind(p["kind"]):
                raise ValueError(f"{p['id']}: ไม่รู้จักชนิด {p['kind']!r}")
            _level_or_fail(book, p["level"])
            book["rooms"].append({"id": store.next_id(book), "name": p["name"], "kind": p["kind"],
                                  "level": p["level"], "poly": p["poly"], "color": None, "src": "suggest",
                                  "confirmed": True, "note": f"จากข้อเสนอ {p['id']} ที่ยืนยันแล้ว"})
            added += 1
        rep.update({"imported": added, "skipped_unconfirmed": skipped})
        if not added:
            raise ValueError("ไม่มีข้อเสนอที่ยืนยันแล้ว (confirmed=true พร้อม name และ kind) — ไม่ได้บันทึกอะไร")
    rep.update(_save(book, a.model, a.out))
    rep["rooms_total"] = len(book["rooms"])
    rep["table"] = [f"{r['id']} {r['level']} {r['name']} [{r['kind']}] {geo.area([tuple(q) for q in r['poly']]):.2f} ตร.ม."
                    for r in book["rooms"]]
    return rep


def cmd_add(argv):
    ap = argparse.ArgumentParser(prog="room-add")
    ap.add_argument("model", type=Path)
    ap.add_argument("--name", required=True)
    ap.add_argument("--kind", required=True)
    ap.add_argument("--level", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--rect")
    g.add_argument("--poly")
    g.add_argument("--at", help="จุด x,y ในห้อง — โปรแกรมหาขอบเขตจากผนังให้ ต้องใส่ --confirm เพื่อยืนยันก่อนบันทึก")
    ap.add_argument("--confirm", action="store_true", help="ยืนยันขอบเขตที่เสนอจาก --at")
    ap.add_argument("--color", help="ทับสีของชนิด เช่น 0.9,0.8,0.7")
    ap.add_argument("--note", default="")
    ap.add_argument("--src", choices=("user", "ai"), default="user")
    ap.add_argument("--levels", default="", help="เพิ่มชั้นที่ยังไม่มี เช่น \"L1:ชั้น 1:0:3\"")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    book = store.read_book(a.model)
    if a.levels:
        _merge_levels(book, a.levels)
    lv = _level_or_fail(book, a.level)
    if not kinds.has_kind(a.kind):
        raise ValueError(f"ไม่รู้จักชนิด {a.kind!r} — ที่มี: {', '.join(kinds.kinds())}")
    rep = {}
    if a.rect:
        poly = geo.parse_rect(a.rect)
    elif a.poly:
        poly = geo.parse_poly(a.poly)
    else:
        pt = geo.parse_point(a.at)
        scene = _scene(a.model)
        poly, leak = suggest.space_at(scene, lv, pt)
        if poly is None:
            if leak:
                w = f" ช่องกว้างประมาณ {leak['width']:.2f} ม." if leak.get("width") else ""
                raise ValueError(f"รั่ว: พื้นที่รอบจุด {pt} ต่อเนื่องออกนอกอาคาร — ตำแหน่งรั่วใกล้ {leak['at']}{w} · "
                                 "ปิดช่องหรือใช้ --rect/--poly แทน (ไม่เดาต่อ)")
            raise ValueError(f"ไม่พบช่องปิดล้อมที่ครอบจุด {pt} (อาจอยู่บนผนัง หรือเล็กกว่า 0.5 ตร.ม.)")
        rep.update({"proposed_poly": [[round(x, 3), round(y, 3)] for x, y in poly],
                    "proposed_area_m2": round(geo.area(poly), 2)})
        if not a.confirm:
            rep.update({"saved": False,
                        "needs_confirm": "นี่คือขอบเขตที่โปรแกรมเดาจากผนัง (ปิดประตู) — ตรวจแล้วสั่งซ้ำพร้อม --confirm จึงจะบันทึก"})
            return rep
    poly = geo.ccw(geo.simplify_collinear(poly))
    if geo.area(poly) <= 0 or not geo.is_simple(poly):
        raise ValueError("ขอบเขตห้องไม่ถูกต้อง (ไม่มีพื้นที่ หรือตัดกันเอง)")
    color = [float(c) for c in a.color.split(",")] if a.color else None
    room = {"id": store.next_id(book), "name": a.name, "kind": a.kind, "level": lv["id"],
            "poly": [[round(x, 4), round(y, 4)] for x, y in poly], "color": color, "src": a.src,
            "confirmed": True, "note": a.note or ("ขอบเขตจากผนังที่ยืนยันแล้ว" if a.at else "")}
    book["rooms"].append(room)
    rep.update(_save(book, a.model, a.out))
    rep.update({"added": f"{room['id']} {room['name']} {geo.area(poly):.2f} ตร.ม.", "rooms_total": len(book["rooms"])})
    return rep


def cmd_list(argv):
    ap = argparse.ArgumentParser(prog="room-list")
    ap.add_argument("model", type=Path)
    ap.add_argument("--level")
    a = ap.parse_args(argv)
    book = store.read_book(a.model)
    lv = _level_or_fail(book, a.level) if a.level else None
    rows = [_row(book, r) for r in book["rooms"] if lv is None or r.get("level") == lv["id"]]
    return {"levels": [f"{v['id']} {v.get('name', '')} {v['z0']:g}..{v['z1']:g} ม." for v in book["levels"]],
            "count": len(rows), "rooms": rows,
            "text": [f"{r['id']} {r['level']} {r['name']} [{r['kind']}] {r['area_m2']:.2f} ตร.ม. ({r['src']}"
                     f"{'' if r['confirmed'] else ', ยังไม่ยืนยัน'})" for r in rows]}


def cmd_check(argv):
    ap = argparse.ArgumentParser(prog="room-check")
    ap.add_argument("model", type=Path)
    ap.add_argument("--no-model", action="store_true", help="ตรวจเฉพาะป้าย ไม่เทียบกับผนังในโมเดล")
    a = ap.parse_args(argv)
    book = store.read_book(a.model)
    scene = None if a.no_model or not book["rooms"] else _scene(a.model)
    rep = chk.run(book, scene)
    rep["errors"] = [i["msg"] for i in rep["errors"]]
    rep["warnings"] = [i["msg"] for i in rep["warnings"]]
    rep["summary"] = ("ผ่าน" if rep["passed"] else "ไม่ผ่าน") + f" · ผิดพลาด {len(rep['errors'])} · เตือน {len(rep['warnings'])}"
    return rep


def cmd_suggest(argv):
    ap = argparse.ArgumentParser(prog="room-suggest")
    ap.add_argument("model", type=Path)
    ap.add_argument("--level", help="ชั้นเดียว (ไม่ใส่ = ทุกชั้นที่มี)")
    ap.add_argument("--levels", default="", help="กำหนดชั้นให้ใช้ (ไม่บันทึกลงโมเดล) เช่น \"L1:ชั้น 1:0:3\"")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    book = store.read_book(a.model)
    if a.levels:
        _merge_levels(book, a.levels)
    if not book["levels"]:
        raise ValueError("ยังไม่มีชั้น — ใส่ --levels \"L1:ชั้น 1:0:3\" หรือ room-import ก่อน")
    scene = _scene(a.model)
    use = [_level_or_fail(book, a.level)] if a.level else sorted(book["levels"], key=lambda v: v["z0"])
    results, text = [], []
    for lv in use:
        res = suggest.propose(scene, book, lv)
        results.append(res)
        text.append(f"{lv['id']}: ปิดประตู {res['doors_shut']} ก้อน · เปิดประตูใน {res['doors_open']} ก้อน")
        for p in res["proposals"]:
            text.append(f"  {p['id']} {p['area_m2']:.1f} ตร.ม." + (f" — {'; '.join(p['notes'])}" if p["notes"] else ""))
    out = results[0] if len(results) == 1 else {"v": 1, "kind": "room-suggest-set", "sets": results}
    if len(results) > 1:        # one proposal file per level keeps room-import simple
        paths = []
        for res in results:
            pth = a.out.with_name(f"{a.out.stem}-{res['level']['id']}{a.out.suffix}")
            pth.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
            paths.append(str(pth))
        return {"proposal_files": paths, "text": text, "model_changed": False}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"proposal_file": str(a.out), "text": text, "model_changed": False,
            "next": "ตั้ง name/kind แล้วเปลี่ยน confirmed เป็น true → room-import --from-suggest"}


def cmd_remove(argv):
    ap = argparse.ArgumentParser(prog="room-remove")
    ap.add_argument("model", type=Path)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--id")
    g.add_argument("--name")
    ap.add_argument("--level")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    book = store.read_book(a.model)
    lv = _level_or_fail(book, a.level) if a.level else None
    hits = [r for r in book["rooms"]
            if (r.get("id") == a.id if a.id else r.get("name") == a.name)
            and (lv is None or r.get("level") == lv["id"])]
    if not hits:
        raise ValueError("ไม่พบป้ายห้องที่ระบุ")
    if len(hits) > 1:
        raise ValueError("ตรงหลายห้อง: " + ", ".join(f"{r['id']} ({r['level']})" for r in hits) + " — ระบุ --id หรือ --level")
    book["rooms"].remove(hits[0])
    rep = _save(book, a.model, a.out)
    rep.update({"removed": f"{hits[0]['id']} {hits[0]['name']}", "rooms_total": len(book["rooms"])})
    return rep


def _scene(path):
    return __import__("yotathai.rooms.model", fromlist=["load_scene"]).load_scene(path)
