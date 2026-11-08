# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Yotathai — on top of IngeCAD (Marco Sumari Tellez and contributors).
"""Yotathai CAD inside the one Yotathai app (``yotathai/`` at the project
root): the menu bar name, macOS "open file" events, the start without the
startup window when the home screen already asked, and the «2D ⇄ 3D» menu
that raises the plan into a 3D model.

main.py calls :func:`early_init` before the QApplication, builds the app
with :func:`make_app`, and calls :func:`install` once the window exists.
Without the ``yotathai`` package the program runs exactly as before.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def _shell():
    if not (_ROOT / "yotathai" / "__init__.py").is_file():
        return None
    if str(_ROOT) not in sys.path:
        sys.path.append(str(_ROOT))     # after ingecad-src/: our core stays first
    try:
        import yotathai.bridge  # noqa: F401
        return sys.modules["yotathai"]
    except Exception:          # noqa: BLE001
        return None


def early_init() -> None:
    if _shell() is None:
        return
    from yotathai import macos
    macos.set_app_name("Yotathai")


def from_home() -> bool:
    """Started from the Yotathai home screen: the startup window (units,
    recent drawings) would ask what the home screen just asked."""
    return os.environ.get("YOTATHAI_FROM_HOME") == "1"


# ---- macOS "open file" ---------------------------------------------------------------

def open_any(window, path: Path) -> None:
    """A file macOS (or the user) hands to this running 2D window: a model
    goes to the 3D side; a drawing opens here when the window holds only an
    untouched new drawing, else in a window of its own (never a "save
    changes?" question for a double-click)."""
    path = Path(path)
    shell = _shell()
    if shell is not None:
        from yotathai.bridge import launch
        from yotathai.paths import MODE_2D, MODE_3D, mode_for
        mode = mode_for(path)
        if mode == MODE_3D:
            launch(MODE_3D, path)
            return
        if mode != MODE_2D:
            return
        doc = window.document
        busy = doc is not None and (doc.path is not None or doc.dirty)
        if busy:
            launch(MODE_2D, path)
            return
    if path.suffix.lower() in (".dxf", ".dwg") and path.exists():
        window.open_path(path)


def make_app(argv):
    """The QApplication, catching macOS's FileOpen event: Finder never puts
    a double-clicked drawing on the command line, it sends the event — the
    2D window used to ignore it and show an empty drawing."""
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    class _App(QApplication):
        def __init__(self, args):
            super().__init__(args)
            self.open_window = None
            self.pending_open_path = None

        def event(self, e):  # noqa: D401 — Qt override
            if e.type() == QEvent.Type.FileOpen:
                path = Path(e.file())
                if self.open_window is not None:
                    open_any(self.open_window, path)
                else:
                    self.pending_open_path = path
                return True
            return super().event(e)

    return _App(argv)


# ---- the menu -------------------------------------------------------------------------

def install(window) -> None:
    if _shell() is None:
        return
    build = getattr(window, "_build_menus", None)
    if build is not None and not getattr(build, "_yotathai", False):
        # The menu bar is rebuilt whenever a plugin is switched on or off;
        # put our menu back each time.
        def rebuilt(*a, **k):
            result = build(*a, **k)
            _add_menu(window)
            return result
        rebuilt._yotathai = True
        window._build_menus = rebuilt
    _add_menu(window)


def _add_menu(window) -> None:
    try:
        from core.i18n import tr
        from yotathai import ui
        from yotathai.bridge import launch
        from yotathai.paths import MODE_3D
        menu = ui.add_menu(window, (tr("Help"), "Help", "ช่วยเหลือ"))
        ui.action(menu, "ยกแปลนนี้เป็นโมเดล 3 มิติ…", lambda: lift_to_3d(window),
                  "อ่านผนัง (เส้นคู่หรือเส้นกึ่งกลาง) ประตู หน้าต่าง เสา จากเลเยอร์ "
                  "แล้วสร้างโมเดล 3 มิติ เปิดในส่วนโมเดล 3 มิติ")
        ui.common_actions(menu, "เปิดส่วนโมเดล 3 มิติ", lambda: launch(MODE_3D))
    except Exception:          # noqa: BLE001 — never block the window
        import traceback
        traceback.print_exc()


def _detect_layers(doc) -> dict:
    """Which layers look like walls / doors / windows / columns, by name —
    the same rule the converter applies (shown so the user can correct)."""
    from yotathai.convert.plan_to_model import ROLE_PATTERNS, role_of
    found = {r: [] for r in ROLE_PATTERNS}
    used = set()
    try:
        for e in doc.modelspace():
            used.add(e.dxf.get("layer", "0"))
        for block in doc.blocks:
            if not block.name.startswith("*"):
                for e in block:
                    used.add(e.dxf.get("layer", "0"))
    except Exception:          # noqa: BLE001
        pass
    for layer in doc.layers:
        name = layer.dxf.name
        if name not in used:
            continue
        role = role_of(name, {})
        if role is not None:
            found[role].append(name)
    return found


ROLE_LABELS = {"wall": "ผนัง", "door": "ประตู", "window": "หน้าต่าง",
               "column": "เสา"}


def _selection(window) -> set:
    """Handles selected in model space (empty in a paper layout)."""
    try:
        if getattr(window, "_active_layout", "Model") != "Model":
            return set()
        return set(window.tools.selection or ())
    except Exception:          # noqa: BLE001
        return set()


def _ask_options(window, detected: dict, selected: int = 0):
    from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox,
                                   QDoubleSpinBox,
                                   QFormLayout, QGroupBox, QLabel, QLineEdit,
                                   QVBoxLayout)
    dlg = QDialog(window)
    dlg.setWindowTitle("ยกแปลนเป็นโมเดล 3 มิติ")
    dlg.setMinimumWidth(520)
    lay = QVBoxLayout(dlg)
    intro = QLabel(
        "สร้างโมเดล 3 มิติจากแปลนที่เปิดอยู่ (แบบไม่ถูกแก้ไข): ผนังจากเส้นคู่ "
        "หรือเส้นกึ่งกลาง ช่องว่างในผนังเป็นประตู/หน้าต่างตามเลเยอร์ที่อยู่ตรงนั้น "
        "เสาจากรูปปิด และพื้นตามขอบผนัง")
    intro.setWordWrap(True)
    lay.addWidget(intro)

    def spin(value, lo=0.0, hi=50.0, step=0.05):
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(2)
        s.setSingleStep(step)
        s.setValue(value)
        s.setSuffix(" ม.")
        return s
    sizes = QGroupBox("ความสูง")
    f1 = QFormLayout(sizes)
    height = spin(3.0, 1.0)
    door_h = spin(2.10, 1.0)
    sill = spin(0.90)
    head = spin(2.10, 0.5)
    thick = spin(0.15, 0.04, 0.6, 0.01)
    f1.addRow("ความสูงผนัง", height)
    f1.addRow("ความสูงประตู / ช่องเปิด", door_h)
    f1.addRow("หน้าต่าง: ระดับขอบล่าง", sill)
    f1.addRow("หน้าต่าง: ระดับขอบบน", head)
    f1.addRow("ความหนาผนัง (ถ้าเขียนเส้นเดียว)", thick)
    lay.addWidget(sizes)

    roles = QGroupBox("เลเยอร์ (ตรวจจากชื่อ แก้ได้ คั่นด้วยจุลภาค)")
    f2 = QFormLayout(roles)
    edits = {}
    for role, label in ROLE_LABELS.items():
        e = QLineEdit(", ".join(detected.get(role, [])))
        e.setPlaceholderText("ไม่พบ")
        f2.addRow(label, e)
        edits[role] = e
    lay.addWidget(roles)

    only = QCheckBox(f"ใช้เฉพาะที่เลือกไว้ ({selected:,} ชิ้น)")
    only.setChecked(bool(selected))
    only.setVisible(bool(selected))
    lay.addWidget(only)
    if not selected:
        tip = QLabel("ถ้าแบบมีหลายแปลน (เช่น ชุดขออนุญาต) ให้เลือกเฉพาะแปลนชั้นที่ต้องการก่อน "
                     "ไม่เช่นนั้นทุกแปลนจะถูกยกขึ้นพร้อมกัน")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #6b7380;")
        lay.addWidget(tip)
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.button(QDialogButtonBox.Ok).setText("สร้างโมเดล")
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    lay.addWidget(buttons)
    while dlg.exec() == QDialog.Accepted:
        chosen = {r: [x.strip() for x in e.text().split(",") if x.strip()]
                  for r, e in edits.items()}
        if not chosen["wall"]:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(dlg, "ยกแปลนเป็นโมเดล 3 มิติ",
                                "ต้องมีเลเยอร์ผนังอย่างน้อย 1 เลเยอร์")
            continue
        if sill.value() >= head.value():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(dlg, "ยกแปลนเป็นโมเดล 3 มิติ",
                                "ขอบล่างหน้าต่างต้องต่ำกว่าขอบบน")
            continue
        return {"height": height.value(), "door_height": door_h.value(),
                "sill": sill.value(), "head": head.value(),
                "thickness": thick.value(), "layers": chosen,
                "only_selected": only.isChecked() and bool(selected)}
    return None


