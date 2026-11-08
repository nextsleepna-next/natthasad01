# SPDX-License-Identifier: GPL-3.0-or-later
"""Qt pieces both engines share: the «2D ⇄ 3D» menu skeleton and running
a converter in the background with a progress dialog.

PySide6 only — no engine import — so the 2D and the 3D window both use it.
Texts are Thai directly: this layer exists for Yotathai alone.
"""
from __future__ import annotations

import json
import re

from yotathai.paths import ROOT, python

MENU_TITLE = "2D ⇄ 3D"


def add_menu(window, before_title_candidates=("Help", "ช่วยเหลือ", "วิธีใช้")):
    """A «2D ⇄ 3D» menu just before Help (or at the end). Returns it; an
    existing one is emptied and reused (menus get rebuilt)."""
    from PySide6.QtWidgets import QMenu
    # Yotathai CAD keeps its own QMenuBar in a header widget; asking the
    # window for menuBar() would make a second, empty one.
    bar = getattr(window, "_menu_bar", None) or window.menuBar()
    for act in bar.actions():
        menu = act.menu()
        if menu is not None and menu.objectName() == "yt_bridge_menu":
            menu.clear()
            return menu
    menu = QMenu(MENU_TITLE, window)
    menu.setObjectName("yt_bridge_menu")
    before = None
    for act in bar.actions():
        text = act.text().replace("&", "")
        if text in before_title_candidates:
            before = act
            break
    if before is not None:
        bar.insertMenu(before, menu)
    else:
        bar.addMenu(menu)
    return menu


def action(menu, text, slot, tip=""):
    from PySide6.QtGui import QAction
    act = QAction(text, menu)
    # Keep macOS from moving it into the application menu by its words.
    act.setMenuRole(QAction.MenuRole.NoRole)
    if tip:
        act.setStatusTip(tip)
        act.setToolTip(tip)
    act.triggered.connect(lambda _checked=False: slot())
    menu.addAction(act)
    return act


def common_actions(menu, other_mode_text, open_other):
    """The two items every engine has under the conversion one."""
    from yotathai.bridge import go_home
    menu.addSeparator()
    action(menu, other_mode_text, open_other)
    action(menu, "หน้าแรก Yotathai Plan", go_home,
           "เปิดหน้าแรก: เลือกเขียนแบบ 2 มิติ / โมเดล 3 มิติ และไฟล์ล่าสุด")


def run_converter(parent, module: str, args: list, title: str, label: str):
    """Run ``python -m yotathai.convert.<module> args --json`` without
    freezing the window: a progress dialog (Cancel kills the job) that
    follows ``view n/total`` lines. Returns the report dict, None when
    cancelled; raises RuntimeError with the converter's message."""
    from PySide6.QtCore import QEventLoop, QProcess, QProcessEnvironment, Qt
    from PySide6.QtWidgets import QProgressDialog

    proc = QProcess(parent)
    proc.setWorkingDirectory(str(ROOT))
    env = QProcessEnvironment.systemEnvironment()
    env.remove("PYTHONPATH")
    proc.setProcessEnvironment(env)
    out_chunks: list[str] = []
    err_chunks: list[str] = []
    dlg = QProgressDialog(label, "ยกเลิก", 0, 0, parent)
    dlg.setWindowTitle(title)
    dlg.setWindowModality(Qt.WindowModal)
    dlg.setMinimumDuration(300)
    dlg.setAutoClose(False)
    dlg.setAutoReset(False)
    loop = QEventLoop()
    state = {"cancelled": False}

    def read_out():
        text = bytes(proc.readAllStandardOutput()).decode("utf-8", "replace")
        out_chunks.append(text)
        for m in re.finditer(r"view (\d+)/(\d+)", text):
            n, total = int(m.group(1)), int(m.group(2))
            dlg.setMaximum(total)
            dlg.setValue(n)
            dlg.setLabelText(f"{label}\n({n}/{total})")

    def read_err():
        err_chunks.append(bytes(proc.readAllStandardError()).decode("utf-8", "replace"))

    def cancel():
        # QProgressDialog also says «canceled» when it is merely closed —
        # only a click while the job runs is a cancel.
        if proc.state() == QProcess.NotRunning:
            return
        state["cancelled"] = True
        proc.kill()

    proc.readyReadStandardOutput.connect(read_out)
    proc.readyReadStandardError.connect(read_err)
    proc.finished.connect(lambda *_a: loop.quit())
    proc.errorOccurred.connect(lambda *_a: loop.quit())
    dlg.canceled.connect(cancel)
    proc.start(python(), ["-m", f"yotathai.convert.{module}", *map(str, args), "--json"])
    if not proc.waitForStarted(5000):
        dlg.close()
        raise RuntimeError("เริ่มตัวแปลงไม่ได้: " + proc.errorString())
    if proc.state() != QProcess.NotRunning:
        loop.exec()
    read_out()
    read_err()
    dlg.canceled.disconnect(cancel)
    dlg.close()
    if state["cancelled"]:
        return None
    lines = [ln for ln in "".join(out_chunks).splitlines() if ln.startswith("{")]
    report = None
    if lines:
        try:
            report = json.loads(lines[-1])
        except ValueError:
            pass
    if report is None or not report.get("ok"):
        msg = (report or {}).get("error") or "".join(err_chunks).strip()[-800:] \
            or f"exit {proc.exitCode()}"
        raise RuntimeError(msg)
    return report
