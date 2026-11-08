# SPDX-License-Identifier: GPL-3.0-or-later
# Yotathai 3D — shortcuts that work in any keyboard language.
"""Keyboard-layout independent shortcuts + a «which language am I typing» badge.

The problem (Thai users, but the same for Russian, Greek, Arabic, Hebrew,
Japanese kana…): a shortcut is bound to a Latin letter («L» = Line). With the
Thai layout selected the physical L key produces «ส», Qt matches nothing and
the user has to flip the language just to pick a tool.

The rule this module enforces, the same on macOS, Windows and Linux:

* focus is NOT in a text box  → the PHYSICAL key decides: the key printed «L»
  on a US keyboard is «L» whatever language is selected, so shortcuts, the
  measurement box (VCB: digits, ``m``/``cm``…) and tool keys all work;
* focus IS in a text box (a line edit, a spin box, a text area…) → the
  selected language decides, so Thai can be typed.

How: an application-wide event filter sees the key press only after Qt has
failed to match a shortcut (a Thai character matches nothing). It reads the
physical key from the native code (macOS virtual key / Windows scan code /
X11-Wayland keycode), rebuilds the Latin key event and replays it the way Qt
would: first a ShortcutOverride to the focus widget (a tool that claims the
key, a VCB in progress), then the window's actions and ``QShortcut``s, then a
plain key press. Layouts whose keys are already Latin (English, German,
French…) are never touched.

The badge in the status bar shows the language the keyboard is in now.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, QKeyCombination, QObject, QSettings, Qt, Signal
from PySide6.QtGui import QAction, QGuiApplication, QKeyEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QLabel, QLineEdit,
                               QPlainTextEdit, QTextEdit, QWidget)

from core.i18n import tr

_SETTING = "keyboard/layout_independent_shortcuts"

# --- physical key tables -----------------------------------------------------
# Characters are those of a US keyboard, i.e. what the key is NAMED in every
# shortcut list. Three families of native codes:

#: macOS ``kVK_ANSI_*`` virtual key codes (``QKeyEvent.nativeVirtualKey()``).
_MAC = {
    0: "a", 1: "s", 2: "d", 3: "f", 4: "h", 5: "g", 6: "z", 7: "x", 8: "c",
    9: "v", 11: "b", 12: "q", 13: "w", 14: "e", 15: "r", 16: "y", 17: "t",
    18: "1", 19: "2", 20: "3", 21: "4", 22: "6", 23: "5", 24: "=", 25: "9",
    26: "7", 27: "-", 28: "8", 29: "0", 30: "]", 31: "o", 32: "u", 33: "[",
    34: "i", 35: "p", 37: "l", 38: "j", 39: "'", 40: "k", 41: ";", 42: "\\",
    43: ",", 44: "/", 45: "n", 46: "m", 47: ".", 50: "`",
}


def _scan_set1() -> dict[int, str]:
    """Windows scan codes (set 1) of the main block; evdev numbers match."""
    table: dict[int, str] = {}
    for first, chars in ((0x02, "1234567890-="), (0x10, "qwertyuiop[]"),
                         (0x1E, "asdfghjkl;'`"), (0x2C, "zxcvbnm,./")):
        for i, ch in enumerate(chars):
            table[first + i] = ch
    table[0x2B] = "\\"
    return table


_SET1 = _scan_set1()

_SHIFTED = {"1": "!", "2": "@", "3": "#", "4": "$", "5": "%", "6": "^",
            "7": "&", "8": "*", "9": "(", "0": ")", "-": "_", "=": "+",
            "[": "{", "]": "}", ";": ":", "'": '"', "`": "~", "\\": "|",
            ",": "<", ".": ">", "/": "?"}

_PUNCT_KEY = {"-": Qt.Key_Minus, "=": Qt.Key_Equal, "[": Qt.Key_BracketLeft,
              "]": Qt.Key_BracketRight, ";": Qt.Key_Semicolon,
              "'": Qt.Key_Apostrophe, "`": Qt.Key_QuoteLeft,
              "\\": Qt.Key_Backslash, ",": Qt.Key_Comma, ".": Qt.Key_Period,
              "/": Qt.Key_Slash}

_SYMBOL_KEY = {sym: Qt.Key(ord(sym)) for sym in _SHIFTED.values()}

_CHORD_MASK = (Qt.ControlModifier | Qt.ShiftModifier | Qt.AltModifier
               | Qt.MetaModifier)


def physical_char(ev: QKeyEvent) -> str | None:
    """The US-keyboard character of the physical key behind ``ev``."""
    if sys.platform == "darwin":
        return _MAC.get(ev.nativeVirtualKey())
    scan = ev.nativeScanCode()
    if sys.platform.startswith("win"):
        return _SET1.get(scan) if 0 < scan < 0x100 else None
    return _SET1.get(scan - 8)        # X11 / Wayland: evdev + 8


def needs_remap(ev: QKeyEvent) -> bool:
    """True when the key came out as a NON-Latin character (Thai, Cyrillic,
    Greek, Arabic, Hebrew, kana…). Latin layouts (accents included), named
    keys (Space, Enter, arrows, F-keys…) and modifiers are left alone."""
    k = ev.key()
    if 0x250 <= k < 0x01000000:
        return True
    if k == Qt.Key_unknown or k == 0:
        text = ev.text()
        return bool(text) and ord(text[0]) >= 0x250
    return False


def latin_event_parts(ev: QKeyEvent):
    """``(qt_key, text)`` of the Latin key the user physically pressed, or
    ``None`` when the native code is unknown."""
    ch = physical_char(ev)
    if ch is None:
        return None
    shift = bool(ev.modifiers() & Qt.ShiftModifier)
    if ch.isalpha():
        key = Qt.Key(int(Qt.Key_A) + ord(ch) - ord("a"))
        return key, (ch.upper() if shift else ch)
    if ch.isdigit():
        return Qt.Key(int(Qt.Key_0) + int(ch)), (_SHIFTED[ch] if shift else ch)
    key = _PUNCT_KEY[ch]
    return key, (_SHIFTED[ch] if shift else ch)


def latin_key_for(ev: QKeyEvent) -> int:
    """Qt key for ``ev`` ignoring the language (for key-capture boxes):
    the event's own key when it is already Latin/named, else the physical one."""
    if needs_remap(ev):
        parts = latin_event_parts(ev)
        if parts:
            return int(parts[0])
    return ev.key()


