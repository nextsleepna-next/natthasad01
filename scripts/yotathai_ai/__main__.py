# SPDX-License-Identifier: GPL-3.0-or-later
"""Yotathai for AI: one door to both engines, no window needed.

    venv/bin/python scripts/yotathai_ai <command> ...            (source tree, Mac/Linux)
    yotathai-ai.bat <command> ...                                (Windows portable package)

  plan-to-3d  PLAN.dxf MODEL.igz [--height 3] [--glb X] [--ifc X] ...
  model-to-2d MODEL.igz SHEET.dxf [--cuts 1.2,4.2] [--no-roof] [--room-fill off|presentation|construction] ...
  room-import MODEL.igz --design design.json | --from-suggest proposals.json   room labels into the model (name, kind, level, outline)
  room-add    MODEL.igz --name N --kind K --level 1 (--rect x0,y0,x1,y1 | --poly "x,y;.." | --at x,y --confirm)
  room-list   MODEL.igz [--level 1]                     room-check MODEL.igz [--no-model]
  room-suggest MODEL.igz --out proposals.json           proposes enclosed spaces from the walls; needs a name + confirmation, never used silently
  room-remove MODEL.igz (--id r03 | --name N [--level 1])
  build-3d    RECIPE.py MODEL.igz [--glb X] [--ifc X]   recipe uses house()/wall()/extrude()...
  draw-2d     SCRIPT.py DRAWING.dxf                     script gets doc, msp (ezdxf, metres)
  to-dwg      DRAWING.dxf DRAWING.dwg                   writes AutoCAD R2000 through LibreDWG
  calc-beam   JOB.json [--out X] [--steps]              RC beams by SDM (needs the ytstruct pack)
  calc-rc     list | FUNC JOB.json [--out X]            any RC-Design engine function (wind, seismic, column, slab, footing, frame...)
  calc-building SPEC.json --out JOB [--steps 10]        grid building, 1–10+ storeys: site criteria, 3D frame (seismic + wind),
                                                        SDM beams/columns/joints, sizes grown until all pass, then foundations
  calc-foundation JOB [--soil SOIL.json]                footings / pile caps from a designed JOB's base forces, every soil case
  job-building PROJECT [--spec SPEC.json] [--skip-sheets]  grid building in a job-new project: calc, foundations, slabs, stairs,
                                                        structural sheets, BOQ + ราคากลาง ปร.1-4, duration, installments
  road-section / road-takeoff / road-sheets  --surface S --cbr N --adt N|--trucks10 N [--width M --length M ...]
                                                        local-road standard sections (อปท. 2556): layers, quantities, 2D cross-section sheet
                                                        (needs the road skill pack ytstruct/infra — separate pack, not in the free program)
  job-new     SLUG --province X [--amphoe Y] [--name-th ..] [--dest D]  new project, site wind/seismic filled in
  job-run     PROJECT [--from N] [--only x,y] [--list]  whole chain: model, calc, drawings A/S/MEP, permit book,
                                                        BOQ + ราคากลาง ปร.1-4, duration, installments, S-curve
  open        FILE                                      show it in the Yotathai app (reuses the window that has it)
  find-work   [--days N] [--all] [FOLDER ...]           list your drawings/models (.igz .dxf .dwg .skp) newest first: finds work from older versions
  recipes                                               the 3D helper reference
  check                                                 both engines + converters OK?

Every command prints a one-line JSON report with --json (else key: value).
See README.md beside this file.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Source tree: <root>/scripts/yotathai_ai ; portable/installed package: <app>/yotathai_ai
# (the folder that holds the ``yotathai`` package, ``src`` and ``ingecad-src``).
ROOT = HERE.parent if (HERE.parent / "yotathai").is_dir() else HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yotathai.convert._common import run, save_model, use_3d_engine  # noqa: E402



DWG_VERSIONS = {"2000": "2000", "2004": "2004", "2007": "2007", "2010": "2010",
                "2013": "2013", "2018": "2018"}


def cmd_plan_to_3d(argv):
    from yotathai.convert import plan_to_model
    return plan_to_model.main(argv)


def cmd_model_to_2d(argv):
    from yotathai.convert import views_to_dxf
    return views_to_dxf.main(argv)


def cmd_room_import(argv):
    from yotathai.rooms import cli
    return cli.cmd_import(argv)


def cmd_room_add(argv):
    from yotathai.rooms import cli
    return cli.cmd_add(argv)


def cmd_room_list(argv):
    from yotathai.rooms import cli
    return cli.cmd_list(argv)


def cmd_room_check(argv):
    from yotathai.rooms import cli
    return cli.cmd_check(argv)


def cmd_room_suggest(argv):
    from yotathai.rooms import cli
    return cli.cmd_suggest(argv)


def cmd_room_remove(argv):
    from yotathai.rooms import cli
    return cli.cmd_remove(argv)


def cmd_build_3d(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="build-3d")
    ap.add_argument("recipe", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--glb", type=Path)
    ap.add_argument("--ifc", type=Path)
    a = ap.parse_args(argv)
    use_3d_engine()
    from core.ai import _recipe_helpers
    from core.scene import Scene
    scene = Scene()
    from core import bim
    ns = dict(_recipe_helpers(scene))
    # tag(group, "IfcWall", "ผนัง 1") makes a piece exportable to IFC.
    ns.update({"scene": scene, "bim": bim, "tag": bim.tag_group,
               "__name__": "__recipe__"})
    exec(compile(a.recipe.read_text(encoding="utf-8-sig"), str(a.recipe), "exec"), ns)
    save_model(scene, a.out, a.glb)
    report = {"model": str(a.out), "groups": len(scene.groups)}
    if a.ifc:
        from formats.ifc import save_ifc
        try:
            report["ifc_elements"] = save_ifc(scene, a.ifc, project_name=a.out.stem)
        except ValueError as exc:            # nothing tagged
            report["ifc_error"] = str(exc)
    return report


def cmd_draw_2d(argv):
    import argparse

    import ezdxf
    ap = argparse.ArgumentParser(prog="draw-2d")
    ap.add_argument("script", type=Path)
    ap.add_argument("out", type=Path)
    a = ap.parse_args(argv)
    doc = ezdxf.new("R2018", setup=True)
    doc.units = ezdxf.units.M
    doc.header["$INSUNITS"] = 6
    doc.header["$MEASUREMENT"] = 1
    # Thai text styles by font NAME only — never copy a font file.
    doc.styles.add("TH", font="Tahoma.ttf")
    # Free fonts that ship with the portable package (looked up by file name; the app registers them).
    doc.styles.add("TH-DRAFT", font="YotathaiDrafting-Regular.ttf")
    doc.styles.add("TH-KANIT", font="Kanit-Regular.ttf")
    doc.styles.add("TH-SARABUN", font="Sarabun-Regular.ttf")
    msp = doc.modelspace()
    ns = {"doc": doc, "msp": msp, "ezdxf": ezdxf, "__name__": "__drawing__"}
    exec(compile(a.script.read_text(encoding="utf-8-sig"), str(a.script), "exec"), ns)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(a.out)
    return {"drawing": str(a.out), "entities": len(msp),
            "layers": sorted(ly.dxf.name for ly in doc.layers)}


def cmd_to_dwg(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="to-dwg")
    ap.add_argument("dxf", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--version", default="2000", choices=sorted(DWG_VERSIONS))
    a = ap.parse_args(argv)
    # LibreDWG's dxf2dwg shipped with the program (writes AutoCAD r2000)
    from yotathai.paths import SRC_2D
    if str(SRC_2D) not in sys.path:
        sys.path.insert(0, str(SRC_2D))
    from formats.dwg_bridge import DwgBridgeError, find_dxf2dwg, write_dwg
    if find_dxf2dwg() is None:
        raise RuntimeError("DWG writing needs a converter: LibreDWG (dxf2dwg) was not found next to the program "
                           "and on PATH. Save DXF instead.")
    import shutil
    import tempfile

    import ezdxf
    from core.encoding import write_dwg_intermediate
    # same pipeline as File > Save as DWG in the 2D program: R2000 intermediate with every group
    # written out, and Thai/accented text escaped as \\U+xxxx so AutoCAD shows it correctly
    doc = ezdxf.readfile(a.dxf)
    tmp = Path(tempfile.mkdtemp(prefix="yotathai-to-dwg-"))
    try:
        write_dwg_intermediate(doc, tmp / "out.dxf")
        warnings = write_dwg(tmp / "out.dxf", a.out)
    except DwgBridgeError as exc:
        raise RuntimeError(str(exc)) from exc
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if not a.out.exists():
        raise RuntimeError("LibreDWG did not write the DWG")
    return {"dwg": str(a.out), "version": "2000", "engine": "libredwg", "bytes": a.out.stat().st_size,
            **({"warnings": warnings} if warnings else {}),
            **({"note": f"LibreDWG writes AutoCAD R2000 only; asked for {a.version}"}
               if a.version != "2000" else {})}


def _run_pack(sub, argv, keep=0):
    """Structural pack (ytstruct, kept apart from this GPL shell): run it as its own program."""
    import json
    import subprocess
    if not (ROOT / "ytstruct" / "cli.py").exists():
        raise RuntimeError("the structural calculation pack (ytstruct) is not installed here")
    # the pack runs from ROOT: make the job file and --out absolute against the caller's folder
    # (the first `keep` words, e.g. a function name, are passed through as they are)
    args, prev = list(argv[:keep]), ""
    for a in argv[keep:]:
        args.append(str(Path(a).resolve()) if (not a.startswith("-") and prev in ("", "--out", "--soil", "--spec")) else a)
        prev = a if a.startswith("-") else ""
    proc = subprocess.run([sys.executable, "-m", "ytstruct", *sub, *args, "--json"], cwd=str(ROOT),
                          capture_output=True, text=True, encoding="utf-8")
    lines = proc.stdout.strip().splitlines()
    try:
        last = json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError):
        raise RuntimeError((proc.stderr or proc.stdout).strip()[-800:]) from None
    if not last.pop("ok", False):
        raise RuntimeError(last.get("error", "ytstruct failed"))
    return last


def cmd_calc_beam(argv):
    return _run_pack(["beam"], argv)


def cmd_calc_building(argv):
    return _run_pack(["building"], argv)


def cmd_job_building(argv):
    return _run_pack(["job-building"], argv)


def cmd_calc_foundation(argv):
    return _run_pack(["foundation"], argv)


def cmd_calc_rc(argv):
    """Any function of the RC-Design engine: `calc-rc list [--filter X]` or `calc-rc FUNC JOB.json`."""
    if argv[:1] == ["list"]:
        return _run_pack(["rc", "list"], argv[1:])
    return _run_pack(["rc", "call"], argv, keep=1)


def _kit() -> Path:
    """The AI-BIM work kit (template + reference data): env YOTATHAI_KIT, else ~/Yotathai_Pro/Yotathai-AI-BIM."""
    for c in (os.environ.get("YOTATHAI_KIT"), Path.home() / "Yotathai_Pro" / "Yotathai-AI-BIM",
              ROOT.parent / "Yotathai-AI-BIM"):
        if c and (Path(c) / "tools" / "template" / "run_all.py").exists():
            return Path(c)
    raise RuntimeError("work kit not found: set YOTATHAI_KIT to the Yotathai-AI-BIM folder")


def _kit_fonts(project: Path) -> None:
    """Documents need Sarabun/Kanit (OFL): copy the kit's copies into the project's fonts/ if missing."""
    import shutil
    src = _kit() / "tools" / "app" / "fonts"
    dst = project / "fonts"
    dst.mkdir(exist_ok=True)
    for f in list(src.glob("Sarabun*.ttf")) + list(src.glob("Kanit*.ttf")):
        if not (dst / f.name).exists():
            shutil.copy2(f, dst / f.name)


def cmd_job_new(argv):
    """New project from the kit template: job-new SLUG --province X [--name-th ...] [--owner ...] [--dest DIR]."""
    import subprocess
    if not argv or argv[0].startswith("-"):
        raise RuntimeError("usage: job-new SLUG --province จังหวัด [--name-th ชื่อ] [--owner ชื่อ] [--dest โฟลเดอร์]")
    import json
    kit = _kit()
    args, amphoe = list(argv), ""
    if "--amphoe" in args:
        i = args.index("--amphoe")
        amphoe = args[i + 1]
        del args[i:i + 2]
    if "--dest" in args:
        i = args.index("--dest") + 1
        args[i] = str(Path(args[i]).resolve())
    else:
        args += ["--dest", str(kit / "my-work")]
    proc = subprocess.run([sys.executable, str(kit / "tools" / "new_project.py"), *args, "--engine", str(ROOT)],
                          capture_output=True, text=True, encoding="utf-8")
    if proc.returncode:
        raise RuntimeError((proc.stderr or proc.stdout).strip()[-800:])
    project = Path(args[args.index("--dest") + 1]) / argv[0]
    _kit_fonts(project)
    rep = {"project": str(project), "next": f"edit {project / 'project.json'} then: job-run {project}"}
    # wind / seismic site values from the structural pack's tables (each with its clause), never guessed
    if (ROOT / "ytstruct" / "site_loads.py").exists():
        province = args[args.index("--province") + 1]
        p = subprocess.run([sys.executable, "-m", "ytstruct", "site", province, amphoe, "--json"], cwd=str(ROOT),
                           capture_output=True, text=True, encoding="utf-8")
        site = json.loads(p.stdout.strip().splitlines()[-1])
        if site["ok"]:
            cfg_path = project / "project.json"
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            cfg.setdefault("calc", {}).update(site["calc"])
            cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            rep["site"] = site["calc"]
        else:
            rep["site_todo"] = site["error"]
    return rep


def _run_roadbridge(action, argv):
    """Road/bridge/box-culvert/irrigation pack (ytstruct.roadbridge): price and duration from a JOB.json."""
    import json
    import subprocess
    if not argv or argv[0].startswith("-"):
        raise RuntimeError(f"usage: {action}-road JOB.json [--out ผล.json]  (ดู ytstruct/roadbridge/README.md)")
    args = [str(Path(a).resolve()) if (i == 0 or argv[i - 1] in ("--out", "--xlsx")) else a for i, a in enumerate(argv)]
    proc = subprocess.run([sys.executable, "-m", "ytstruct.roadbridge", action, *args, "--json"], cwd=str(ROOT),
                          capture_output=True, text=True, encoding="utf-8")
    try:
        last = json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        raise RuntimeError((proc.stderr or proc.stdout).strip()[-800:]) from None
    if not last.get("ok"):
        raise RuntimeError(last.get("error", "roadbridge failed"))
    return {"summary": last.get("summary"), "engine": last.get("engine")}


def cmd_price_road(argv):
    """ราคากลางงานทาง/สะพาน/ท่อเหลี่ยม/ชลประทาน: price-road JOB.json [--xlsx out.xlsx] [--out ผล.json]"""
    return _run_roadbridge("price", argv)


def cmd_time_road(argv):
    """ระยะเวลา + งวดงานทาง/สะพาน (คู่มือ อปท. 2566): time-road JOB.json"""
    return _run_roadbridge("time", argv)


_INFRA_STATUS = {"not_specified": "แผ่นไม่กำหนดความหนา", "none": "ไม่มีชั้นนี้", "blank": "แผ่นเว้นว่าง ผู้ออกแบบกำหนด",
                 "not_shown": "แผ่นไม่แสดงชั้นนี้"}


def _infra_layer(l):
    """ชื่อชั้น + ความหนา + ป้าย 🟢/🟡 (ชั้นที่แผ่นระบุ 'ไม่มี' ไม่แสดงเป็น 0.0 ม.)"""
    mark = f" {l['confidence']}" if l.get("confidence") else ""
    if l.get("status") in ("none", "not_specified", "blank", "not_shown") or l.get("thickness_m") is None:
        return f"{l['name']} ({_INFRA_STATUS.get(l.get('status'), l.get('status'))}){mark}"
    return f"{l['name']} {l['thickness_m']} ม.{mark}"


def _run_infra(action, argv):
    """Local-road skill pack (ytstruct.infra, แบบมาตรฐาน อปท. 2556): section / takeoff / sheets as its own program.
    The pack is optional (a separate skill pack): without it this command says so instead of failing obscurely."""
    import json
    import subprocess
    if not (ROOT / "ytstruct" / "infra" / "__main__.py").exists():
        raise RuntimeError("ชุดทักษะถนน อปท. (ytstruct/infra) ไม่ได้ติดตั้งในเครื่องนี้ — เป็นแพ็กแยก ไม่รวมในโปรแกรมฟรี")
    if not argv or argv[0] in ("-h", "--help"):
        raise RuntimeError(f"usage: road-{action} --surface concrete_reinforced|concrete_plain|asphalt_concrete|... --cbr N "
                           "--adt N | --trucks10 N [--variant type1|type2] [--width M --length M] "
                           + ("[--out-dir DIR --pdf --project ชื่อ --site ที่ตั้ง --code RD-01] " if action == "sheets" else "")
                           + "(ดู docs/road-infra-usage-691101.md)")
    args = list(argv)
    if action == "sheets":
        eq = [i for i, a in enumerate(args) if a.startswith("--out-dir=")]
        if eq:
            args[eq[-1]] = "--out-dir=" + str(Path(args[eq[-1]].split("=", 1)[1]).resolve())
        elif "--out-dir" not in args:
            args += ["--out-dir", str(Path.cwd() / "out" / "road-infra")]
        else:
            i = args.index("--out-dir") + 1
            if i < len(args):
                args[i] = str(Path(args[i]).resolve())
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    proc = subprocess.run([sys.executable, "-m", "ytstruct.infra", action, *args], cwd=str(ROOT), env=env,
                          capture_output=True, text=True, encoding="utf-8")
    try:
        last = json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        raise RuntimeError((proc.stderr or proc.stdout).strip()[-800:]) from None
    sec = last.get("section") or {}
    if not last.get("ok"):
        if "error" in last:
            raise RuntimeError(last["error"])
        stops = [f for f in sec.get("flags", []) if f.get("severity") == "stop"]
        raise RuntimeError("ไม่สร้างให้ (ไม่เดาค่า): " + ("; ".join(f"{f['code']}: {f['message']}" for f in stops) or "ไม่มีหน้าตัดที่ใช้ได้"))
    tk = last.get("takeoff")
    all_flags = list(sec.get("flags", [])) + list((tk or {}).get("flags", []))     # ธงของการถอดปริมาณ (เช่น LANES_ASSUMED) ต้องไม่หาย
    rep = {"sheet": sec.get("sheet_code"), "pdf_page": sec.get("sheet_pdf_page"), "confidence": sec.get("confidence"),
           "needs_engineer_review": bool(sec.get("needs_engineer_review")) or any(f.get("severity") in ("review", "stop") for f in all_flags),
           "layers": [_infra_layer(l) for l in sec.get("layers", [])],
           "flags": list(dict.fromkeys(f["code"] for f in all_flags)),
           "flag_notes": [f"{f['code']}: {f['message']}" for f in all_flags if f.get("severity") in ("review", "stop")]}
    if sec.get("alternatives"):
        rep["alternatives"] = list(dict.fromkeys(a.get("sheet_code") or a.get("sheet") or str(a) for a in sec["alternatives"]))
    if tk:
        rep["basis"] = (f"ผิวจราจรกว้าง {tk.get('width_m')} ม. ยาว {tk.get('length_m')} ม. · ชั้นกว้างเท่าผิวจราจร "
                        "ไม่รวมไหล่ทาง/ลาดข้าง")
        rep["takeoff"] = [f"{i['name']}: {i['qty_total']} {i['unit']}" for i in tk.get("items", [])]
        rep["not_included"] = [e["item"] for e in tk.get("excluded", [])]
    sheet = last.get("sheet")
    if sheet:
        rep["files"] = {k: sheet[k] for k in ("dxf", "pdf") if sheet.get(k)}
        rep["scale"] = sheet.get("scale")
        rep["layout_overlaps"] = len(sheet.get("layout_overlaps", []))
    rep["note"] = "แบบมาตรฐาน อปท. 2556 — ใช้ภายในทีม ต้องให้วิศวกรผู้มีหน้าที่ตรวจเทียบแผ่นจริงก่อนใช้ในสัญญา/ยื่นขอ"
    return rep


def cmd_road_section(argv):
    """หน้าตัดชั้นทางตามแบบมาตรฐาน อปท. 2556: road-section --surface S --cbr N --adt N|--trucks10 N [--variant type1|type2]"""
    return _run_infra("section", argv)


def cmd_road_takeoff(argv):
    """ปริมาณงานชั้นทางต่อ กม./สายทาง: road-takeoff --surface S --cbr N --adt N --width M [--length M]"""
    return _run_infra("takeoff", argv)


def cmd_road_sheets(argv):
    """แผ่นรูปตัดโครงสร้างชั้นทาง 2D (DXF [+PDF]): road-sheets --surface S --cbr N --adt N --width M [--length M --out-dir DIR --pdf]"""
    return _run_infra("sheets", argv)


def cmd_job_k(argv):
    """K escalation per installment from the project's schedule (out/schedule/schedule.json).
    job-k PROJECT --signed 2569-01-15 --bid-open 2568-12-10 [--approval DATE] [--formula 1] [--indices FILE]"""
    if not argv or argv[0].startswith("-"):
        raise RuntimeError("usage: job-k PROJECT_FOLDER --signed YYYY-MM-DD --bid-open YYYY-MM-DD (พ.ศ.)")
    project = Path(argv[0]).resolve()
    sched = project / "out" / "schedule" / "schedule.json"
    if not sched.exists():
        raise RuntimeError(f"no schedule yet ({sched}) — run: job-run {project} --only schedule")
    rest = list(argv[1:])
    if "--indices" in rest:
        i = rest.index("--indices") + 1
        rest[i] = str(Path(rest[i]).resolve())
    return _run_pack(["k-plan"], [str(sched), *rest, "--out", str(project / "out" / "k")])


def cmd_job_run(argv):
    """Whole chain for one project: model > calc > sheets A/S/MEP > check > permit book > presentation
    > BOQ + ราคากลาง ปร.1-ปร.4 > duration, installments, S-curve.  job-run PROJECT [--from N] [--only x,y] [--list]"""
    import subprocess
    if not argv or argv[0].startswith("-"):
        raise RuntimeError("usage: job-run PROJECT_FOLDER [--from N] [--only calc,price] [--list]")
    project = Path(argv[0]).resolve()
    if not (project / "run_all.py").exists():
        raise RuntimeError(f"not a project folder (no run_all.py): {project}")
    _kit_fonts(project)
    env = dict(os.environ, YOTATHAI_HOME=str(ROOT), QT_QPA_PLATFORM="offscreen", PYTHONUTF8="1")
    env.setdefault("YOTATHAI_REF", str(_kit() / "knowledge" / "ref-data"))
    extra = argv[1:]
    if "--list" not in extra and "--skip-render" not in extra and "--render" not in extra:
        extra.append("--skip-render")           # no window/GPU needed unless asked
    extra = [a for a in extra if a != "--render"]
    proc = subprocess.run([sys.executable, str(project / "run_all.py"), *extra], cwd=str(project), env=env,
                          capture_output=True, text=True, encoding="utf-8")
    out = proc.stdout.strip().splitlines()
    if proc.returncode:
        raise RuntimeError("\n".join(out[-14:]) or proc.stderr.strip()[-800:])
    files = [l.split(": ", 1)[1].rsplit(" (", 1)[0] for l in out if l.startswith("  ") and ": /" in l]
    return {"project": str(project), "outputs": files, "log": str(project / "out" / "logs")}


def cmd_open(argv):
    from yotathai.bridge import launch
    from yotathai.paths import mode_for
    if not argv:
        launch()
        return {"opened": "home"}
    path = Path(argv[0]).resolve()
    if mode_for(path) is None:
        raise ValueError(f"not a drawing or model: {path.name}")
    from yotathai.live import request_reload
    if request_reload(path):         # a window already shows this file: it refreshes itself
        return {"opened": str(path), "mode": mode_for(path), "reused_window": True}
    launch(None, path)
    return {"opened": str(path), "mode": mode_for(path)}


def cmd_recipes(argv):
    use_3d_engine()
    from core.ai_recipes import reference
    print(reference())
    return {}


def cmd_check(argv):
    import subprocess

    from yotathai.paths import SRC_2D, SRC_3D, python
    report = {}
    for name, folder in (("2d", SRC_2D), ("3d", SRC_3D)):
        if sys.platform == "win32":
            # embedded Python is isolated (no script-folder on sys.path): start the engine
            # the same way the check .bat does
            cmd, cwd = [python(), "-X", "utf8", "-m", "yotathai.run_engine", name, "--check"], str(ROOT)
        else:
            cmd, cwd = [python(), "main.py", "--check"], str(folder)
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=180)
        report[name] = "OK" if proc.returncode == 0 else proc.stdout.strip()[-300:]
    # LibreDWG shipped with the program (or on PATH)
    sys.path.insert(0, str(SRC_2D))
    from formats.dwg_bridge import find_dwg2dxf, find_dxf2dwg
    d2x, x2d = find_dwg2dxf(), find_dxf2dwg()
    report["dwg_writer"] = (f"LibreDWG dxf2dwg (R2000): {x2d}" if x2d
                            else "missing (LibreDWG dxf2dwg; DXF still works)")
    report["dwg_reader"] = f"LibreDWG dwg2dxf: {d2x}" if d2x else "missing (LibreDWG dwg2dxf)"
    import re
    import subprocess
    for key, tool in (("dwg_reader", d2x), ("dwg_writer", x2d)):        # LibreDWG < 0.14 อ่านแบบจริงของหน่วยงานไม่ได้ (วัด 31 ต.ค. 2569)
        if tool:
            try:
                out = subprocess.run([str(tool), "--version"], capture_output=True, text=True, timeout=20)
                m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", (out.stdout + out.stderr))
                ver = tuple(int(x or 0) for x in m.groups()) if m else None
            except Exception:
                ver = None
            if ver:
                report[key] += f" [รุ่น {'.'.join(str(x) for x in ver)}]"
                if ver < (0, 14):
                    report[key] += " — เก่าเกินไป: อ่านไฟล์ DWG จริงไม่ได้ ต้องใช้ 0.14 ขึ้นไป (cloud/setup.sh คอมไพล์ให้)"
    report["engine_root"] = str(ROOT)
    report["python"] = sys.executable
    fonts = ROOT / "fonts"
    report["fonts"] = (f"{len(list(fonts.glob('*.ttf')))} files in {fonts}" if fonts.is_dir()
                       else "no fonts folder (system fonts only)")
    try:                                    # PDF -> PNG for the work kit goes through Qt's PDF module
        from PySide6.QtPdf import QPdfDocument  # noqa: F401
        report["pdf_to_png"] = "OK (Qt QtPdf)"
    except Exception as exc:  # noqa: BLE001
        report["pdf_to_png"] = f"missing: {exc}"
    try:
        import pypdf  # noqa: F401
        report["pdf_merge"] = "OK (pypdf)"
    except ImportError:
        import shutil
        report["pdf_merge"] = "OK (pdfunite/qpdf)" if (shutil.which("pdfunite") or shutil.which("qpdf")) \
            else "missing (pypdf, pdfunite or qpdf)"
    if any(v != "OK" for k, v in report.items() if k in ("2d", "3d")):
        raise RuntimeError(f"engine check failed: {report}")
    return report


WORK_SUFFIXES = (".igz", ".dxf", ".dwg", ".skp")
_SKIP_DIRS = {"python", "src", "ingecad-src", "yotathai", "yotathai_ai", "fonts", "licenses", "resources",
              "node_modules", "__pycache__", "site-packages", "$recycle.bin", "appdata", ".git", "venv"}


def _work_roots() -> list:
    """The usual places a user keeps drawings/models: Documents (also under OneDrive), Desktop,
    Downloads, the Yotathai work folder, and the install folder's data/ (auto-save)."""
    from yotathai.paths import DOCUMENTS
    home = Path.home()
    roots = [DOCUMENTS.parent, DOCUMENTS, home / "Desktop", home / "Downloads", home / "Documents"]
    for one in home.glob("OneDrive*"):
        roots += [one / "Documents", one / "Desktop", one / "เอกสาร", one / "เดสก์ท็อป"]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        roots.append(Path(local) / "Yotathai" / "data")
    seen, out = set(), []
    for r in roots:
        try:
            key = str(r.resolve()).lower()
        except OSError:
            continue
        if key not in seen and r.is_dir():
            seen.add(key)
            out.append(r)
    return out


