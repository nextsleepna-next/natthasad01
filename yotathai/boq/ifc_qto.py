# SPDX-License-Identifier: GPL-3.0-or-later
"""Read elements and Qto_* quantities from an IFC4 STEP file (no ifcopenshell)."""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

_ENT = re.compile(r"#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)\)\s*;\s*$", re.S)
_X2 = re.compile(r"\\X2\\([0-9A-Fa-f]+)\\X0\\")
_REF = re.compile(r"#(\d+)")


def _decode(s: str) -> str:
    s = _X2.sub(lambda m: "".join(
        chr(int(m.group(1)[i:i + 4], 16)) for i in range(0, len(m.group(1)), 4)), s)
    return s.replace("''", "'")


def _split_args(body: str) -> list[str]:
    out, depth, cur, quote = [], 0, [], False
    i = 0
    while i < len(body):
        ch = body[i]
        if quote:
            cur.append(ch)
            if ch == "'":
                if i + 1 < len(body) and body[i + 1] == "'":
                    cur.append("'")
                    i += 1
                else:
                    quote = False
        elif ch == "'":
            quote = True
            cur.append(ch)
        elif ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
        i += 1
    out.append("".join(cur).strip())
    return out


def _str(arg: str) -> str:
    arg = arg.strip()
    return _decode(arg[1:-1]) if arg.startswith("'") and arg.endswith("'") else ""


def read_elements(path: str | Path) -> list[dict]:
    """Return [{id, ifc_class, name, qto: {set: {quantity: (kind, value)}}}]."""
    text = Path(path).read_text(encoding="ascii", errors="replace")
    ents: dict[int, tuple[str, list[str]]] = {}
    for stmt in re.split(r";\s*\n", text):
        m = _ENT.match(stmt.strip() + ";")
        if m:
            ents[int(m.group(1))] = (m.group(2), _split_args(m.group(3)))

    quantities: dict[int, tuple[str, str, float]] = {}
    qkind = {"IFCQUANTITYLENGTH": "length", "IFCQUANTITYAREA": "area",
             "IFCQUANTITYVOLUME": "volume", "IFCQUANTITYCOUNT": "count",
             "IFCQUANTITYWEIGHT": "weight"}
    for eid, (name, a) in ents.items():
        if name in qkind and len(a) >= 4:
            quantities[eid] = (qkind[name], _str(a[0]), float(a[3]))

    qsets: dict[int, tuple[str, dict]] = {}
    for eid, (name, a) in ents.items():
        if name == "IFCELEMENTQUANTITY" and len(a) >= 6:
            qs = {}
            for r in _REF.findall(a[5]):
                q = quantities.get(int(r))
                if q:
                    qs[q[1]] = (q[0], q[2])
            qsets[eid] = (_str(a[2]), qs)

    by_elem: dict[int, dict] = defaultdict(dict)
    for _eid, (name, a) in ents.items():
        if name == "IFCRELDEFINESBYPROPERTIES" and len(a) >= 6:
            ref = _REF.search(a[5])
            if ref and int(ref.group(1)) in qsets:
                set_name, qs = qsets[int(ref.group(1))]
                for e in _REF.findall(a[4]):
                    by_elem[int(e)][set_name] = qs

    out = []
    for eid, qto in sorted(by_elem.items()):
        name, a = ents[eid]
        out.append({"id": eid, "ifc_class": _ifc_class(name),
                    "name": _str(a[2]) if len(a) > 2 else "", "qto": qto})
    return out


def _ifc_class(upper: str) -> str:
    # IFCWALL -> IfcWall (class names the exporter writes are all single words)
    from_known = {"IFCWALL": "IfcWall", "IFCSLAB": "IfcSlab", "IFCCOLUMN": "IfcColumn",
                  "IFCBEAM": "IfcBeam", "IFCFOOTING": "IfcFooting", "IFCROOF": "IfcRoof",
                  "IFCSTAIR": "IfcStair", "IFCRAMP": "IfcRamp", "IFCDOOR": "IfcDoor",
                  "IFCWINDOW": "IfcWindow", "IFCRAILING": "IfcRailing",
                  "IFCCOVERING": "IfcCovering", "IFCPILE": "IfcPile",
                  "IFCMEMBER": "IfcMember", "IFCSPACE": "IfcSpace",
                  "IFCBUILDINGELEMENTPROXY": "IfcBuildingElementProxy"}
    return from_known.get(upper, upper)