def _combos(key: Qt.Key, text: str, mods) -> list[QKeyCombination]:
    """Every way a sequence may spell this press: ``Shift+1`` or ``!``."""
    mods = mods & _CHORD_MASK
    out = [QKeyCombination(mods, key)]
    if mods & Qt.ShiftModifier and text and text in _SYMBOL_KEY:
        out.append(QKeyCombination(mods & ~Qt.ShiftModifier, _SYMBOL_KEY[text]))
    return out


# --- what counts as «typing in a box» ----------------------------------------
def is_text_input(w: QWidget | None) -> bool:
    """True when the focus widget takes typed text, so the language the user
    picked must be honoured. Read-only boxes do not count (nothing to type)."""
    if w is None:
        return False
    if isinstance(w, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)):
        ro = getattr(w, "isReadOnly", None)
        return not (callable(ro) and ro())
    return False


class LayoutKeyFilter(QObject):
    """Application-wide filter described in the module docstring."""

    #: language code of the keyboard now ("th", "en", "ja"…)
    languageChanged = Signal(str)
    #: True while the focus is in a box that takes typed text
    typingChanged = Signal(bool)

    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self._busy = False
        self._typing = False
        self._lang = self._query_language()
        self.enabled = QSettings().value(_SETTING, True, type=bool)
        app.focusChanged.connect(self._on_focus)
        try:
            QGuiApplication.inputMethod().localeChanged.connect(self._on_locale)
        except Exception:                      # platform without the signal
            pass

    # ---- language bookkeeping ------------------------------------------------
    @staticmethod
    def _query_language() -> str:
        try:
            name = QGuiApplication.inputMethod().locale().name()
        except Exception:
            return "en"
        lang = name.split("_")[0].lower()
        return "en" if lang in ("", "c") else lang

    @property
    def language(self) -> str:
        return self._lang

    @property
    def typing(self) -> bool:
        return self._typing

    def set_language(self, lang: str) -> None:
        if lang != self._lang:
            self._lang = lang
            self.languageChanged.emit(lang)

    def _on_locale(self) -> None:
        self.set_language(self._query_language())

    def _on_focus(self, _old, new) -> None:
        typing = is_text_input(new)
        if typing != self._typing:
            self._typing = typing
            self.typingChanged.emit(typing)
        self._on_locale()                      # a refresh costs nothing

    def _learn_from_text(self, text: str) -> None:
        """Typed characters are the surest sign of the language in use, on
        platforms where the input-source change signal is late or missing."""
        if not text or not text[0].isalpha():
            return
        c = ord(text[0])
        if 0x0E00 <= c <= 0x0E7F:
            self.set_language("th")
        elif c < 0x250 and self._lang == "th":
            self.set_language("en")

    # ---- the filter ------------------------------------------------------------
    def eventFilter(self, obj, ev) -> bool:
        t = ev.type()
        if t not in (QEvent.KeyPress, QEvent.KeyRelease) or self._busy:
            return False
        if t == QEvent.KeyPress and ev.spontaneous():
            self._learn_from_text(ev.text())
        if not self.enabled or not needs_remap(ev):
            return False
        focus = QApplication.focusWidget()
        if focus is None or obj is not focus or is_text_input(focus):
            return False
        parts = latin_event_parts(ev)
        if parts is None:
            return False
        key, text = parts
        self._busy = True
        try:
            if t == QEvent.KeyPress:
                self._press(focus, ev, key, text)
            else:
                QApplication.sendEvent(focus, self._clone(ev, t, key, text))
        finally:
            self._busy = False
        return True

    @staticmethod
    def _clone(ev, etype, key, text) -> QKeyEvent:
        return QKeyEvent(etype, int(key), ev.modifiers(), ev.nativeScanCode(),
                         ev.nativeVirtualKey(), ev.nativeModifiers(), text,
                         ev.isAutoRepeat(), ev.count())

    def _press(self, focus, ev, key, text) -> None:
        # 1. Like Qt: let the focus widget claim the key (a tool that plays
        #    letters as keys, a measurement being typed).
        override = self._clone(ev, QEvent.ShortcutOverride, key, text)
        override.ignore()
        QApplication.sendEvent(focus, override)
        if override.isAccepted():
            QApplication.sendEvent(focus, self._clone(ev, QEvent.KeyPress, key, text))
            return
        # 2. The window's shortcuts (never on auto-repeat of a tool switch).
        if self._fire_shortcut(key, text, ev.modifiers()):
            return
        # 3. Nobody bound it: hand the plain Latin key over (P, arrows keep
        #    their direct handling in the viewport).
        QApplication.sendEvent(focus, self._clone(ev, QEvent.KeyPress, key, text))

    def _fire_shortcut(self, key, text, mods) -> bool:
        win = QApplication.activeWindow()
        if win is None:
            return False
        wanted = _combos(key, text, mods)

        def hit(seq: QKeySequence) -> bool:
            return seq.count() == 1 and any(
                seq[0].key() == c.key()
                and seq[0].keyboardModifiers() == c.keyboardModifiers()
                for c in wanted)

        ok_ctx = (Qt.WindowShortcut, Qt.ApplicationShortcut)
        for action in win.findChildren(QAction):
            if (action.isEnabled() and action.isVisible()
                    and action.shortcutContext() in ok_ctx
                    and any(hit(s) for s in action.shortcuts())):
                action.trigger()
                return True
        for sc in win.findChildren(QShortcut):
            if (sc.isEnabled() and sc.context() in ok_ctx and hit(sc.key())):
                sc.activated.emit()
                return True
        return False


