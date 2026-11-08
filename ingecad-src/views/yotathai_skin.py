# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Yotathai — on top of IngeCAD (Marco Sumari Tellez and contributors).
"""Yotathai look for IngeCAD: the same light, orange, Thai-font face as
Yotathai 3D, so the two engines read as one family.

IngeCAD is dark by design and several widgets carry their own dark
stylesheet, so besides the palette and an application stylesheet this
module re-maps those inline colours to light ones the moment a widget is
polished. Nothing upstream is edited except two calls in main.py.
Switch off with the setting ``yotathai/skin`` = ``0``.
"""
from __future__ import annotations

import re
import sys

from PySide6.QtCore import QEvent, QObject, QSettings, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette

ACCENT = "#E8772E"
ACCENT_DARK = "#C45F1A"
ACCENT_SOFT = "rgba(232, 119, 46, 0.16)"
INK = "#1f2328"

_FONTS = ["Sukhumvit Set", "Leelawadee UI", "Noto Sans Thai UI",
          "Noto Sans Thai", "Sarabun", "Thonburi", "Tahoma"]

#: Canvas colours: model space stays solid black (the CAD classic, what
#: every drafter's eye is used to), a light desk around the sheet, a faint
#: cream for the block editor. ACI 7 flips to white on black by itself
#: (core.window_colors).
_CANVAS = {"colors/model_background": "#000000",
           "colors/sheet_background": "#E4E4E0",
           "colors/block_editor_background": "#FBF5EC"}

#: Inline dark colours used across IngeCAD's widgets -> the light look.
_REMAP = [
    ("QLabel { color: #e8e8e8; }", "QLabel { color: %s; }" % INK),
    ("#1e1e22", "#ffffff"), ("#232327", "#f6f6f4"), ("#26262a", "#f4f4f2"),
    ("#2d2d31", "#ececea"), ("#2b2b2b", "#ffffff"), ("#a8a8a8", "#6b7380"),
    ("#d8d8d8", INK), ("#c8c8c8", "#2a2f36"), ("#b0b0b0", "#5a6472"),
    ("#3a3940", "#e4e4e0"), ("#4a4a52", "#c9c9c4"), ("#5a5a5a", "#c9c9c4"),
    ("#35424f", ACCENT), ("#2f3a45", ACCENT), ("#4a5a6a", ACCENT_DARK),
    ("#3d5063", ACCENT_DARK), ("#6a8aa8", ACCENT_DARK), ("#4a6480", ACCENT_DARK),
    ("#e8e8e8", "#ffffff"),
]
#: Widgets whose dark look is deliberate (the floating MText editor sits on
#: the drawing like AutoCAD's) keep it.
_KEEP_DARK = ("MTextInPlaceEditor",)


def branding_path(name: str):
    from core.paths import app_root
    return app_root() / "resources" / "branding" / name


def enabled() -> bool:
    return str(QSettings().value("yotathai/skin", "1")) != "0"


def lighten(sheet: str) -> str:
    out = sheet
    for a, b in _REMAP:
        out = re.sub(re.escape(a), b, out, flags=re.IGNORECASE)
    return out


def _light_palette() -> QPalette:
    window, text = QColor(242, 242, 239), QColor(INK)
    disabled = QColor(160, 160, 160)
    p = QPalette()
    p.setColor(QPalette.Window, window)
    p.setColor(QPalette.WindowText, text)
    p.setColor(QPalette.Base, QColor(255, 255, 255))
    p.setColor(QPalette.AlternateBase, QColor(247, 247, 245))
    p.setColor(QPalette.Text, text)
    p.setColor(QPalette.PlaceholderText, QColor(120, 124, 130))
    p.setColor(QPalette.Button, window)
    p.setColor(QPalette.ButtonText, text)
    p.setColor(QPalette.BrightText, QColor(200, 30, 30))
    p.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
    p.setColor(QPalette.ToolTipText, text)
    p.setColor(QPalette.Highlight, QColor(ACCENT))
    p.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.Link, QColor(26, 110, 190))
    p.setColor(QPalette.Light, QColor(255, 255, 255))
    p.setColor(QPalette.Midlight, QColor(0xD6, 0xD6, 0xD2))
    p.setColor(QPalette.Mid, QColor(0xB8, 0xB8, 0xB4))
    p.setColor(QPalette.Dark, QColor(0x9F, 0x9F, 0x9B))
    p.setColor(QPalette.Shadow, QColor(0x76, 0x76, 0x72))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText,
                 QPalette.HighlightedText):
        p.setColor(QPalette.Disabled, role, disabled)
    return p


