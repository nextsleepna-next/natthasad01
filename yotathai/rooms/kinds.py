# SPDX-License-Identifier: GPL-3.0-or-later
"""Room kind -> colour table (``kinds.json``), the one table for the whole system.

Flat technical colour only (SOLID, no pattern, no gradient, no watercolour
or wood effect), pastel (luminance >= 0.75). Two tints are derived from it:

* ``presentation`` — the table colour as it is (clear pastel);
* ``construction`` — the same colour mixed 12% with white, so the fill
  stays behind the lines of a construction sheet.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

MODES = ("presentation", "construction")
#: share of white mixed into the colour for a construction sheet
CONSTRUCTION_WHITE = 0.12


@lru_cache(maxsize=1)
def _table() -> dict:
    return json.loads((Path(__file__).with_name("kinds.json")).read_text(encoding="utf-8"))


def kinds() -> dict:
    return _table()["kinds"]


def has_kind(key: str) -> bool:
    return key in kinds()


def kind_th(key: str) -> str:
    return kinds()[key]["th"]


def legend_group(key: str) -> str:
    k = kinds()[key]
    return k.get("group", k["th"])


def legend_kind(key: str) -> str:
    """The name of a kind's legend row when it is the only kind of its group on
    the sheet: its own name, except where the table says otherwise (the living
    space of an open plan is always "นั่งเล่น / รับประทานอาหาร")."""
    k = kinds()[key]
    return k.get("legend_alone", k["th"])


def legend_short(key: str) -> str:
    """Short name of a kind for a legend row that names several kinds of one
    group ("ศาลา / ชาน"): only the kinds really on the sheet are named."""
    k = kinds()[key]
    return k.get("legend_short", k["th"])


def kind_order(key: str) -> int:
    return list(kinds()).index(key)


def group_order() -> list:
    """Legend groups in the fixed order of the table (rows of a legend follow it)."""
    out = []
    for k in kinds().values():
        g = k.get("group", k["th"])
        if g not in out:
            out.append(g)
    return out


def is_walled(key: str) -> bool:
    return bool(kinds().get(key, {}).get("walled", True))


def fills(key: str) -> bool:
    k = kinds().get(key)
    return bool(k) and k.get("fill", True) and k.get("rgb") is not None


def luminance(rgb) -> float:
    return 0.30 * rgb[0] + 0.59 * rgb[1] + 0.11 * rgb[2]


def tint(rgb, mode: str) -> tuple:
    """The colour used on a sheet of ``mode`` ("presentation"/"construction")."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}")
    rgb = tuple(float(c) for c in rgb)
    if mode == "construction":
        w = CONSTRUCTION_WHITE
        rgb = tuple(c + (1.0 - c) * w for c in rgb)
    return rgb


def room_rgb(room: dict, mode: str):
    """Colour of one room on a sheet, or None for no fill. A per-room
    ``color`` overrides the kind's colour."""
    own = room.get("color")
    if own:
        return tint(own, mode)
    key = room.get("kind")
    if not fills(key):
        return None
    return tint(kinds()[key]["rgb"], mode)


def guess_kind(name: str):
    """Kind from a Thai room name by keyword (design.json import only) —
    ``None`` when no keyword matches; the caller must then ask, never guess."""
    n = str(name)
    for word, key in _table()["name_keywords"]:
        if word in n:
            return key
    return None


# --- colour difference (to keep colours apart, on screen and on paper) ---------

def lab(rgb) -> tuple:
    """CIE L*a*b* (D65) of an sRGB colour given as 0..1."""
    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(float(c)) for c in rgb)
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e76(a, b) -> float:
    la, lb = lab(a), lab(b)
    return sum((p - q) ** 2 for p, q in zip(la, lb)) ** 0.5


