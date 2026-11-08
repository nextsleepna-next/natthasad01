# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Yotathai — built on IngeTrazo (Marco Sumari Tellez and contributors).
"""Yotathai 3D inside the one Yotathai app (``yotathai/`` at the project
root): the menu bar name, the «2D ⇄ 3D» menu, and drawings that belong to
the 2D side going there.

main.py calls :func:`early_init` before the QApplication, :func:`route_open`
for every file it is asked to open, and :func:`install` once the window
exists. Every hook is best-effort: without the ``yotathai`` package (a
plain IngeTrazo checkout) the program runs exactly as before.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def _shell():
    """The yotathai package, or None when this is not a Yotathai tree."""
    if not (_ROOT / "yotathai" / "__init__.py").is_file():
        return None
    if str(_ROOT) not in sys.path:
        sys.path.append(str(_ROOT))     # after src/: our core stays first
    try:
        import yotathai.bridge  # noqa: F401
        return sys.modules["yotathai"]
    except Exception:          # noqa: BLE001
        return None


def early_init() -> None:
    """Before the QApplication: the app is «Yotathai» in the menu bar."""
    if _shell() is None:
        return
    from yotathai import macos
    macos.set_app_name("Yotathai")


def from_home() -> bool:
    """Started from the Yotathai home screen (which already offered new /
    open / recent): the 3D welcome screen would only ask again."""
    return os.environ.get("YOTATHAI_FROM_HOME") == "1"


def route_open(path) -> bool:
    """A drawing (DXF/DWG) double-clicked or handed to us belongs to the 2D
    side: open it there. True when it was handed over."""
    if _shell() is None:
        return False
    from yotathai.paths import MODE_2D, mode_for
    if mode_for(path) != MODE_2D:
        return False
    from yotathai.bridge import open_in_2d
    open_in_2d(Path(path))
    return True


# ---- the menu ----------------------------------------------------------------------

def install(window) -> None:
    if _shell() is None:
        return
    from views.live_reload import install as install_live_reload
    install_live_reload(window)         # follows the file when something else rewrites it
    try:
        from core.i18n import tr
        from yotathai import ui
        from yotathai.bridge import launch
        from yotathai.paths import MODE_2D
        menu = ui.add_menu(window, (tr("Help"), "Help", "ช่วยเหลือ"))
        ui.action(menu, "ส่งผังและรูปด้านไปเขียนแบบ 2 มิติ…",
                  lambda: send_to_2d(window),
                  "ตัดผังพื้นตามระดับที่เลือก + ผังหลังคา + รูปด้าน 4 ด้าน "
                  "เป็นแบบ DXF หน่วยเมตร แล้วเปิดในส่วนเขียนแบบ 2 มิติ")
        ui.common_actions(menu, "เปิดส่วนเขียนแบบ 2 มิติ",
                          lambda: launch(MODE_2D))
    except Exception:          # noqa: BLE001 — never block the window
        import traceback
        traceback.print_exc()


def _ask_options(window, zmin: float, zmax: float):
    """Cut levels and what to draw. None when cancelled."""
    from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox,
                                   QFormLayout, QLabel, QLineEdit,
                                   QVBoxLayout)
    dlg = QDialog(window)
    dlg.setWindowTitle("ส่งไปเขียนแบบ 2 มิติ")
    lay = QVBoxLayout(dlg)
    intro = QLabel(
        "สร้างแบบ 2 มิติจากโมเดลนี้ในไฟล์ DXF เดียว (หน่วยเมตร) "
        "แล้วเปิดในส่วนเขียนแบบ 2 มิติ — โมเดลไม่ถูกแก้ไข")
    intro.setWordWrap(True)
    lay.addWidget(intro)
    form = QFormLayout()
    from yotathai.convert.views_to_dxf import default_cut
    cuts = QLineEdit(f"{default_cut(zmin, zmax):.2f}")
    cuts.setToolTip("ใส่ได้หลายระดับ คั่นด้วยจุลภาค เช่น 1.65, 5.65, 9.65 "
                    "(ผังพื้นชั้นละ 1 รูป ตัดที่ระดับนั้น)")
    form.addRow("ระดับที่ตัดผังพื้น (ม.)", cuts)
    form.addRow("", QLabel(f"โมเดลสูงจาก {zmin:+.2f} ถึง {zmax:+.2f} ม."))
    roof = QCheckBox("ผังหลังคา (มองจากด้านบน)")
    roof.setChecked(True)
    elev = QCheckBox("รูปด้าน 4 ด้าน (หน้า ขวา หลัง ซ้าย)")
    elev.setChecked(True)
    form.addRow("", roof)
    form.addRow("", elev)
    lay.addLayout(form)
    note = QLabel("อาคารใหญ่ใช้เวลาประมาณครึ่งนาที (คำนวณเส้นที่ถูกบังจริง)")
    note.setStyleSheet("color: #6b7380;")
    lay.addWidget(note)
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.button(QDialogButtonBox.Ok).setText("สร้างแบบ")
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    lay.addWidget(buttons)
    while dlg.exec() == QDialog.Accepted:
        try:
            levels = [float(x) for x in cuts.text().replace(" ", "").split(",") if x]
        except ValueError:
            levels = None
        if levels and all(zmin < z < zmax for z in levels):
            return levels, roof.isChecked(), elev.isChecked()
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(dlg, "ระดับตัดผัง",
                            f"ใส่ตัวเลขระดับ (ม.) ระหว่าง {zmin:+.2f} ถึง {zmax:+.2f} "
                            "คั่นด้วยจุลภาค")
    return None


def send_to_2d(window) -> None:
    """Model -> DXF sheet (plans, roof, elevations) -> the 2D side."""
    from PySide6.QtWidgets import QMessageBox
    from formats import igz as igz_format
    from yotathai import ui
    from yotathai.bridge import open_in_2d
    from yotathai.paths import output_folder, unique_path

    scene = window.viewport.scene
    lo, hi = scene.bounds()
    if lo is None:
        QMessageBox.information(window, "ส่งไปเขียนแบบ 2 มิติ",
                                "ยังไม่มีอะไรในโมเดล — วาดหรือเปิดโมเดลก่อน")
        return
    opts = _ask_options(window, lo.z(), hi.z())
    if opts is None:
        return
    levels, roof, elevations = opts
    current = getattr(window, "_current_path", None)
    stem = Path(current).stem if current else "model"
    out = unique_path(output_folder(current) / f"{stem}-2D.dxf")
    tmp = Path(tempfile.mkdtemp(prefix="yotathai-3d2d-")) / "model.igz"
    try:
        igz_format.save_scene(scene, tmp)      # the live model, saved or not
        args = [tmp, out, "--cuts", ",".join(f"{z:.3f}" for z in levels),
                "--title", stem]
        if not roof:
            args.append("--no-roof")
        if not elevations:
            args.append("--no-elevations")
        report = ui.run_converter(window, "views_to_dxf", args,
                                  "ส่งไปเขียนแบบ 2 มิติ",
                                  "กำลังสร้างผังและรูปด้าน…")
    except Exception as exc:  # noqa: BLE001 — shown to the user
        QMessageBox.warning(window, "ส่งไปเขียนแบบ 2 มิติ",
                            f"สร้างแบบไม่สำเร็จ\n\n{exc}")
        return
    finally:
        try:
            tmp.unlink()
            tmp.parent.rmdir()
        except OSError:
            pass
    if report is None:
        return                                 # cancelled
    open_in_2d(out)
    lines = sum(v["lines"] for v in report.get("views", []))
    window.statusBar().showMessage(
        f"ส่งแบบ {len(report.get('views', []))} รูป ({lines:,} เส้น) ไปเขียนแบบ 2 มิติแล้ว: {out}",
        15000)