_filter: LayoutKeyFilter | None = None


def get_filter() -> LayoutKeyFilter | None:
    """The one filter of the process, installed on first use."""
    global _filter
    app = QApplication.instance()
    if app is None:
        return None
    if _filter is None or _filter.parent() is not app:
        _filter = LayoutKeyFilter(app)
        app.installEventFilter(_filter)
    return _filter


# --- the badge ----------------------------------------------------------------
_NAMES = {"en": "EN", "th": "ไทย"}

_BADGE_TH = ("background:#F59E0B; color:#1F1300; font-weight:700;"
             "border-radius:8px; padding:1px 9px; margin:0 6px;")


class KeyboardLayoutBadge(QLabel):
    """Status-bar badge: the language the keyboard is in right now.

    Amber and bold when it is NOT Latin (that is when shortcuts used to fail
    and when a typed number would come out as a Thai digit), quiet otherwise.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self._lang = "en"
        self._typing = False
        flt = get_filter()
        if flt is not None:
            self._lang, self._typing = flt.language, flt.typing
            flt.languageChanged.connect(self._set_language)
            flt.typingChanged.connect(self._set_typing)
        self._refresh()

    def _set_language(self, lang: str) -> None:
        self._lang = lang
        self._refresh()

    def _set_typing(self, typing: bool) -> None:
        self._typing = typing
        self._refresh()

    def _refresh(self) -> None:
        name = _NAMES.get(self._lang, self._lang.upper())
        text = tr("Keyboard: {lang}", lang=name)
        if self._typing:
            text += tr(" (typing text)")
        self.setText(text)
        self.setToolTip(tr(
            "Keyboard language now: {lang}.\n"
            "Outside a text box the shortcut keys (L, M, O, 1-9…) work in "
            "every language — press the key, no need to switch.\n"
            "Inside a text box you type in the language shown here.",
            lang=name))
        if self._lang == "en":
            self.setStyleSheet("color:#6B7280; padding:0 8px;")
        else:
            self.setStyleSheet(_BADGE_TH)