def _write_temp_dxf(doc) -> Path:
    """The drawing as it is on screen (unsaved edits included), without
    touching the document's own file name."""
    folder = Path(tempfile.mkdtemp(prefix="yotathai-2d3d-"))
    path = folder / "plan.dxf"
    with open(path, "wt", encoding=doc.output_encoding, errors="dxfreplace") as fp:
        doc.write(fp)
    return path


def _summary(report: dict) -> str:
    lines = [f"ผนัง {report['walls']} ช่วง (ยาวรวม {report['wall_length_m']:.2f} ม.)",
             f"ประตู {report['doors']} · หน้าต่าง {report['windows']} · "
             f"ช่องเปิดอื่น {report['openings']} · เสา {report['columns']}",
             f"พื้น {report['slab_area_m2']:.2f} ตร.ม."]
    rooms = report.get("rooms") or []
    if rooms:
        lines.append("")
        lines.append("ห้องที่ผนังล้อมรอบ (พื้นที่ภายในผนัง):")
        for r in rooms[:12]:
            lines.append(f"   • {r['name'] or 'ไม่มีชื่อ'}  {r['area_m2']:.2f} ตร.ม.")
        if len(rooms) > 12:
            lines.append(f"   … อีก {len(rooms) - 12} ห้อง")
    if report.get("mode") == "single":
        lines.append("")
        lines.append("ผนังเขียนเป็นเส้นเดียว: ใช้ความหนาที่กำหนด")
    return "\n".join(lines)


