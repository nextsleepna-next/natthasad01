# SPDX-License-Identifier: GPL-3.0-or-later
"""Where room labels live: ``plugin_data["yotathai_rooms"]`` of an .igz model.

Two ways in, one data shape:

* **in the app / in a loaded scene** — :func:`book_of_scene` /
  :func:`set_book_on_scene` (the second goes through ``SetPluginDataCommand``,
  so it is undoable);
* **on a file** (the command line, no engine loaded) — :func:`read_book` /
  :func:`write_book` patch only ``scene.plugin_data`` of the document and
  leave every other byte of the model alone (a plain-JSON model is rewritten
  with the engine's own formatting; a container model is re-zipped with every
  other member copied as it was).

Shape (v1)::

    {"v": 1,
     "levels": [{"id": "L1", "name": "ชั้น 1", "z0": 0.0, "z1": 3.0}],
     "rooms":  [{"id": "r01", "name": "...", "kind": "living", "level": "L1",
                 "poly": [[x, y], ...], "color": null, "src": "design.json",
                 "confirmed": true, "note": ""}]}

A label counts only when ``confirmed`` is true. ``src`` says where it came
from: ``design.json`` / ``user`` / ``ai`` / ``suggest`` (a suggestion a person
or an AI has named and confirmed — never a silent guess).
"""
from __future__ import annotations

import copy
import json
import os
import re
import zipfile
from pathlib import Path

KEY = "yotathai_rooms"
VERSION = 1
SOURCES = ("design.json", "user", "ai", "suggest")
_ZIP_MAGIC = b"PK\x03\x04"
_DOC_ENTRY = "document.json"


def empty_book() -> dict:
    return {"v": VERSION, "levels": [], "rooms": []}


def normalize(raw) -> dict:
    """A book from whatever is stored (None -> empty). Unknown keys are kept."""
    if raw in (None, {}):
        return empty_book()
    if not isinstance(raw, dict):
        raise ValueError("ป้ายห้องในไฟล์ผิดรูปแบบ (ไม่ใช่ออบเจ็กต์)")
    book = copy.deepcopy(raw)
    if int(book.get("v", 1)) > VERSION:
        raise ValueError(f"ป้ายห้องรุ่น v{book.get('v')} ใหม่กว่าโปรแกรมนี้ (รองรับ v{VERSION})")
    book.setdefault("v", VERSION)
    if not isinstance(book.get("levels"), list):
        book["levels"] = []
    if not isinstance(book.get("rooms"), list):
        book["rooms"] = []
    for r in book["rooms"]:
        if isinstance(r, dict):
            r.setdefault("confirmed", True)
    return book


# --- levels ---------------------------------------------------------------

def level_of(book: dict, ref):
    """The level dict for ``ref`` — an id ("L2"), a number ("2" -> "L2") or a
    name ("ชั้น 2"); ``None`` if there is no such level."""
    if ref is None:
        return None
    s = str(ref).strip()
    for lv in book["levels"]:
        if lv["id"] == s or lv.get("name") == s:
            return lv
    if re.fullmatch(r"\d+", s):
        for lv in book["levels"]:
            if lv["id"] == f"L{int(s)}":
                return lv
    return None


def level_for_cut(book: dict, cut_z: float):
    """The level whose z-range holds a plan cut (z0 <= cut < z1), or None."""
    for lv in sorted(book["levels"], key=lambda v: v["z0"]):
        if lv["z0"] - 1e-9 <= cut_z < lv["z1"] - 1e-9:
            return lv
    return None


def parse_levels(text: str) -> list:
    """``"L1:ชั้น 1:0:3,L2:ชั้น 2:3:6"`` -> level dicts."""
    out = []
    for chunk in [c for c in text.split(",") if c.strip()]:
        parts = [p.strip() for p in chunk.split(":")]
        if len(parts) != 4:
            raise ValueError("--levels ต้องเป็น รหัส:ชื่อ:z0:z1 คั่นด้วยจุลภาค เช่น L1:ชั้น 1:0:3,L2:ชั้น 2:3:6")
        out.append({"id": parts[0], "name": parts[1], "z0": float(parts[2]), "z1": float(parts[3])})
    return out


