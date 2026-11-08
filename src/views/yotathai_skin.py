# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Yotathai — built on IngeTrazo (Marco Sumari Tellez and contributors).
"""Yotathai 3D skin: a friendlier face for local Thai builders.

Everything lives in this one module so the upstream code stays nearly
untouched (main.py calls :func:`apply_skin` and :func:`enhance_window`):

* a light theme by default, a Thai-friendly UI font and one construction
  indigo accent on warm paper greys (orange stays the 3D selection colour),
  through a single application stylesheet that reads the palette for its
  greys and is re-formatted on every theme change — light and dark;
* a «Basic tools» toolbar: the ten tools a beginner needs, with their
  name under the icon (the SAME QActions as the other toolbars, so the
  active tool stays in sync everywhere);
* a welcome screen at a bare start: new model, open, recent files, a
  sample house built in one click, and the trackpad / shortcut cheat sheet.

Switch it all off with the setting ``yotathai/skin`` = ``0``.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase

from core.i18n import tr

#: Indigo chrome (the logo navy's lighter sibling). Orange is NOT chrome any
#: more: it marks what is selected in the 3D view, so it never competes with
#: a button or a tab.
_TOKENS = {
    "light": dict(accent="#3A49A6", accent_dark="#28337A",
                  soft="rgba(58, 73, 166, 0.12)", accent_text="#3A49A6",
                  on_accent="#FFFFFF", title="#272c7e", sub="#6b7380"),
    "dark": dict(accent="#8D9AEB", accent_dark="#B3BCF3",
                 soft="rgba(141, 154, 235, 0.16)", accent_text="#B3BCF3",
                 on_accent="#16181E", title="#C9CFF7", sub="#9EA3B0"),
}

#: Warm paper greys (light) and cool slate (dark) laid over the stock palettes.
_PALETTE = {
    "light": {"Window": "#F1EFEA", "Button": "#F1EFEA", "Base": "#FFFFFF",
              "AlternateBase": "#F7F6F3", "WindowText": "#23262E",
              "Text": "#23262E", "ButtonText": "#23262E",
              "ToolTipBase": "#FFFFFF", "ToolTipText": "#23262E",
              "PlaceholderText": "#7A7F8A", "Highlight": "#3A49A6",
              "HighlightedText": "#FFFFFF", "Link": "#3A49A6",
              "Light": "#FFFFFF", "Midlight": "#DEDBD3", "Mid": "#C5C1B8",
              "Dark": "#A5A196", "Shadow": "#7A766C"},
    "dark": {"Window": "#272A34", "Button": "#272A34", "Base": "#1B1D24",
             "AlternateBase": "#22252E", "WindowText": "#E6E7EB",
             "Text": "#E6E7EB", "ButtonText": "#E6E7EB",
             "ToolTipBase": "#323643", "ToolTipText": "#E6E7EB",
             "Highlight": "#8D9AEB", "HighlightedText": "#16181E",
             "Link": "#A9B4F0", "Light": "#343846", "Midlight": "#323643",
             "Mid": "#3A3E4B", "Dark": "#1A1C22", "Shadow": "#0C0D10"},
}


def _tokens(dark: bool | None = None) -> dict:
    """Colour tokens for the palette in force (or for ``dark``)."""
    if dark is None:
        from PySide6.QtGui import QPalette
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        dark = (app is not None
                and app.palette().color(QPalette.Window).lightness() < 128)
    return _TOKENS["dark" if dark else "light"]


ACCENT = _TOKENS["light"]["accent"]
ACCENT_DARK = _TOKENS["light"]["accent_dark"]
ACCENT_SOFT = _TOKENS["light"]["soft"]

_KEY_SKIN = "yotathai/skin"
_KEY_WELCOME = "yotathai/show_welcome"
_KEY_THEME_SET = "yotathai/theme_defaulted"

#: The beginner's tools, in the order a first model is drawn.
BASIC_TOOLS = ["select", "line", "rectangle", "circle", "pushpull",
               "move", "rotate", "offset", "tape", "paint", "eraser"]

#: Thai UI fonts, best first: macOS, Windows, then the free Noto/Sarabun.
_FONTS = ["Sukhumvit Set", "Leelawadee UI", "Noto Sans Thai UI",
          "Noto Sans Thai", "Sarabun", "Thonburi", "Tahoma"]


def enabled() -> bool:
    return str(QSettings().value(_KEY_SKIN, "1")) != "0"


# ---- A: theme ---------------------------------------------------------------

def _ui_font() -> QFont | None:
    families = set(QFontDatabase.families())
    for name in _FONTS:
        if name in families:
            f = QFont(name)
            # A touch larger than the platform default: Thai vowels and
            # tone marks stack, and at 12-13 px they blur together.
            f.setPointSizeF(13.5 if sys.platform == "darwin" else 10.0)
            return f
    return None


STYLESHEET = """
/* ---------- Yotathai 3D (views/yotathai_skin.py) ---------- */
QToolTip {{
    background: palette(base); color: palette(text);
    border: 1px solid {accent}; border-radius: 6px; padding: 6px 8px;
}}

