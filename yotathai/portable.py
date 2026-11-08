# SPDX-License-Identifier: GPL-3.0-or-later
"""Yotathai Portable: run from an unzipped folder (or a pen drive) with
nothing installed and nothing written to the registry.

The mode is switched on by an empty file ``portable.flag`` in the app
folder (``paths.ROOT``, next to ``python/``). Without it every function here
does nothing, so the Mac app and the installed Windows build are untouched.

What it does when on:

* settings: ``QSettings`` become INI files in ``<data>/settings`` (no registry);
* logs, temp files, auto-save, texture / map caches live in ``<data>``;
* fonts: ``<app>/fonts`` is loaded into Qt (``QFontDatabase``) and into
  ezdxf's font manager, so the fonts need no installation.

``<data>`` is ``<app>/data``; when that folder cannot be written (Program
Files, a write-protected drive) it falls back to ``%LOCALAPPDATA%\\Yotathai\\data``.

Pure stdlib at import time (Qt/ezdxf are imported lazily); the launcher
imports it before Qt.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from yotathai import paths

FLAG_NAME = "portable.flag"
ENV_DATA = "YOTATHAI_DATA_DIR"        # inherited by the engines (see their autosave / log code)
FONT_SUFFIXES = (".ttf", ".otf")
SUBDIRS = ("settings", "logs", "tmp", "autosave", "cache", "textures")


def flag_file() -> Path:
    return paths.ROOT / FLAG_NAME


def is_portable() -> bool:
    return flag_file().is_file()


def fonts_dir() -> Path:
    """The fonts shipped in the package (``<app>/fonts``)."""
    return paths.ROOT / "fonts"


def _writable(folder: Path) -> bool:
    """True when files can really be created in ``folder`` (os.access lies
    on read-only drives and locked folders). Reuses one probe file."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with open(folder / ".write-test", "w", encoding="ascii") as f:
            f.write("ok")
        return True
    except OSError:
        return False


def _fallback_base() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        local = str(Path.home() / "AppData" / "Local")
    return Path(local) / "Yotathai" / "data"


def data_dir() -> Path:
    """The writable data folder; a child process inherits the parent's
    choice through ``YOTATHAI_DATA_DIR`` so both agree."""
    chosen = os.environ.get(ENV_DATA)
    if chosen and Path(chosen).is_dir():
        return Path(chosen)
    for candidate in (paths.ROOT / "data", _fallback_base()):
        if _writable(candidate):
            return candidate
    import tempfile
    return Path(tempfile.gettempdir()) / "Yotathai-data"      # last resort


_done: Path | None = None


def setup() -> Path | None:
    """Switch the process to portable storage. Idempotent; returns the data
    folder, or None when this is not a portable run. Call before the first
    ``QSettings`` / ``ezdxf`` use."""
    global _done
    if not is_portable():
        return None
    data = data_dir()
    if _done == data:
        return data
    for name in SUBDIRS:
        try:
            (data / name).mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    os.environ["YOTATHAI_PORTABLE"] = "1"
    os.environ[ENV_DATA] = str(data)
    os.environ["XDG_CACHE_HOME"] = str(data / "cache")          # ezdxf font cache
    os.environ["INGETRAZO_TEXTURE_CACHE"] = str(data / "textures")
    for var in ("TMP", "TEMP", "TMPDIR"):
        os.environ[var] = str(data / "tmp")
    import tempfile
    tempfile.tempdir = None                                      # re-read the env
    try:
        from PySide6.QtCore import QSettings
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope,
                          str(data / "settings"))
    except Exception:          # noqa: BLE001 — Qt missing: nothing to redirect
        pass
    _done = data
    return data


def font_files() -> list[Path]:
    folder = fonts_dir()
    if not folder.is_dir():
        return []
    return sorted(f for f in folder.iterdir()
                  if f.is_file() and f.suffix.lower() in FONT_SUFFIXES)


def load_qt_fonts() -> list[str]:
    """Register the packaged fonts with Qt (needs a QGuiApplication).
    Returns the family names that became available. Does nothing unless
    portable."""
    if not is_portable():
        return []
    from PySide6.QtGui import QFontDatabase
    families: list[str] = []
    for f in font_files():
        fid = QFontDatabase.addApplicationFont(str(f))
        if fid >= 0:
            for fam in QFontDatabase.applicationFontFamilies(fid):
                if fam not in families:
                    families.append(fam)
    return families


def register_ezdxf_fonts() -> int:
    """Teach ezdxf's font manager the packaged fonts (drawing and PDF
    output name them by file, e.g. ``YotathaiDrafting-Regular.ttf``). They
    are added in memory at every start: cheap, and independent of any font
    cache on disk. Returns how many files were added. Does nothing unless
    portable."""
    if not is_portable():
        return 0
    try:
        import ezdxf
        from ezdxf.fonts import fonts
    except Exception:          # noqa: BLE001
        return 0
    folder = fonts_dir()
    if not folder.is_dir():
        return 0
    dirs = list(ezdxf.options.support_dirs)
    if str(folder) not in dirs:
        ezdxf.options.support_dirs = dirs + [str(folder)]
    fonts.font_manager.scan_all([str(folder)])
    return len(font_files())


def log_dir() -> Path | None:
    return data_dir() / "logs" if is_portable() else None
