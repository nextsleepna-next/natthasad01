# SPDX-License-Identifier: GPL-3.0-or-later
"""Where everything lives, and which engine a file belongs to.

Pure stdlib: imported by the launcher before Qt, by both engines, and by
the converters running in a plain subprocess.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

#: The project root (holds src/, ingecad-src/, venv/, yotathai/).
ROOT = Path(__file__).resolve().parent.parent
SRC_3D = ROOT / "src"
SRC_2D = ROOT / "ingecad-src"
RESOURCES = Path(__file__).resolve().parent / "resources"

MODE_2D = "2d"
MODE_3D = "3d"

#: File types each engine opens. DXF/DWG are drawings (2D); the 3D engine
#: can still import them from its own File menu.
EXT_2D = (".dxf", ".dwg")
EXT_3D = (".igz", ".skp", ".dae")

IS_WINDOWS = sys.platform == "win32"


def _documents_folder() -> Path:
    """The user's real Documents folder. On Windows it may live in OneDrive
    (Known Folder Move), so ask the shell instead of assuming ~/Documents."""
    if IS_WINDOWS:
        try:
            import ctypes
            from ctypes import wintypes
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            # CSIDL_PERSONAL = 5, SHGFP_TYPE_CURRENT = 0
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 \
                    and buf.value:
                return Path(buf.value)
        except Exception:      # noqa: BLE001 — fall back to the home folder
            pass
    return Path.home() / "Documents"


#: Where models and drawings go when the source has no folder of its own
#: (an unsaved drawing): ASCII path, never inside the app.
DOCUMENTS = _documents_folder() / "Yotathai"

#: Fonts shipped inside a Windows install (``Yotathai\fonts``); the drawing
#: renderer and Qt are told about this folder at start-up.
BUNDLED_FONTS = ROOT / "fonts"


def python(gui: bool = False) -> str:
    """The interpreter both engines run on: the project venv when present
    (one venv for 2D and 3D since 2026-10-04), else this one.

    On Windows the install carries its own Python in ``<root>\\python``;
    ``gui=True`` asks for ``pythonw.exe`` (no black console window), the
    default for anything whose output is read (converters) is
    ``python.exe``."""
    if IS_WINDOWS:
        exe = "pythonw.exe" if gui else "python.exe"
        for base in (ROOT / "python", ROOT / "venv" / "Scripts"):
            if (base / exe).exists():
                return str(base / exe)
        return sys.executable
    venv = ROOT / "venv" / "bin" / "python"
    if venv.exists():
        return str(venv)
    return sys.executable


def mode_for(path) -> str | None:
    """Which engine opens ``path`` — None when neither does."""
    ext = Path(path).suffix.lower()
    if ext in EXT_2D:
        return MODE_2D
    if ext in EXT_3D:
        return MODE_3D
    return None


def engine_dir(mode: str) -> Path:
    return SRC_2D if mode == MODE_2D else SRC_3D


def bundle() -> Path | None:
    """The Yotathai.app this process was started from (the launcher script
    exports it), or None when run from a terminal."""
    raw = os.environ.get("YOTATHAI_BUNDLE", "")
    if raw and Path(raw).is_dir():
        return Path(raw)
    return None


def unique_path(path: Path) -> Path:
    """``path`` itself, or ``name-2.ext``, ``name-3.ext``… — never
    overwrite a model or drawing the user may have edited since."""
    path = Path(path)
    if not path.exists():
        return path
    for i in range(2, 1000):
        candidate = path.with_name(f"{path.stem}-{i}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(path)


def output_folder(source: Path | None) -> Path:
    """The source's own folder when we may write there, else
    ~/Documents/Yotathai."""
    if source is not None:
        folder = Path(source).parent
        if folder.is_dir() and os.access(folder, os.W_OK):
            return folder
    DOCUMENTS.mkdir(parents=True, exist_ok=True)
    return DOCUMENTS

