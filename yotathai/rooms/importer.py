# SPDX-License-Identifier: GPL-3.0-or-later
"""Room labels from a project's ``design.json`` (the spec the AI built the model from).

Accepted shapes of ``design["rooms"]``:

* ``{"gf": [[name, x0, y0, x1, y1], ...], "uf": [...]}`` — one list per storey
  (levels come out in that order; storey height from ``design["levels"]["storey_h"]``);
* ``[[name, x0, y0, x1, y1], ...]`` — one storey (floor at ``design["G"]``,
  top at ``design["plate"]``);
* a list of objects ``{"name", "x0","y0","x1","y1" | "poly", "kind"?, "floor"?}``.

The kind comes from the entry, from ``kind_map`` (name -> kind) or from the
name's keyword (``kinds.json``). A name none of these decide is an error,
never a default: the colour must be a decision, not a guess.
"""
from __future__ import annotations

from . import geometry as geo
from . import kinds


def _entry(raw):
    """(name, poly, kind|None, floor|None) of one design.json room entry."""
    if isinstance(raw, dict):
        name = raw.get("name") or raw.get("th") or ""
        if raw.get("poly"):
            poly = [tuple(p) for p in raw["poly"]]
        else:
            poly = geo.rect(raw["x0"], raw["y0"], raw["x1"], raw["y1"])
        return name, poly, raw.get("kind"), raw.get("floor", raw.get("level"))
    name, x0, y0, x1, y1 = raw[:5]
    return name, geo.rect(x0, y0, x1, y1), None, None


def rooms_from_design(design: dict, kind_map: dict | None = None, levels: list | None = None):
    """``(levels, rooms, notes)`` — rooms without ids (the book assigns them)."""
    kind_map = kind_map or {}
    raw = design.get("rooms")
    if not raw:
        raise ValueError("design.json ไม่มี rooms")
    groups = []     # [(level key, [entries])]
    if isinstance(raw, dict):
        groups = [(k, v) for k, v in raw.items()]
    else:
        floors = []
        for e in raw:
            fl = _entry(e)[3]
            if fl not in floors:
                floors.append(fl)
        if len(floors) > 1 or (len(floors) == 1 and floors[0] is not None):
            groups = [(fl, [e for e in raw if _entry(e)[3] == fl]) for fl in floors]
        else:
            groups = [(None, raw)]

    notes = []
    if levels is None:
        levels = []
        storey = (design.get("levels") or {}).get("storey_h") if isinstance(design.get("levels"), dict) else None
        for i, (key, _entries) in enumerate(groups):
            if len(groups) == 1 and not storey:
                z0 = float(design.get("G", 0.0))
                if "plate" in design:
                    z1 = float(design["plate"])
                elif "wall_h" in design:
                    z1 = z0 + float(design.get("FFL", 0.0)) + float(design["wall_h"])
                else:
                    raise ValueError("design.json ไม่บอกระดับชั้น — ใส่ --levels L1:ชั้น 1:0:3")
            elif storey:
                z0, z1 = i * float(storey), (i + 1) * float(storey)
            else:
                raise ValueError("design.json ไม่บอกความสูงชั้น — ใส่ --levels L1:ชั้น 1:0:3,L2:ชั้น 2:3:6")
            levels.append({"id": f"L{i + 1}", "name": f"ชั้น {i + 1}", "z0": z0, "z1": z1})
            notes.append(f"{levels[-1]['id']} ← {key if key is not None else 'rooms'} (z {z0:g}..{z1:g} ม.)")
    if len(levels) != len(groups):
        raise ValueError(f"design.json มี {len(groups)} ชั้น แต่ --levels ให้มา {len(levels)} ชั้น")

    rooms, unresolved = [], []
    for (key, entries), lv in zip(groups, levels):
        for e in entries:
            name, poly, kind, _fl = _entry(e)
            if not kind:
                kind = kind_map.get(name) or kinds.guess_kind(name)
            if not kind:
                unresolved.append(name)
                continue
            if not kinds.has_kind(kind):
                raise ValueError(f"ชนิดห้อง {kind!r} ของ {name!r} ไม่อยู่ใน kinds.json")
            rooms.append({"name": name, "kind": kind, "level": lv["id"], "poly": [list(p) for p in geo.ccw(poly)],
                          "color": None, "src": "design.json", "confirmed": True, "note": ""})
    if unresolved:
        raise ValueError("ชื่อห้องที่ยังตัดสินชนิดไม่ได้: " + ", ".join(sorted(set(unresolved)))
                         + " — ใส่ --kinds แผนที่.json ({\"ชื่อห้อง\": \"ชนิด\"}) · ชนิดที่มี: "
                         + ", ".join(kinds.kinds()))
    return levels, rooms, notes
