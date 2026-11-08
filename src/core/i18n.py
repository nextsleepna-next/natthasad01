# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marco Sumari Tellez and IngeTrazo contributors.
"""Lightweight JSON-based UI translation.

English is the *source* language: the keys passed to :func:`tr` are the English
strings themselves, so any untranslated string falls back to readable English
instead of a cryptic key. Other languages live as flat ``{english: translation}``
maps in ``i18n/<lang>.json`` (``i18n/en.json`` is the identity map, kept empty).

This deliberately avoids Qt's ``.ts``/``.qm`` + Linguist toolchain to stay
dependency-free, matching the project's minimal stack.

Usage::

    from core.i18n import tr
    label = tr("File")                       # -> "Archivo" in Spanish
    msg = tr("Imported {name}", name="a.obj")  # interpolates after lookup
"""
from __future__ import annotations

import json
from pathlib import Path

from core.paths import app_root

_I18N_DIR = app_root() / "i18n"

#: How each language names itself in the Language menu and Preferences.
LANGUAGE_NAMES = {"en": "English", "es": "Español",
                  "pt-BR": "Português (Brasil)", "zh-CN": "简体中文", "it": "Italiano",
                  "id": "Bahasa Indonesia", "fr": "Français", "de": "Deutsch",
                  "pl": "Polski", "ru": "Русский", "vi": "Tiếng Việt",
                  "lo": "ລາວ", "th": "ไทย",
                  "ja": "日本語", "ko": "한국어", "uk": "Українська",
                  "ar": "العربية"}

#: Languages written from right to left: the whole interface is mirrored
#: for them (see views/rtl.py). Arabic ships; the rest are ready for when
#: their catalogue comes.
RTL_LANGUAGES = frozenset({"ar", "he", "fa", "ur"})


def is_rtl(lang: str | None) -> bool:
    """Whether ``lang`` (``"ar"``, ``"fa-IR"``…) is written right to left."""
    return str(lang or "").split("-")[0].split("_")[0].lower() in RTL_LANGUAGES


#: The saved choice that follows the operating system's language (#818);
#: also what an unset choice means.
SYSTEM = "system"

_catalog: dict[str, str] = {}
_lang = "en"


#: Yotathai: the languages offered (menu, Preferences); ``None`` = every
#: catalog in ``i18n/``. The skin sets ``("en", "th")``.
OFFERED_LANGUAGES: tuple[str, ...] | None = None

#: Catalogues that ship but are not offered yet. Lao (#850) was here until
#: its marks composed on Windows (views/script_fonts.py, round 0.6.0).
HIDDEN_LANGUAGES: frozenset[str] = frozenset()


def available_languages() -> list[str]:
    """Language codes with a JSON file in ``i18n/`` (e.g. ``["en", "es"]``),
    less :data:`HIDDEN_LANGUAGES`."""
    if not _I18N_DIR.is_dir():
        return ["en"]
    codes = sorted(p.stem for p in _I18N_DIR.glob("*.json")
                   if p.stem not in HIDDEN_LANGUAGES)
    if OFFERED_LANGUAGES is not None:
        codes = [c for c in codes if c in OFFERED_LANGUAGES or c == "en"]
    return codes


#: Yotathai: show "ไทย (English)" for the glossary's ``pair`` terms. Off
#: here (tests and plain IngeTrazo see the catalog as it is); main.py turns
#: it on from the setting ``ui/paired_terms`` before :func:`set_language`.
_paired_terms = False


def set_paired_terms(on: bool) -> None:
    """Pair tool names and CAD terms with their English source (applies on
    the next :func:`set_language`)."""
    global _paired_terms
    _paired_terms = bool(on)


