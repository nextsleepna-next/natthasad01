# SPDX-License-Identifier: GPL-3.0-or-later
"""The Yotathai home screen: pick 2D drafting or 3D modelling, open a file,
or reopen a recent one of either kind.

Choosing turns THIS process into the engine (``exec_engine``), so the
window the user picked replaces the home screen under the same Dock icon.
A file double-clicked in Finder while the home screen is up (or that
started the app) goes straight to its engine the same way.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from yotathai.paths import EXT_2D, EXT_3D, MODE_2D, MODE_3D, SRC_3D, mode_for

ACCENT = "#3A49A6"          # indigo chrome (same as views/yotathai_skin.py)
ACCENT_DARK = "#28337A"
ORANGE = "#E8772E"          # the 3D mark (cube / arc) — not chrome
ORANGE_DARK = "#C45F1A"
NAVY = "#272c7e"
INK = "#1f2328"
MUTED = "#6b7380"

_FONTS = ["Sukhumvit Set", "Leelawadee UI", "Noto Sans Thai UI",
          "Noto Sans Thai", "Sarabun", "Thonburi", "Tahoma"]


# ---- recent files of both engines ---------------------------------------------

def _recent_3d() -> list[Path]:
    """Yotathai 3D keeps its list in its QSettings (``recent_files``)."""
    from PySide6.QtCore import QSettings
    # The 2-argument constructor always means NativeFormat (the registry on
    # Windows); spell the format out so Yotathai Portable's INI applies.
    raw = QSettings(QSettings.defaultFormat(), QSettings.UserScope,
                    "IngeTrazo", "IngeTrazo").value("recent_files", []) or []
    if isinstance(raw, str):
        raw = [raw]
    return [Path(str(p)) for p in raw]


def _recent_2d() -> list[Path]:
    """Yotathai CAD keeps a JSON list (ingecad-src/core/recent.py)."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    try:
        data = json.loads((Path(base) / "IngeCAD" / "recent.json")
                          .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [Path(p) for p in data if isinstance(p, str)]


#: Folders whose files are scratch, not the user's work (test runs, the
#: temp copies the converters make): never offered as "recent".
_SCRATCH = ("/tmp/", "/private/tmp/", "/private/var/folders/", "/var/folders/")
if sys.platform == "win32":
    import tempfile
    _SCRATCH += (tempfile.gettempdir(),)


def recent_by_mode(limit: int = 8) -> dict[str, list[tuple[Path, float]]]:
    """Each engine's own recent list — most recent first, as the engine
    keeps it — reduced to files that still exist: {"2d": [(path, mtime)],
    "3d": [...]}. Two lists, not one merged by date: merged, a week of
    drafting pushed every 3D model off the screen (คุณช่างถึก, 4 ต.ค. 2569)."""
    out: dict[str, list[tuple[Path, float]]] = {MODE_2D: [], MODE_3D: []}
    for mode, paths in ((MODE_2D, _recent_2d()), (MODE_3D, _recent_3d())):
        seen = set()
        for p in paths:
            key = str(p)
            if key in seen or mode_for(p) != mode or key.startswith(_SCRATCH):
                continue
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            seen.add(key)
            out[mode].append((p, mtime))
            if len(out[mode]) >= limit:
                break
    return out


def _when(mtime: float) -> str:
    days = int((time.time() - mtime) // 86400)
    if days <= 0:
        return "วันนี้"
    if days == 1:
        return "เมื่อวาน"
    if days < 30:
        return f"{days} วันก่อน"
    t = time.localtime(mtime)
    months = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.",
              "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    return f"{t.tm_mday} {months[t.tm_mon - 1]} {t.tm_year + 543}"


# ---- painted glyphs for the two big buttons ------------------------------------

def _glyph(kind: str, size: int = 64):
    """A plan (2D) or a box in isometric (3D), drawn — no image files."""
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF
    from PySide6.QtWidgets import QApplication
    dpr = max(1.0, QApplication.instance().devicePixelRatio())
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#FFE9DA" if kind == MODE_3D else "#E4E6F6"))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
    s = size / 64.0
    if kind == MODE_2D:
        pen = QPen(QColor(NAVY), 3.2 * s)
        pen.setJoinStyle(Qt.MiterJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(14 * s, 16 * s, 36 * s, 32 * s))
        p.drawLine(QPointF(32 * s, 16 * s), QPointF(32 * s, 34 * s))
        p.drawLine(QPointF(14 * s, 34 * s), QPointF(24 * s, 34 * s))
        thin = QPen(QColor(ORANGE), 2.0 * s)
        p.setPen(thin)
        p.drawArc(QRectF(24 * s - 8 * s, 34 * s - 8 * s, 16 * s, 16 * s), 0, 90 * 16)
        p.drawLine(QPointF(14 * s, 54 * s), QPointF(50 * s, 54 * s))
        p.drawLine(QPointF(14 * s, 51 * s), QPointF(14 * s, 57 * s))
        p.drawLine(QPointF(50 * s, 51 * s), QPointF(50 * s, 57 * s))
    else:
        c = QPointF(32 * s, 34 * s)
        top = QPolygonF([QPointF(32 * s, 12 * s), QPointF(52 * s, 23 * s),
                         c, QPointF(12 * s, 23 * s)])
        left = QPolygonF([QPointF(12 * s, 23 * s), c,
                          QPointF(32 * s, 56 * s), QPointF(12 * s, 45 * s)])
        right = QPolygonF([c, QPointF(52 * s, 23 * s),
                           QPointF(52 * s, 45 * s), QPointF(32 * s, 56 * s)])
        pen = QPen(QColor(ORANGE_DARK), 2.0 * s)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(QColor("#ffffff"))
        p.drawPolygon(top)
        p.setBrush(QColor(ORANGE))
        p.drawPolygon(left)
        p.setBrush(QColor(ORANGE).darker(125))
        p.drawPolygon(right)
    p.end()
    return pm


STYLE = f"""
QWidget#home {{ background: #ffffff; }}
QLabel {{ color: {INK}; }}
QLabel#title {{ font-size: 30px; font-weight: 700; color: {NAVY}; }}
QLabel#sub {{ font-size: 14px; color: {MUTED}; }}
QLabel#head {{ font-size: 14px; font-weight: 700; color: {ACCENT}; }}
QLabel#foot {{ font-size: 11px; color: #8a919b; }}
QFrame#card {{
    border-radius: 14px; background: #f6f6f4; border: 1px solid #e4e4e0;
}}
QFrame#card:hover, QFrame#card:focus {{ background: #eff0fa; border: 1px solid {ACCENT}; }}
QLabel#cardTitle {{ font-size: 19px; font-weight: 700; color: {INK}; background: transparent; }}
QLabel#cardText {{ font-size: 13px; color: {MUTED}; background: transparent; }}
QPushButton#open {{
    padding: 9px 18px; border-radius: 9px; font-size: 14px;
    background: {ACCENT}; color: white; border: 1px solid {ACCENT_DARK};
}}
QPushButton#open:hover {{ background: {ACCENT_DARK}; }}
QPushButton#link {{
    padding: 9px 14px; border-radius: 9px; font-size: 14px;
    background: #ffffff; color: {INK}; border: 1px solid #d6d6d2;
}}
QPushButton#link:hover {{ border: 1px solid {ACCENT}; }}
QListWidget {{
    border: 1px solid #e4e4e0; border-radius: 10px; padding: 4px;
    background: #ffffff; outline: none;
}}
QListWidget::item {{ border-radius: 7px; padding: 2px; }}
QScrollBar:vertical {{ width: 10px; background: transparent; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #d0d0cc; border-radius: 4px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: {ACCENT}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QListWidget::item:hover {{ background: #eff0fa; }}
QListWidget::item:selected {{ background: #ffe6d4; color: {INK}; }}
"""


def _card(kind: str, title: str, lines: str, on_click):
    """A big clickable tile: glyph, title, one line of what it is for."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

    class _Card(QFrame):
        def mouseReleaseEvent(self, e):  # noqa: N802 — Qt override
            if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
                on_click()

        def keyPressEvent(self, e):  # noqa: N802 — Qt override
            if e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
                on_click()
            else:
                super().keyPressEvent(e)

    card = _Card()
    card.setObjectName("card")
    card.setAttribute(Qt.WA_Hover, True)
    card.setFocusPolicy(Qt.StrongFocus)
    card.setCursor(Qt.PointingHandCursor)
    card.setAccessibleName(title)
    h = QHBoxLayout(card)
    h.setContentsMargins(18, 16, 18, 16)
    h.setSpacing(16)
    icon = QLabel()
    icon.setPixmap(_glyph(kind, 64))
    icon.setFixedSize(64, 64)
    h.addWidget(icon, 0, Qt.AlignVCenter)
    v = QVBoxLayout()
    v.setSpacing(3)
    t = QLabel(title)
    t.setObjectName("cardTitle")
    d = QLabel(lines)
    d.setObjectName("cardText")
    d.setWordWrap(True)
    v.addStretch(1)
    v.addWidget(t)
    v.addWidget(d)
    v.addStretch(1)
    h.addLayout(v, 1)
    card.setMinimumHeight(108)
    return card


class _RecentRow:
    """One line of the recent list: badge, name, folder and age."""

    @staticmethod
    def widget(mode: str, path: Path, mtime: float):
        from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(8, 5, 8, 5)
        h.setSpacing(10)
        badge = QLabel("2D" if mode == MODE_2D else "3D")
        color = NAVY if mode == MODE_2D else ORANGE
        badge.setStyleSheet(
            f"background: {color}; color: white; border-radius: 5px;"
            f"padding: 1px 6px; font-weight: 700; font-size: 11px;")
        badge.setFixedWidth(30)
        h.addWidget(badge)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        name = QLabel(path.name)
        name.setStyleSheet("font-size: 14px;")
        folder = QLabel(str(path.parent).replace(str(Path.home()), "~"))
        folder.setStyleSheet(f"font-size: 11px; color: {MUTED};")
        texts.addWidget(name)
        texts.addWidget(folder)
        h.addLayout(texts, 1)
        age = QLabel(_when(mtime))
        age.setStyleSheet(f"font-size: 11px; color: {MUTED};")
        h.addWidget(age)
        return w


def _build(window, choose):
    """Fill ``window``; ``choose(mode, path_or_None)`` leaves for an engine."""
    from PySide6.QtCore import QSize, Qt
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel,
                                   QListWidget, QListWidgetItem, QPushButton,
                                   QVBoxLayout)
    window.setObjectName("home")
    window.setStyleSheet(STYLE)
    root = QVBoxLayout(window)
    root.setContentsMargins(34, 28, 34, 18)
    root.setSpacing(16)

    header = QHBoxLayout()
    header.setSpacing(18)
    logo = QLabel()
    pm = QPixmap(str(SRC_3D / "resources" / "branding" / "yotathai-logo-256.png"))
    if not pm.isNull():
        logo.setPixmap(pm.scaled(84, 84, Qt.KeepAspectRatio,
                                 Qt.SmoothTransformation))
    header.addWidget(logo, 0, Qt.AlignVCenter)
    titles = QVBoxLayout()
    titles.setSpacing(2)
    title = QLabel("Yotathai Plan")
    title.setObjectName("title")
    sub = QLabel("เขียนแบบ 2 มิติ และขึ้นโมเดล 3 มิติ ในโปรแกรมเดียว — ฟรี สำหรับช่างไทย")
    sub.setObjectName("sub")
    sub.setWordWrap(True)
    titles.addStretch(1)
    titles.addWidget(title)
    titles.addWidget(sub)
    titles.addStretch(1)
    header.addLayout(titles, 1)
    root.addLayout(header)

    cards = QHBoxLayout()
    cards.setSpacing(16)
    cards.addWidget(_card(MODE_3D, "โมเดล 3 มิติ",
                          "ขึ้นรูป ดัน/ดึง วัดระยะ ถอดปริมาณ · IGZ / SKP",
                          lambda: choose(MODE_3D, None)), 1)
    cards.addWidget(_card(MODE_2D, "เขียนแบบ 2 มิติ",
                          "แปลน รูปด้าน รูปตัด แบบขออนุญาต · DWG / DXF",
                          lambda: choose(MODE_2D, None)), 1)
    root.addLayout(cards)

    actions = QHBoxLayout()
    actions.setSpacing(10)
    open_btn = QPushButton("เปิดไฟล์…")
    open_btn.setObjectName("open")
    open_btn.setCursor(Qt.PointingHandCursor)
    open_btn.setShortcut("Ctrl+O")

    def open_file():
        patterns = " ".join(f"*{e}" for e in EXT_2D + EXT_3D)
        path, _ = QFileDialog.getOpenFileName(
            window, "เปิดไฟล์", str(Path.home()),
            f"แบบและโมเดล ({patterns});;"
            f"แบบ 2 มิติ ({' '.join('*' + e for e in EXT_2D)});;"
            f"โมเดล 3 มิติ ({' '.join('*' + e for e in EXT_3D)})")
        if path:
            choose(mode_for(path), Path(path))
    open_btn.clicked.connect(open_file)
    actions.addWidget(open_btn)

    sample = QPushButton("🏠  ลองบ้านตัวอย่าง (3 มิติ)")
    sample.setObjectName("link")
    sample.setCursor(Qt.PointingHandCursor)
    sample.setToolTip("สร้างบ้านโมเดิร์นสองชั้นพร้อมสระว่ายน้ำไว้ลองเครื่องมือ "
                      "แล้วส่งเป็นแบบ 2 มิติได้จากเมนู 2D ⇄ 3D")
    sample.clicked.connect(lambda: _open_sample(window, choose))
    actions.addWidget(sample)
    actions.addStretch(1)
    hint = QLabel("ลากไฟล์มาวางที่หน้าต่างนี้ก็ได้")
    hint.setObjectName("foot")
    actions.addWidget(hint)
    root.addLayout(actions)

    recents = recent_by_mode()
    panes = QHBoxLayout()
    panes.setSpacing(16)
    window._recent_lists = {}            # tests read them
    for mode, title, empty in (
            (MODE_3D, "โมเดล 3 มิติล่าสุด",
             "ยังไม่มีโมเดล 3 มิติ — กด «โมเดล 3 มิติ» หรือ «ลองบ้านตัวอย่าง»"),
            (MODE_2D, "แบบ 2 มิติล่าสุด",
             "ยังไม่มีแบบ 2 มิติ — กด «เขียนแบบ 2 มิติ» หรือ «เปิดไฟล์…»")):
        col = QVBoxLayout()
        col.setSpacing(6)
        head = QLabel(title)
        head.setObjectName("head")
        head.setStyleSheet(f"color: {NAVY if mode == MODE_2D else ORANGE_DARK};")
        col.addWidget(head)
        lst = QListWidget()
        lst.setObjectName("recent")
        lst.setSelectionMode(QListWidget.SingleSelection)
        lst.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        for path, mtime in recents[mode]:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, (mode, str(path)))
            item.setToolTip(str(path))
            item.setSizeHint(QSize(100, 52))
            lst.addItem(item)
            lst.setItemWidget(item, _RecentRow.widget(mode, path, mtime))
        lst.itemActivated.connect(lambda it: choose(*_item_target(it)))
        lst.itemClicked.connect(lambda it: choose(*_item_target(it)))
        col.addWidget(lst, 1)
        note = QLabel(empty)
        note.setObjectName("foot")
        note.setWordWrap(True)
        col.addWidget(note)
        lst.setVisible(bool(recents[mode]))
        note.setVisible(not recents[mode])
        if not recents[mode]:
            col.addStretch(1)
        panes.addLayout(col, 1)
        window._recent_lists[mode] = lst
    root.addLayout(panes, 1)

    foot = QLabel("พัฒนาต่อจากโปรแกรมโอเพนซอร์ส IngeCAD 0.6.5 (2 มิติ) และ "
                  "IngeTrazo 0.5.8 (3 มิติ) · GPL-3.0 · ใช้งานได้ฟรี · โยธาไทย")
    foot.setObjectName("foot")
    root.addWidget(foot)


def _item_target(item):
    from PySide6.QtCore import Qt
    mode, path = item.data(Qt.UserRole)
    return mode, Path(path)


def _open_sample(window, choose) -> None:
    """Build (once) the sample modern house in ~/Documents/Yotathai and open
    it in 3D."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QMessageBox
    from yotathai.paths import DOCUMENTS
    target = DOCUMENTS / "modern-house.igz"
    if not target.exists():
        from yotathai.bridge import run_converter
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            run_converter("sample", [target])
        except Exception as exc:  # noqa: BLE001 — shown to the user
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(window, "Yotathai",
                                f"สร้างบ้านตัวอย่างไม่สำเร็จ\n\n{exc}")
            return
        QApplication.restoreOverrideCursor()
    choose(MODE_3D, target)


def _ui_font():
    from PySide6.QtGui import QFont, QFontDatabase
    families = set(QFontDatabase.families())
    for name in _FONTS:
        if name in families:
            f = QFont(name)
            f.setPointSizeF(13.5 if sys.platform == "darwin" else 10.0)
            return f
    return None


def run_home(files: list[str] | None = None, *, exec_engine=None,
             auto_quit_ms: int | None = None) -> int:
    """Show the home screen. ``exec_engine`` is replaceable for tests (the
    real one replaces this process and never returns)."""
    from PySide6.QtCore import QEvent, QSettings, QTimer, Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QWidget

    from yotathai import macos
    macos.set_app_name("Yotathai Plan")
    if exec_engine is None:
        from yotathai.__main__ import exec_engine as _real
        exec_engine = _real

    state = {"leaving": False}

    def choose(mode, path):
        if mode is None or state["leaving"]:
            return
        state["leaving"] = True
        win = getattr(app, "home_window", None)
        if win is not None:
            win.hide()
        app.processEvents()
        exec_engine(mode, [str(path)] if path else [], [])

    class _HomeApp(QApplication):
        def event(self, e):
            if e.type() == QEvent.Type.FileOpen:
                path = Path(e.file())
                choose(mode_for(path), path)
                return True
            return super().event(e)

    app = QApplication.instance() or _HomeApp(sys.argv[:1])
    app.setApplicationName("Yotathai")
    app.setOrganizationName("Yotathai")
    app.setStyle("Fusion")
    from PySide6.QtGui import QColor, QPalette
    pal = QPalette()
    for role, color in ((QPalette.Window, "#ffffff"), (QPalette.Base, "#ffffff"),
                        (QPalette.WindowText, INK), (QPalette.Text, INK),
                        (QPalette.Button, "#f6f6f4"), (QPalette.ButtonText, INK),
                        (QPalette.Highlight, ACCENT),
                        (QPalette.HighlightedText, "#ffffff")):
        pal.setColor(role, QColor(color))
    app.setPalette(pal)
    from yotathai import portable
    portable.load_qt_fonts()           # packaged fonts, no installation (portable only)
    font = _ui_font()
    if font is not None:
        app.setFont(font)
    icon = SRC_3D / "resources" / "branding" / "yotathai-3d-icon-1024.png"
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))

    class _Home(QWidget):
        def __init__(self):
            super().__init__()
            self.setAcceptDrops(True)

        def dragEnterEvent(self, e):  # noqa: N802 — Qt override
            if any(mode_for(u.toLocalFile()) for u in e.mimeData().urls()):
                e.acceptProposedAction()

        def dropEvent(self, e):  # noqa: N802 — Qt override
            for u in e.mimeData().urls():
                p = u.toLocalFile()
                if mode_for(p):
                    choose(mode_for(p), Path(p))
                    return

        def closeEvent(self, e):  # noqa: N802 — Qt override
            QSettings().setValue("home/geometry", self.saveGeometry())
            super().closeEvent(e)

    win = _Home()
    win.setWindowTitle("Yotathai Plan")
    win.setMinimumSize(780, 560)
    _build(win, choose)
    geo = QSettings().value("home/geometry")
    if geo is not None:
        win.restoreGeometry(geo)
    else:
        win.resize(880, 640)
    app.home_window = win

    # A cold launch by double-clicking a file delivers it as a FileOpen
    # event once the loop runs: wait a moment before showing the home
    # screen, so that case goes straight to the engine without a flash.
    def show():
        if not state["leaving"]:
            win.show()
            win.raise_()
            win.activateWindow()
    QTimer.singleShot(250, show)
    for f in files or []:
        if mode_for(f):
            QTimer.singleShot(0, lambda f=f: choose(mode_for(f), Path(f)))
            break
    if auto_quit_ms is not None:
        QTimer.singleShot(auto_quit_ms, app.quit)
    return app.exec()