def lift_to_3d(window) -> None:
    from PySide6.QtWidgets import QMessageBox
    from yotathai import ui
    from yotathai.bridge import open_in_3d
    from yotathai.paths import output_folder, unique_path

    document = window.document
    if document is None or not len(document.doc.modelspace()):
        QMessageBox.information(window, "ยกแปลนเป็นโมเดล 3 มิติ",
                                "ยังไม่มีแปลน — เปิดหรือเขียนแปลนก่อน")
        return
    selected = _selection(window)
    opts = _ask_options(window, _detect_layers(document.doc), len(selected))
    if opts is None:
        return
    stem = Path(document.path).stem if document.path else "plan"
    out = unique_path(output_folder(document.path) / f"{stem}-3D.igz")
    tmp = None
    try:
        tmp = _write_temp_dxf(document.doc)
        args = [tmp, out, "--height", opts["height"],
                "--door-height", opts["door_height"], "--sill", opts["sill"],
                "--head", opts["head"], "--thickness", opts["thickness"]]
        for role, names in opts["layers"].items():
            args += [f"--{role}-layers", ",".join(names)]
        if opts.get("only_selected"):
            handles = tmp.parent / "selection.txt"
            handles.write_text("\n".join(sorted(selected)), encoding="utf-8")
            args += ["--handles", handles]
        report = ui.run_converter(window, "plan_to_model", args,
                                  "ยกแปลนเป็นโมเดล 3 มิติ", "กำลังสร้างโมเดล…")
    except Exception as exc:  # noqa: BLE001 — shown to the user
        QMessageBox.warning(window, "ยกแปลนเป็นโมเดล 3 มิติ",
                            f"สร้างโมเดลไม่สำเร็จ\n\n{exc}")
        return
    finally:
        if tmp is not None:
            for f in tmp.parent.iterdir():
                try:
                    f.unlink()
                except OSError:
                    pass
            try:
                tmp.parent.rmdir()
            except OSError:
                pass
    if report is None:
        return
    box = QMessageBox(window)
    box.setWindowTitle("ยกแปลนเป็นโมเดล 3 มิติ")
    box.setIcon(QMessageBox.Information)
    box.setText("สร้างโมเดลแล้ว")
    box.setInformativeText(_summary(report) + f"\n\nไฟล์: {out}")
    open_btn = box.addButton("เปิดในโมเดล 3 มิติ", QMessageBox.AcceptRole)
    box.addButton("ปิด", QMessageBox.RejectRole)
    box.setDefaultButton(open_btn)
    box.exec()
    if box.clickedButton() is open_btn:
        open_in_3d(out)