def glossary(lang: str) -> list[tuple[str, str, str]]:
    """``i18n/<lang>-terms.tsv`` as ``(english, mode, translation)`` rows:
    one place that fixes the words of the main tools and terms. ``mode`` is
    ``pair`` (translation + English), ``thai`` (translation only) or
    ``keep`` (the English source)."""
    path = _I18N_DIR / f"{lang}-terms.tsv"
    rows: list[tuple[str, str, str]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for line in lines:
        if not line.strip() or line.startswith("#"):
            continue
        cells = line.split("\t")
        if len(cells) < 2 or cells[1] not in ("pair", "thai", "keep"):
            continue
        rows.append((cells[0], cells[1], cells[2] if len(cells) > 2 else ""))
    return rows


def _apply_glossary(lang: str) -> None:
    for english, mode, word in glossary(lang):
        if mode == "keep":
            _catalog[english] = english
            continue
        if word:
            _catalog[english] = word
        if mode == "pair" and _paired_terms and english in _catalog:
            dots = "…" if english.endswith("…") else ""
            thai = _catalog[english].removesuffix("…")
            _catalog[english] = f"{thai} ({english.removesuffix('…')}){dots}"


def plain_term(text: str) -> str:
    """``text`` without the "(English)" a paired term carries — for a label
    under an icon, where the short word reads better."""
    if text.endswith(")") or text.endswith(")…"):
        cut = text.rfind(" (")
        if cut > 0:
            return text[:cut] + ("…" if text.endswith("…") else "")
    return text


def language_for_locales(locales) -> str:
    """The catalog that best serves ``locales`` — the system's UI
    languages, most preferred first (``["pt-PT", "en-US"]``).

    An exact tag wins, else the same base language: Portuguese from
    Portugal reads the Brazilian catalog, ``zh-Hans-CN`` the simplified
    Chinese one. The first locale with any match decides, so an English
    system stays English; nothing matching at all means English."""
    have = available_languages()
    by_tag = {code.lower(): code for code in have}
    by_base: dict[str, str] = {}
    for code in have:
        by_base.setdefault(code.lower().split("-")[0], code)
    for name in locales:
        tag = str(name).replace("_", "-").lower()
        found = by_tag.get(tag) or by_base.get(tag.split("-")[0])
        if found:
            return found
    return "en"


def resolve_language(choice: str | None) -> str:
    """The language code a saved ``choice`` runs in: itself, or for
    :data:`SYSTEM` (or no choice yet) the operating system's."""
    if choice and str(choice) != SYSTEM:
        return str(choice)
    from PySide6.QtCore import QLocale
    return language_for_locales(QLocale.system().uiLanguages())


def set_language(lang: str) -> None:
    """Activate ``lang`` for subsequent :func:`tr` calls.

    English (or a missing/broken file) loads an empty catalog, so ``tr`` returns
    the source string unchanged.
    """
    global _catalog, _lang
    _lang = lang or "en"
    path = _I18N_DIR / f"{_lang}.json"
    if _lang == "en" or not path.exists():
        _catalog = {}
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        _catalog = {str(k): str(v) for k, v in data.items()}
    except (OSError, ValueError):
        _catalog = {}
    _apply_glossary(_lang)


def current_language() -> str:
    return _lang


_reverse: dict[str, str] | None = None
_reverse_of: dict | None = None


def source_of(text: str) -> str:
    """The English source of a string ``tr`` produced — for a key that
    must not change with the language (a remembered keyboard shortcut).
    Text that is not a translation comes back as it is."""
    global _reverse, _reverse_of
    if _reverse_of is not _catalog:
        _reverse = {v: k for k, v in _catalog.items()}
        _reverse_of = _catalog
    return _reverse.get(text, text)


def tr(text: str, /, **kwargs) -> str:
    """Translate ``text`` into the active language; interpolate ``kwargs``.

    ``.format`` runs only when keyword arguments are given, so source strings
    that contain literal braces are safe when called without kwargs.
    """
    out = _catalog.get(text, text)
    if kwargs:
        try:
            out = out.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            out = text.format(**kwargs)
    return out