def cmd_find_work(argv):
    """List the user's drawings/models, newest first, so work from an older version is never "lost":
    find-work [--days N] [--all] [--depth 4] [FOLDER ...]  (default: the usual places, newest 40)."""
    import time
    days, depth, show_all, extra = None, 4, False, []
    it = iter(argv)
    for a in it:
        if a == "--days":
            days = float(next(it))
        elif a == "--depth":
            depth = int(next(it))
        elif a == "--all":
            show_all = True
        else:
            extra.append(Path(a).expanduser())
    roots = extra or _work_roots()
    now, found, seen = time.time(), [], set()

    def walk(folder: Path, level: int) -> None:
        try:
            entries = list(os.scandir(folder))
        except OSError:
            return
        for e in entries:
            try:
                if e.is_dir(follow_symlinks=False):
                    if level < depth and e.name.lower() not in _SKIP_DIRS:
                        walk(Path(e.path), level + 1)
                elif e.name.lower().endswith(WORK_SUFFIXES) and not e.name.startswith(("~", ".")):
                    st = e.stat()
                    key = (e.name.lower(), st.st_size, int(st.st_mtime))
                    if key in seen or (days is not None and now - st.st_mtime > days * 86400):
                        continue
                    seen.add(key)
                    found.append((st.st_mtime, st.st_size, e.path))
            except OSError:
                continue

    for r in roots:
        walk(r, 0)
    found.sort(reverse=True)
    shown = found if show_all else found[:40]
    lines = [f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(m))} | {size / 1024:,.0f} KB | {path}"
             for m, size, path in shown]
    return {"searched": [str(r) for r in roots], "found": len(found), "shown": len(shown),
            "files": lines,
            "note": "autosave of the portable package is in <package>/app/data/autosave; "
                    "copy app/data from the old package to the new one to keep settings"}


