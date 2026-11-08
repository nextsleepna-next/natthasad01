# SPDX-License-Identifier: GPL-3.0-or-later
"""``python -m yotathai.run_engine 2d|3d [--new-window] [file]`` — Windows
only way to start an engine (a Mac/Linux process becomes the engine through
``os.execv`` in ``yotathai/__main__.py`` instead).

The Windows embeddable Python reads ``pythonXY._pth`` and then behaves as in
isolated mode: the folder of a script is NOT put on ``sys.path``. Each
engine (``src/`` and ``ingecad-src/``) imports its own ``core`` package from
its own folder, so this stub puts that folder first, makes it the working
directory (the engines read resources relative to it) and runs ``main.py``
exactly as ``python main.py [file]`` would.
"""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from yotathai.paths import MODE_2D, MODE_3D, engine_dir


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in (MODE_2D, MODE_3D):
        print("usage: python -m yotathai.run_engine 2d|3d [--new-window] [file]",
              file=sys.stderr)
        return 2
    mode, rest = argv[0], argv[1:]
    from yotathai import portable
    portable.setup()          # settings/logs/temp in <app>/data when portable.flag exists
    folder = engine_dir(mode)
    os.environ.setdefault("YOTATHAI_FROM_HOME", "1")
    os.chdir(folder)
    sys.path.insert(0, str(folder))
    sys.argv = [str(folder / "main.py"), *rest]
    runpy.run_path(str(folder / "main.py"), run_name="__main__")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