def delta_e2000(c1, c2) -> float:
    """CIEDE2000 (Sharma et al. 2005)."""
    import math
    L1, a1, b1 = lab(c1)
    L2, a2, b2 = lab(c2)
    C1, C2 = math.hypot(a1, b1), math.hypot(a2, b2)
    Cm = (C1 + C2) / 2
    G = 0.5 * (1 - math.sqrt(Cm ** 7 / (Cm ** 7 + 25 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if C1p else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if C2p else 0.0
    dLp, dCp = L2 - L1, C2p - C1p
    if C1p * C2p == 0:
        dhp = 0.0
    else:
        dhp = h2p - h1p
        dhp += -360 if dhp > 180 else (360 if dhp < -180 else 0)
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2))
    Lpm, Cpm = (L1 + L2) / 2, (C1p + C2p) / 2
    if C1p * C2p == 0:
        hpm = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hpm = (h1p + h2p) / 2
    else:
        hpm = (h1p + h2p + 360) / 2 if h1p + h2p < 360 else (h1p + h2p - 360) / 2
    T = (1 - 0.17 * math.cos(math.radians(hpm - 30)) + 0.24 * math.cos(math.radians(2 * hpm))
         + 0.32 * math.cos(math.radians(3 * hpm + 6)) - 0.20 * math.cos(math.radians(4 * hpm - 63)))
    dtheta = 30 * math.exp(-(((hpm - 275) / 25) ** 2))
    Rc = 2 * math.sqrt(Cpm ** 7 / (Cpm ** 7 + 25 ** 7))
    Sl = 1 + 0.015 * (Lpm - 50) ** 2 / math.sqrt(20 + (Lpm - 50) ** 2)
    Sc, Sh = 1 + 0.045 * Cpm, 1 + 0.015 * Cpm * T
    Rt = -math.sin(math.radians(2 * dtheta)) * Rc
    return math.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh))


def delta_e(a, b) -> float:
    """CIE76 ΔE(Lab) — the figure the colour floors below are set in
    (CIEDE2000 is also available, :func:`delta_e2000`, and is reported)."""
    return delta_e76(a, b)


WHITE = (1.0, 1.0, 1.0)
#: every colour at least this far from the paper, and every two colours of a
#: sheet's legend at least this far apart (floor values, both tints)
MIN_DE_PAPER = 8.0
MIN_DE_PAIR = 12.0


#: AutoCAD colour indices that stand for a real colour of their own: 10..249
#: (1..9 are the pure primaries and 7, "white/black by the viewer's
#: background"; 250..255 are greys that read as white on paper)
ACI_RANGE = range(10, 250)
_ACI = []
_ACI_BY = {}


def _aci_table() -> list:
    if not _ACI:
        from ezdxf import colors
        for i in ACI_RANGE:
            r, g, b = colors.int2rgb(colors.DXF_DEFAULT_COLORS[i])
            _ACI.append((i, lab((r / 255, g / 255, b / 255))))
    return _ACI


def nearest_aci(rgb, taken=()) -> int:
    """The standard AutoCAD colour (10..249) nearest to ``rgb`` (0..1) in Lab,
    leaving out the indices in ``taken``. A hatch carries its true colour AND
    this index, so a CAD program that ignores true colour still shows a
    nearby colour — not white or black."""
    want = lab(rgb)
    best = min((t for t in _aci_table() if t[0] not in taken),
               key=lambda t: sum((p - q) ** 2 for p, q in zip(t[1], want)))
    return best[0]


def group_aci(group: str, mode: str) -> int:
    """The fallback colour index of a legend row (group) in ``mode``: the
    nearest standard colour not already given to another row, so every row
    of the table has an index of its own — the same on every sheet."""
    if mode not in _ACI_BY:
        taken, out = set(), {}
        for g in group_order():
            kind = next(k for k, v in kinds().items() if v.get("group", v["th"]) == g)
            if not fills(kind):
                continue
            out[g] = nearest_aci(tint(kinds()[kind]["rgb"], mode), taken)
            taken.add(out[g])
        _ACI_BY[mode] = out
    return _ACI_BY[mode][group]


def aci_rgb(index: int) -> tuple:
    from ezdxf import colors
    r, g, b = colors.int2rgb(colors.DXF_DEFAULT_COLORS[index])
    return r / 255, g / 255, b / 255