COMMANDS = {
    "plan-to-3d": cmd_plan_to_3d, "model-to-2d": cmd_model_to_2d,
    "room-import": cmd_room_import, "room-add": cmd_room_add, "room-list": cmd_room_list,
    "room-check": cmd_room_check, "room-suggest": cmd_room_suggest, "room-remove": cmd_room_remove,
    "build-3d": cmd_build_3d, "draw-2d": cmd_draw_2d, "to-dwg": cmd_to_dwg,
    "calc-beam": cmd_calc_beam, "calc-rc": cmd_calc_rc, "calc-building": cmd_calc_building, "calc-foundation": cmd_calc_foundation, "job-building": cmd_job_building, "job-new": cmd_job_new, "job-run": cmd_job_run, "job-k": cmd_job_k, "price-road": cmd_price_road, "time-road": cmd_time_road, "road-section": cmd_road_section, "road-takeoff": cmd_road_takeoff, "road-sheets": cmd_road_sheets, "open": cmd_open, "find-work": cmd_find_work, "recipes": cmd_recipes, "check": cmd_check,
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    name = sys.argv[1]
    if name not in COMMANDS:
        print(f"unknown command {name!r}\n{__doc__}", file=sys.stderr)
        return 2
    return run(COMMANDS[name], sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())
