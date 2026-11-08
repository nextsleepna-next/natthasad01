# SPDX-License-Identifier: GPL-3.0-or-later
"""Which rooms get which colour on a plan cut at height z — for any sheet
writer (``model-to-2d --room-fill`` and the project sheet scripts alike).

    from yotathai.rooms import fill, store
    book = store.read_book("model.igz")
    plan = fill.room_fills(book, cut_z=1.2, mode="presentation")
    for f in plan["fills"]:                       # f["poly"], f["rgb"], f["name"], ...
        sheet.fill(f["poly"], f["rgb"])

Only confirmed labels with a kind that has a colour are returned; the rest
come back in ``skipped`` with the reason. A room without walls (pavilion,
deck, balcony) is filled from its own ``poly`` like any other.
"""
from __future__ import annotations

from . import geometry as geo
from . import kinds, store


def room_fills(book: dict, cut_z: float | None = None, level=None,
               mode: str = "presentation") -> dict:
    """``{"level": level dict or None, "fills": [...], "skipped": [...]}``.

    The level is ``level`` (id/number/name) or the one holding ``cut_z``."""
    if mode not in kinds.MODES:
        raise ValueError(f"mode must be one of {', '.join(kinds.MODES)}")
    lv = store.level_of(book, level) if level is not None else \
        (store.level_for_cut(book, cut_z) if cut_z is not None else None)
    out = {"level": lv, "fills": [], "skipped": []}
    if lv is None:
        return out
    for r in book["rooms"]:
        if r.get("level") != lv["id"]:
            continue
        rid = r.get("id")
        if not r.get("confirmed", True):
            out["skipped"].append({"id": rid, "name": r.get("name"), "reason": "unconfirmed"})
            continue
        poly = geo.dedupe(r.get("poly") or [])
        if len(poly) < 3 or geo.area(poly) <= 0:
            out["skipped"].append({"id": rid, "name": r.get("name"), "reason": "bad-poly"})
            continue
        key = r.get("kind")
        if not r.get("color") and not kinds.has_kind(key):
            out["skipped"].append({"id": rid, "name": r.get("name"), "reason": "unknown-kind"})
            continue
        rgb = kinds.room_rgb(r, mode)
        if rgb is None:
            out["skipped"].append({"id": rid, "name": r.get("name"), "reason": "no-fill-kind"})
            continue
        out["fills"].append({
            "id": rid, "name": r.get("name", ""), "kind": key, "poly": geo.ccw(poly),
            "rgb": rgb, "area": geo.area(poly),
            "legend": kinds.legend_group(key) if kinds.has_kind(key) else (r.get("name") or key),
            "legend_kind": kinds.legend_kind(key) if kinds.has_kind(key) else (r.get("name") or key),
            "aci": kinds.group_aci(kinds.legend_group(key), mode) if (kinds.has_kind(key) and not r.get("color"))
            else kinds.nearest_aci(rgb),
            "legend_short": kinds.legend_short(key) if kinds.has_kind(key) else (r.get("name") or key),
            "kind_order": kinds.kind_order(key) if kinds.has_kind(key) else 999,
        })
    return out