STYLESHEET = """
QToolTip {{ background: palette(base); color: palette(text);
    border: 1px solid {accent}; border-radius: 6px; padding: 6px 8px; }}
QToolBar {{ background: palette(window); border: none; spacing: 3px; padding: 3px 4px; }}
QToolBar::separator {{ background: palette(mid); width: 1px; height: 1px; margin: 5px 4px; }}
QToolBar QToolButton {{ border: 1px solid transparent; border-radius: 7px; padding: 4px; margin: 1px; }}
QToolBar QToolButton:hover {{ background: {soft}; border: 1px solid {soft}; }}
QToolBar QToolButton:pressed, QToolBar QToolButton:checked {{ background: {soft}; border: 1px solid {accent}; }}
QMenuBar {{ background: palette(window); padding: 2px 4px; }}
QMenuBar::item {{ padding: 5px 10px; border-radius: 6px; }}
QMenuBar::item:selected {{ background: {soft}; }}
QMenu {{ background: palette(base); border: 1px solid palette(mid); border-radius: 8px; padding: 6px; }}
QMenu::item {{ padding: 6px 26px 6px 22px; border-radius: 6px; }}
QMenu::item:selected {{ background: {accent}; color: white; }}
QMenu::separator {{ height: 1px; background: palette(midlight); margin: 5px 8px; }}
QPushButton {{ background: palette(base); border: 1px solid palette(mid); border-radius: 7px;
    padding: 5px 12px; min-height: 18px; }}
QPushButton:hover {{ border: 1px solid {accent}; }}
QPushButton:pressed {{ background: {soft}; }}
QPushButton:default {{ border: 1px solid {accent}; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ background: palette(base);
    border: 1px solid palette(mid); border-radius: 6px; padding: 3px 6px; min-height: 18px;
    selection-background-color: {accent}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border: 1px solid {accent}; }}
QTabBar::tab {{ padding: 6px 12px; margin: 2px 1px; border-radius: 7px; background: transparent; }}
QTabBar::tab:selected {{ background: {accent}; color: white; }}
QTabBar::tab:hover:!selected {{ background: {soft}; }}
QHeaderView::section {{ background: palette(window); border: none;
    border-bottom: 1px solid palette(mid); padding: 4px 6px; font-weight: 600; }}
QTableView, QTreeView, QListView {{ selection-background-color: {accent}; selection-color: white; }}
QDockWidget::title {{ padding: 6px 8px; background: palette(window); border-bottom: 2px solid {accent}; }}
QScrollBar:vertical {{ width: 10px; background: transparent; margin: 2px; }}
QScrollBar:horizontal {{ height: 10px; background: transparent; margin: 2px; }}
QScrollBar::handle {{ background: palette(mid); border-radius: 4px; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background: {accent}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QStatusBar {{ background: palette(window); border-top: 1px solid palette(midlight); }}
"""


class _Lightener(QObject):
    """Re-maps a widget's own dark stylesheet the first time it is polished
    — catches the dialogs and panels built long after startup."""

    def eventFilter(self, obj, ev):  # noqa: N802 — Qt override
        if ev.type() == QEvent.Polish and hasattr(obj, "styleSheet"):
            try:
                sheet = obj.styleSheet()
            except RuntimeError:
                return False
            if (sheet and not obj.property("yt_lit")
                    and type(obj).__name__ not in _KEEP_DARK):
                new = lighten(sheet)
                obj.setProperty("yt_lit", True)
                if new != sheet:
                    obj.setStyleSheet(new)
        return False