/* Toolbars: airy, rounded, the active tool in indigo */
QToolBar {{
    background: palette(window); border: none; spacing: 3px; padding: 3px 4px;
}}
QToolBar::separator {{
    background: palette(mid); width: 1px; height: 1px; margin: 5px 4px;
}}
QToolBar QToolButton {{
    border: 1px solid transparent; border-radius: 7px; padding: 4px;
    margin: 1px;
}}
QToolBar QToolButton:hover {{
    background: {soft}; border: 1px solid {soft};
}}
QToolBar QToolButton:pressed {{
    background: {soft}; border: 1px solid {accent_dark};
}}
QToolBar QToolButton:checked {{
    background: {soft}; border: 1px solid {accent};
}}

/* The «Basic tools» bar: labelled buttons, a little larger */
QToolBar#yt_basic QToolButton {{
    min-width: 58px; padding: 5px 4px 3px 4px; font-size: 12px;
}}
QToolBar#yt_basic QToolButton:checked {{
    background: {soft}; color: {accent_text}; border: 1px solid {accent};
}}

/* Menus */
QMenuBar {{ background: palette(window); padding: 2px 4px; }}
QMenuBar::item {{ padding: 5px 10px; border-radius: 6px; }}
QMenuBar::item:selected {{ background: {soft}; }}
QMenu {{
    background: palette(base); border: 1px solid palette(mid);
    border-radius: 8px; padding: 6px;
}}
QMenu::item {{ padding: 6px 26px 6px 22px; border-radius: 6px; }}
QMenu::item:selected {{ background: {soft}; color: {accent_text}; }}
QMenu::item:disabled {{ color: palette(mid); }}
QMenu::separator {{ height: 1px; background: palette(mid); margin: 5px 8px; }}

/* Buttons and fields */
QPushButton {{
    background: palette(button); border: 1px solid palette(mid);
    border-radius: 7px; padding: 5px 12px; min-height: 18px;
}}
QPushButton:hover {{ border: 1px solid {accent}; }}
QPushButton:pressed {{ background: {soft}; }}
QPushButton:default {{ border: 1px solid {accent}; }}
QPushButton:disabled {{ color: palette(mid); }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: palette(base); border: 1px solid palette(mid);
    border-radius: 6px; padding: 3px 6px; min-height: 18px;
    selection-background-color: {accent}; selection-color: {on_accent};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {accent};
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {accent}; border: 1px solid {accent_dark}; border-radius: 3px;
}}

/* Side panel: tabs and lists */
QTabBar::tab {{
    padding: 6px 12px; margin: 2px 1px; border-radius: 7px;
    background: transparent;
}}
QTabBar::tab:selected {{ background: {soft}; color: {accent_text}; font-weight: 600; }}
QTabBar::tab:hover:!selected {{ background: {soft}; }}
QHeaderView::section {{
    background: palette(window); border: none;
    border-bottom: 1px solid palette(mid); padding: 4px 6px; font-weight: 600;
}}
QTreeView, QListView, QTableView {{
    border: 1px solid palette(mid); border-radius: 6px;
    selection-background-color: {accent}; selection-color: {on_accent};
}}
QDockWidget::title {{
    padding: 6px 8px; background: palette(window);
    border-bottom: 2px solid {accent};
}}

