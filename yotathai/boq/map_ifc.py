# SPDX-License-Identifier: GPL-3.0-or-later
"""IFC -> BOQ takeoff table with catalog candidates.

    venv/bin/python -m yotathai.boq.map_ifc MODEL.ifc OUT.csv [--json OUT.json]

Quantities are summed per IFC class. Each class lists the catalog items it could
belong to; the user chooses (the program never picks a material or method).
Classes without a rule, or without the quantity, are reported as unmapped.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from .ifc_qto import read_elements
from .thai_text import fix_thai

HERE = Path(__file__).resolve().parent
CATALOG = HERE.parents[1] / "kit-v2/overlay/knowledge/ref-data/boq-db/boq-catalog.json"


def load_rules() -> dict:
    return json.loads((HERE / "rules.json").read_text(encoding="utf-8"))["classes"]


def load_catalog(path: Path = CATALOG) -> dict[str, dict]:
    """code -> first 'head' item (name repaired)."""
    heads: dict[str, dict] = {}
    for it in json.loads(path.read_text(encoding="utf-8"))["items"]:
        if it["level"] == "head" and it["code"] not in heads:
            heads[it["code"]] = {"code": it["code"], "name": fix_thai(it["name"]).strip()}
    return heads


def takeoff(ifc_path: str | Path) -> dict:
    rules, catalog = load_rules(), load_catalog()
    totals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    unmapped: list[dict] = []
    ignored: dict[str, int] = defaultdict(int)
    skipped: dict[str, int] = defaultdict(int)
    warned: dict[str, int] = defaultdict(int)
    for e in read_elements(ifc_path):
        rule = rules.get(e["ifc_class"])
        if rule and "ignore" in rule:
            ignored[e["ifc_class"]] += 1
            continue
        if not rule:
            unmapped.append({"element": e["name"], "class": e["ifc_class"],
                             "reason": "ไม่มีกฎสำหรับชนิดนี้"})
            continue
        qset, qname = rule["quantity"]
        q = e["qto"].get(qset, {}).get(qname)
        if q is None:
            unmapped.append({"element": e["name"], "class": e["ifc_class"],
                             "reason": f"ไม่มีปริมาณ {qset}/{qname}"})
            continue
        if q[1] < rule.get("skip_piece_under_m", 0.0):
            skipped[e["ifc_class"]] += 1
            continue
        width = e["qto"].get(qset, {}).get("Width")
        if width and width[1] > rule.get("warn_width_over_m", float("inf")):
            warned[e["ifc_class"]] += 1
        totals[e["ifc_class"]] += 1.0 if rule.get("measure") == "count" else q[1]
        counts[e["ifc_class"]] += 1
    rows = []
    for cls, total in sorted(totals.items()):
        rule = rules[cls]
        rows.append({
            "ifc_class": cls, "count": counts[cls], "quantity": round(total, 3),
            "unit": rule["unit"], "choice_required": rule["choice"],
            "candidates": [catalog[c] if c in catalog else {"code": c, "name": "?"}
                           for c in rule["candidates"]],
            "skipped": skipped.get(cls, 0),
            "warnings": [m for m in (
                f"{warned[cls]} ชิ้น: {rule['warn_width_msg']}" if warned.get(cls) else "",
                f"ข้าม {skipped[cls]} ชิ้น: {rule['skip_piece_msg']}" if skipped.get(cls) else "",
                rule.get("warn_msg", "")) if m],
        })
    return {"rows": rows, "unmapped": unmapped,
            "ignored": [{"class": c, "count": n, "reason": rules[c]["ignore"]}
                        for c, n in sorted(ignored.items())]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ifc", type=Path)
    ap.add_argument("csv", type=Path)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    res = takeoff(a.ifc)
    with a.csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["ชนิด IFC", "จำนวนชิ้น", "ปริมาณ", "หน่วย", "ต้องเลือก", "รายการที่เป็นไปได้ (รหัส ชื่อ)", "คำเตือน"])
        for r in res["rows"]:
            w.writerow([r["ifc_class"], r["count"], r["quantity"], r["unit"], r["choice_required"],
                        " | ".join(f"{c['code']} {c['name']}" for c in r["candidates"]),
                        " ; ".join(r["warnings"])])
    if a.json:
        a.json.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"rows: {len(res['rows'])}  unmapped: {len(res['unmapped'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