def next_id(book: dict) -> str:
    used = {r.get("id") for r in book["rooms"]}
    n = 1
    while f"r{n:02d}" in used:
        n += 1
    return f"r{n:02d}"


# --- scene (in the app) ----------------------------------------------------

def book_of_scene(scene) -> dict:
    return normalize(getattr(scene, "plugin_data", {}).get(KEY))


def set_book_on_scene(scene, book: dict, history=None) -> None:
    """Store ``book`` in the scene; undoable (``history.execute`` when given)."""
    from core.history import SetPluginDataCommand
    cmd = SetPluginDataCommand(KEY, book if (book["rooms"] or book["levels"]) else None)
    if history is not None:
        history.execute(cmd)
    else:
        cmd.do(scene)


# --- file (the command line) -----------------------------------------------

def _read_document(path: Path):
    """``(data, style, zip_members)`` — style is "indent"/"compact" for the
    JSON text; zip_members is None for a plain-JSON model."""
    raw = Path(path).read_bytes()
    if raw.startswith(_ZIP_MAGIC):
        with zipfile.ZipFile(path) as zf:
            members = [(zi, zf.read(zi)) for zi in zf.infolist()]
        doc = next((b for zi, b in members if zi.filename == _DOC_ENTRY), None)
        if doc is None:
            raise ValueError(f"{Path(path).name} ไม่ใช่ไฟล์โมเดล (ไม่มี {_DOC_ENTRY})")
        text = doc.decode("utf-8")
        return json.loads(text), ("indent" if text[1:2] == "\n" else "compact"), members
    text = raw.decode("utf-8")
    return json.loads(text), ("indent" if text[1:2] == "\n" else "compact"), None


def read_book(path: Path) -> dict:
    data, _style, _members = _read_document(path)
    return normalize((data.get("scene") or {}).get("plugin_data", {}).get(KEY))


def _dump(data, style: str) -> str:
    if style == "compact":
        return json.dumps(data, separators=(",", ":"), allow_nan=False)
    return json.dumps(data, indent=2, allow_nan=False)


def write_book(path: Path, book: dict, out: Path | None = None) -> dict:
    """Write ``book`` into the model at ``path`` (or into the copy ``out``),
    changing nothing else. Returns ``{"file", "reformatted"}`` where
    ``reformatted`` is true if the JSON text of the model was not what the
    engine itself would have written (only the layout of the text changed)."""
    path = Path(path)
    dest = Path(out) if out else path
    data, style, members = _read_document(path)
    scene = data.setdefault("scene", {})
    # does re-dumping the untouched document reproduce it? (informational)
    original_text = (next(b for zi, b in members if zi.filename == _DOC_ENTRY).decode("utf-8")
                     if members is not None else path.read_text(encoding="utf-8"))
    reformatted = _dump(data, style) != original_text
    pd = scene.get("plugin_data")
    if not isinstance(pd, dict):
        pd = {}
    if book["rooms"] or book["levels"]:
        pd[KEY] = book
    else:
        pd.pop(KEY, None)
    if pd:
        scene["plugin_data"] = pd
    else:
        scene.pop("plugin_data", None)
    text = _dump(data, style)
    tmp = dest.with_name(dest.name + ".tmp-rooms")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if members is None:
        tmp.write_bytes(text.encode("utf-8"))
    else:
        with zipfile.ZipFile(tmp, "w") as zout:
            for zi, blob in members:
                payload = text.encode("utf-8") if zi.filename == _DOC_ENTRY else blob
                zout.writestr(zi, payload, compress_type=zi.compress_type)
    os.replace(tmp, dest)
    return {"file": str(dest), "reformatted": reformatted}