/* Slim scrollbars */
QScrollBar:vertical {{ width: 10px; background: transparent; margin: 2px; }}
QScrollBar:horizontal {{ height: 10px; background: transparent; margin: 2px; }}
QScrollBar::handle {{ background: palette(mid); border-radius: 4px; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background: {accent}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* Status bar: the tool hint is the beginner's guide — make it readable */
QStatusBar {{ background: palette(window); border-top: 1px solid palette(mid); }}
QStatusBar QLabel {{ padding: 2px 6px; }}
"""


def apply_skin(app) -> None:
    """Theme, font and stylesheet. Call after ``views.theme.apply_theme``."""
    try:                               # Yotathai Portable: packaged fonts, nothing installed
        from yotathai import portable
        portable.load_qt_fonts()
    except Exception:      # noqa: BLE001 — fonts never block startup
        pass
    if not enabled():
        return
    global _applied
    _applied = True
    from core import i18n
    i18n.OFFERED_LANGUAGES = LANGUAGES
    from views import theme
    # One accent family for both palettes (selection, focus, icon details),
    # re-formatted into the stylesheet whenever the theme changes.
    from PySide6.QtGui import QPalette
    for mode in ("light", "dark"):
        theme.PALETTE_TWEAKS[mode] = {getattr(QPalette, role): QColor(hexv)
                                      for role, hexv in _PALETTE[mode].items()}
        theme.ICON_ACCENT[mode] = QColor(_TOKENS[mode]["accent"])
    theme._HIGHLIGHT = QColor(ACCENT)
    if _on_theme not in theme.ON_APPLIED:
        theme.ON_APPLIED.append(_on_theme)
    st = QSettings()
    # The light chrome is Yotathai's default; once only, so a user who
    # later picks dark in Preferences keeps it.
    if st.value(_KEY_THEME_SET) is None:
        from core import general_settings
        if general_settings.value("theme") is None:
            theme.save_theme(theme.LIGHT)
        st.setValue(_KEY_THEME_SET, 1)
    # The startup units question (IngeTrazo 0.5.8) is off by default: our
    # welcome screen already opens every bare start, and Thai work is in
    # metres. Preferences ▸ Units turns it back on; a user's choice stays.
    from views import units_start_dialog
    if st.value(units_start_dialog.ASK_KEY) is None:
        units_start_dialog.set_ask_at_start(False)
    # Bigger toolbar icons by default (32 px instead of 24): easier to hit
    # on a trackpad and to read. A size the user picked stays theirs.
    if st.value("ui/toolbar_icon_px") is None:
        st.setValue("ui/toolbar_icon_px", 32)
    theme.apply_theme(app)
    font = _ui_font()
    if font is not None:
        app.setFont(font)
    from PySide6.QtGui import QIcon
    icon = _branding("yotathai-3d-icon-1024.png")
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))


def _on_theme(app, dark: bool) -> None:
    """``theme.apply_theme`` just set the palette: format the stylesheet for it."""
    app.setStyleSheet(STYLESHEET.format(**_tokens(dark)))


# ---- Branding: logo, app icon, splash ---------------------------------------

def _branding(name: str) -> Path:
    from core.paths import app_root
    return app_root() / "resources" / "branding" / name


#: Set by :func:`apply_skin` — the running app wears this skin.
_applied = False


def restore_defaults(dialog) -> None:
    """Preferences ▸ «Restore defaults» (0.6.0) sets the controls the way a
    fresh profile gets them; under this skin a fresh profile is light, does
    not ask for units at start and has the bigger toolbar icons."""
    if not _applied:
        return
    from views import theme
    from views.icons import snap_toolbar_icon_px

    def pick(combo, data):
        combo.setCurrentIndex(max(0, combo.findData(data)))
    pick(dialog._theme, theme.LIGHT)
    dialog._units_at_start.setChecked(False)
    pick(dialog._icon_px, snap_toolbar_icon_px(32))


def show_splash(app):
    """The Yotathai elephant while the window builds (a few seconds on a
    big profile). Returns the splash; main.py calls ``finish(window)``."""
    if not enabled():
        return None
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QPainter, QPixmap
    from PySide6.QtWidgets import QSplashScreen
    from core.version import __version__
    w, h = 640, 380
    dpr = max(1.0, app.devicePixelRatio())
    pix = QPixmap(int(w * dpr), int(h * dpr))
    pix.setDevicePixelRatio(dpr)
    pix.fill(QColor("#ffffff"))
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.fillRect(QRectF(0, h - 10, w, 10), QColor(ACCENT))
    logo = QPixmap(str(_branding("yotathai-logo-512.png")))
    if not logo.isNull():
        p.drawPixmap(QRectF(40, 70, 220, 220), logo, QRectF(logo.rect()))
    base = app.font().family()
    f = QFont(base); f.setPixelSize(40); f.setBold(True)
    p.setFont(f); p.setPen(QColor("#272c7e"))
    p.drawText(QRectF(290, 95, 330, 54), Qt.AlignLeft | Qt.AlignVCenter, "Yotathai 3D")
    f = QFont(base); f.setPixelSize(17)
    p.setFont(f); p.setPen(QColor("#33373d"))
    p.drawText(QRectF(292, 152, 330, 60), Qt.AlignLeft | Qt.TextWordWrap,
               tr("3D modeling for Thai builders"))
    f = QFont(base); f.setPixelSize(13)
    p.setFont(f); p.setPen(QColor("#6b7380"))
    p.drawText(QRectF(292, 214, 330, 24), Qt.AlignLeft, f"{tr('Version')} {__version__}")
    p.setPen(QColor(ACCENT))
    p.drawText(QRectF(292, 250, 330, 24), Qt.AlignLeft, tr("Opening…"))
    p.setPen(QColor("#8a919b"))
    f = QFont(base); f.setPixelSize(11)
    p.setFont(f)
    p.drawText(QRectF(40, h - 40, w - 80, 20), Qt.AlignRight,
               tr("Built on IngeTrazo (GPL-3.0)"))
    p.end()
    splash = QSplashScreen(pix, Qt.WindowStaysOnTopHint)
    splash.setWindowTitle("Yotathai Plan")
    splash.show()
    app.processEvents()
    return splash


# ---- B: basic tools toolbar ---------------------------------------------------

def _add_basic_toolbar(win) -> None:
    from PySide6.QtWidgets import QToolBar
    actions = getattr(win, "_tool_actions", {})
    keys = [k for k in BASIC_TOOLS if k in actions]
    if not keys:
        return
    tb = QToolBar(tr("Basic tools"), win)
    tb.setObjectName("yt_basic")
    tb.setMovable(True)
    tb.setFloatable(True)
    from views.icons import toolbar_icon_px
    tb.setIconSize(QSize(toolbar_icon_px(), toolbar_icon_px()))   # same as every bar
    tb.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
    from core.i18n import plain_term
    for k in keys:
        act = actions[k]
        # Under the icon the short Thai word; the menus keep "ไทย (English)".
        act.setIconText(plain_term(act.text()))
        tb.addAction(act)                 # the same action: state stays in sync
        if k in ("select", "circle", "offset"):
            tb.addSeparator()
    ze = next((a for a in win.findChildren(type(actions[keys[0]]))
               if a.text() == tr("Zoom Extents")), None)
    if ze is not None:
        tb.addSeparator()
        ze.setIconText(plain_term(ze.text()))
        tb.addAction(ze)
    win.addToolBarBreak(Qt.TopToolBarArea)
    win.addToolBar(Qt.TopToolBarArea, tb)
    win.toolbars["yt_basic"] = tb
    tb.show()


# ---- B: welcome screen ----------------------------------------------------------

_SAMPLE_HOUSE = (
    "house(width=6.0, depth=4.0, wall_height=3.0, roof='gable', ridge='y', "
    "doors=[('S', 0.8, 0.9, 2.1)], "
    "windows=[('S', 3.5, 0.9, 1.5, 1.2), ('E', 1.5, 0.9, 1.0, 1.2)], "
    "name='" + "บ้านตัวอย่าง" + "', "
    "wall_color=(0.92, 0.89, 0.82), roof_color=(0.80, 0.42, 0.18), "
    "door_color=(0.45, 0.28, 0.15), glass_color=(0.60, 0.80, 0.95))"
)


def _shortcut_rows(win) -> list[tuple[str, str]]:
    """(key, tool name) read from the live actions — never typed by hand."""
    rows = []
    for k in BASIC_TOOLS:
        a = getattr(win, "_tool_actions", {}).get(k)
        if a is None:
            continue
        seq = a.shortcut().toString()
        if k == "select" and not seq:
            seq = "Space"
        if seq:
            rows.append((seq, a.text()))
    return rows


def show_welcome(win) -> None:
    from PySide6.QtWidgets import (QCheckBox, QDialog, QFrame, QGridLayout,
                                   QHBoxLayout, QLabel, QPushButton,
                                   QVBoxLayout)
    dlg = QDialog(win)
    dlg.setObjectName("yt_welcome")
    dlg.setWindowTitle(tr("Welcome to Yotathai Plan"))
    dlg.setMinimumWidth(760)
    tk = _tokens()
    ACCENT, ACCENT_DARK, ACCENT_SOFT = tk["accent"], tk["accent_dark"], tk["soft"]
    dlg.setStyleSheet(
        f"QDialog#yt_welcome {{ background: palette(base); }}"
        f"QLabel#yt_title {{ font-size: 26px; font-weight: 700; color: {tk['title']}; }}"
        f"QLabel#yt_sub {{ color: {tk['sub']}; font-size: 13px; }}"
        f"QLabel#yt_head {{ font-size: 14px; font-weight: 700; color: {ACCENT}; }}"
        f"QPushButton#yt_big {{ text-align: left; padding: 12px 14px; font-size: 14px;"
        f"  border-radius: 10px; }}"
        f"QPushButton#yt_primary {{ text-align: left; padding: 12px 14px; font-size: 14px;"
        f"  border-radius: 10px; background: {ACCENT}; color: {tk['on_accent']}; border: 1px solid {ACCENT_DARK}; }}"
        f"QPushButton#yt_primary:hover {{ background: {ACCENT_DARK}; }}"
        f"QPushButton#yt_recent {{ text-align: left; padding: 6px 10px; border: none;"
        f"  background: transparent; color: palette(text); }}"
        f"QPushButton#yt_recent:hover {{ background: {ACCENT_SOFT}; }}"
        f"QFrame#yt_card {{ background: palette(window); border-radius: 12px; }}"
        f"QLabel#yt_key {{ background: palette(base); border: 1px solid palette(mid);"
        f"  border-radius: 5px; padding: 1px 7px; font-weight: 600; }}")
    root = QVBoxLayout(dlg)
    root.setContentsMargins(26, 22, 26, 18)
    root.setSpacing(12)

    from PySide6.QtGui import QPixmap
    header = QHBoxLayout()
    header.setSpacing(16)
    logo = QLabel()
    pm = QPixmap(str(_branding("yotathai-logo-256.png")))
    if not pm.isNull():
        logo.setPixmap(pm.scaled(88, 88, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    header.addWidget(logo, 0, Qt.AlignVCenter)
    titles = QVBoxLayout()
    titles.setSpacing(2)
    title = QLabel("Yotathai 3D")
    title.setObjectName("yt_title")
    sub = QLabel(tr("Free 3D modeling for Thai builders — draw, push/pull, "
                    "measure and take off quantities."))
    sub.setObjectName("yt_sub")
    sub.setWordWrap(True)
    titles.addStretch(1)
    titles.addWidget(title)
    titles.addWidget(sub)
    titles.addStretch(1)
    header.addLayout(titles, 1)
    root.addLayout(header)

    cols = QHBoxLayout()
    cols.setSpacing(16)
    root.addLayout(cols, 1)

    # left: start
    left = QVBoxLayout()
    left.setSpacing(8)
    head = QLabel(tr("Start"))
    head.setObjectName("yt_head")
    left.addWidget(head)

    def big(text, slot, primary=False):
        b = QPushButton(text)
        b.setObjectName("yt_primary" if primary else "yt_big")
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(slot)
        left.addWidget(b)
        return b

    def new_model():
        dlg.accept()

    def open_file():
        dlg.accept()
        win._on_open()

    def sample_house():
        dlg.accept()
        from core.ai import run_transactional
        run_transactional(win.viewport, _SAMPLE_HOUSE, {})
        win._on_zoom_extents()

    big("＋  " + tr("New model"), new_model, primary=True)
    big("📂  " + tr("Open a file…"), open_file)
    big("🏠  " + tr("Build a sample house (to try the tools)"), sample_house)

    recent = [p for p in win._recent_paths() if Path(p).exists()][:5]
    if recent:
        rh = QLabel(tr("Recent files"))
        rh.setObjectName("yt_head")
        left.addSpacing(6)
        left.addWidget(rh)
        for p in recent:
            b = QPushButton(Path(p).name)
            b.setObjectName("yt_recent")
            b.setToolTip(p)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c=False, path=p: (
                dlg.accept(), win.open_path(Path(path))))
            left.addWidget(b)
    left.addStretch(1)
    cols.addLayout(left, 1)

    # right: how to drive it
    card = QFrame()
    card.setObjectName("yt_card")
    cv = QVBoxLayout(card)
    cv.setContentsMargins(16, 14, 16, 14)
    cv.setSpacing(6)
    h1 = QLabel(tr("Trackpad"))
    h1.setObjectName("yt_head")
    cv.addWidget(h1)
    grid = QGridLayout()
    grid.setHorizontalSpacing(12)
    grid.setVerticalSpacing(5)
    gestures = [
        (tr("Two-finger drag"), tr("Orbit")),
        (tr("Shift + two-finger drag"), tr("Pan")),
        (tr("Pinch"), tr("Zoom")),
        (tr("Middle mouse drag"), tr("Orbit (mouse)")),
    ]
    for r, (g, what) in enumerate(gestures):
        kl = QLabel(g)
        kl.setObjectName("yt_key")
        grid.addWidget(kl, r, 0, Qt.AlignLeft)
        grid.addWidget(QLabel(what), r, 1)
    cv.addLayout(grid)
    cv.addSpacing(8)
    h2 = QLabel(tr("Keyboard shortcuts"))
    h2.setObjectName("yt_head")
    cv.addWidget(h2)
    grid2 = QGridLayout()
    grid2.setHorizontalSpacing(12)
    grid2.setVerticalSpacing(5)
    rows = _shortcut_rows(win)
    half = (len(rows) + 1) // 2
    for i, (key, name) in enumerate(rows):
        r, c = (i, 0) if i < half else (i - half, 2)
        kl = QLabel(key)
        kl.setObjectName("yt_key")
        grid2.addWidget(kl, r, c, Qt.AlignLeft)
        grid2.addWidget(QLabel(name), r, c + 1)
    cv.addLayout(grid2)
    cv.addStretch(1)
    cols.addWidget(card, 1)

    foot = QHBoxLayout()
    again = QCheckBox(tr("Show this screen at start"))
    again.setChecked(str(QSettings().value(_KEY_WELCOME, "1")) != "0")
    again.toggled.connect(lambda on: QSettings().setValue(_KEY_WELCOME, "1" if on else "0"))
    foot.addWidget(again)
    foot.addStretch(1)
    credit = QLabel(tr("Built on IngeTrazo (GPL-3.0)"))
    credit.setObjectName("yt_sub")
    foot.addWidget(credit)
    root.addLayout(foot)
    dlg.exec()


#: The languages Yotathai 3D offers (the other catalogs stay in the source
#: tree, untouched, so upstream merges stay clean).
LANGUAGES = ("en", "th")
_KEY_PAIRED = "ui/paired_terms"


def _tune_language_menu(win) -> None:
    """Language menu: «show English beside Thai» (the glossary
    ``i18n/th-terms.tsv``; applies from the next start). English and Thai
    only is :data:`core.i18n.OFFERED_LANGUAGES`, set in :func:`apply_skin`."""
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QMenu, QMessageBox
    menu = next((m for m in win.findChildren(QMenu)
                 if m.title().replace("&", "") == tr("Language")), None)
    if menu is None:
        return
    menu.addSeparator()
    pair = QAction(tr("Show English names beside Thai"), menu)
    pair.setCheckable(True)
    pair.setChecked(str(QSettings().value(_KEY_PAIRED, "1")) != "0")
    pair.setStatusTip(tr("Tool names and terms as «ดัน / ดึง (Push / Pull)», "
                         "to follow English tutorials. From the next start."))

    def toggled(on: bool) -> None:
        QSettings().setValue(_KEY_PAIRED, "1" if on else "0")
        QMessageBox.information(win, tr("Language changed"),
                                tr("Restart IngeTrazo to apply the new language."))
    pair.toggled.connect(toggled)
    menu.addAction(pair)


def _hide_upstream_documentation(win) -> None:
    """Help ▸ Documentation (0.6.0) opens the base program's online manual
    (English, under its own name): hidden here — คุณช่างถึก 4 พ.ย. 2569.
    Hidden actions also stay out of the command search."""
    from PySide6.QtGui import QAction
    tip = tr("Open the IngeTrazo documentation in the web browser.")
    for action in win.findChildren(QAction):
        if action.statusTip() == tip:
            action.setVisible(False)


def enhance_window(win, opened_document: bool) -> None:
    """Basic toolbar now; the welcome screen once the window is up (only
    for a bare start, and only while the user wants it)."""
    if not enabled():
        return
    try:
        _add_basic_toolbar(win)
    except Exception:          # noqa: BLE001 — a skin must never block startup
        pass
    try:
        _tune_language_menu(win)
    except Exception:          # noqa: BLE001
        pass
    try:
        _hide_upstream_documentation(win)
    except Exception:          # noqa: BLE001
        pass
    if opened_document or str(QSettings().value(_KEY_WELCOME, "1")) == "0":
        return
    from PySide6.QtCore import QTimer
    QTimer.singleShot(350, lambda: show_welcome(win))