_lightener = None


def _user_fonts() -> None:
    """Let the drawing renderer see fonts installed for this user only
    (~/Library/Fonts on a Mac, %LOCALAPPDATA%\\Microsoft\\Windows\\Fonts on
    Windows, and the ``fonts`` folder of a Windows install) — where a Thai
    font such as AA Pirun or Yotathai Drafting goes. ezdxf searches the
    system folders alone, so a drawing that names such a font fell back to
    another face. Rebuilds the font cache once when a folder has a font the
    cache has never seen."""
    import os
    try:                       # Yotathai Portable: packaged fonts for Qt and ezdxf
        from yotathai import portable
        portable.load_qt_fonts()
        portable.register_ezdxf_fonts()
    except Exception:          # noqa: BLE001
        pass
    try:
        import ezdxf
        from ezdxf.fonts import fonts
        folders = [os.path.expanduser("~/Library/Fonts")]
        local = os.environ.get("LOCALAPPDATA")
        if local:
            folders.append(os.path.join(local, "Microsoft", "Windows", "Fonts"))
        folders.append(os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))), "fonts"))
        folders = [f for f in folders if os.path.isdir(f)]
        if not folders:
            return
        dirs = list(ezdxf.options.support_dirs)
        ezdxf.options.support_dirs = dirs + [f for f in folders if f not in dirs]
        rebuild = False
        for folder in folders:
            names = [n for n in os.listdir(folder)
                     if n.lower().endswith((".ttf", ".otf"))]
            if any(fonts.find_font_face(n).filename != n for n in names[:20]):
                rebuild = True
        if rebuild:
            fonts.build_system_font_cache()
    except Exception:          # noqa: BLE001 — fonts never block startup
        pass


def apply_skin(app) -> None:
    """Call right after IngeCAD's own ``_apply_dark_theme(app)``."""
    global _lightener
    if not enabled():
        return
    st = QSettings()
    # Thai menus and the light canvas by default — once, so a user's own
    # later choice in Options stays theirs.
    if st.value("yotathai/defaults_set") is None:
        if st.value("language") is None:
            st.setValue("language", "th")
        for key, color in _CANVAS.items():
            if st.value(key) is None:
                st.setValue(key, color)
        st.setValue("yotathai/defaults_set", 1)

    _user_fonts()
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    app.setStyle("Fusion")
    app.setPalette(_light_palette())
    families = set(QFontDatabase.families())
    for name in _FONTS:
        if name in families:
            f = QFont(name)
            f.setPointSizeF(13.0 if sys.platform == "darwin" else 10.0)
            app.setFont(f)
            break

    # Painted toolbar icons: dark ink, orange accent (they were light-on-dark).
    from views import icons
    icons._STROKE = QColor("#2f3640")
    icons._ACCENT = QColor(ACCENT)
    icons._ACTION = icons._ACCENT
    # Module-level stylesheets read when their widgets are built.
    for mod, attr in (("views.command_line", "_STYLE"),
                      ("views.layers_panel", "_PANEL_STYLE")):
        try:
            m = __import__(mod, fromlist=[attr])
            setattr(m, attr, lighten(getattr(m, attr)))
        except Exception:      # noqa: BLE001 — a skin never blocks startup
            pass

    from PySide6.QtGui import QIcon
    icon = branding_path("yotathai-cad-icon-1024.png")
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))
    app.setStyleSheet(STYLESHEET.format(accent=ACCENT, soft=ACCENT_SOFT))
    _lightener = _Lightener(app)
    app.installEventFilter(_lightener)


def enhance_window(win) -> None:
    """Re-map anything already styled before the filter saw it."""
    if not enabled():
        return
    from PySide6.QtWidgets import QWidget
    for w in [win, *win.findChildren(QWidget)]:
        sheet = w.styleSheet()
        if sheet and type(w).__name__ not in _KEEP_DARK:
            new = lighten(sheet)
            if new != sheet:
                w.setStyleSheet(new)
