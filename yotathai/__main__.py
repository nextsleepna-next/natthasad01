# SPDX-License-Identifier: GPL-3.0-or-later
"""``python -m yotathai [--mode 2d|3d] [--new-window] [file ...]``

The one entry point of Yotathai.app:

* a file (DXF/DWG -> 2D, IGZ/SKP -> 3D) or ``--mode`` -> become that
  engine right away (``os.execv``: same process, so the Dock keeps one icon
  and macOS keeps sending this process its "open file" events);
* nothing -> the home screen, which becomes the engine the user picks
  (or the one a file double-clicked in Finder belongs to).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

if __package__ in (None, ""):          # run as a script: make the package importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from yotathai.paths import MODE_2D, MODE_3D, engine_dir, mode_for, python


def parse(argv: list[str]):
    mode, files, flags = None, [], []
    it = iter(argv)
    for a in it:
        if a == "--mode":
            mode = next(it, None)
        elif a.startswith("--mode="):
            mode = a.split("=", 1)[1]
        elif a == "--new-window":
            flags.append(a)
        elif a.startswith("-psn_"):     # old macOS process serial number
            continue
        elif a.startswith("-"):
            flags.append(a)
        else:
            files.append(a)
    if mode not in (None, MODE_2D, MODE_3D):
        mode = None
    return mode, files, flags


def exec_engine(mode: str, files: list[str], flags: list[str] = ()) -> None:
    """Replace this process with the engine. Does not return."""
    keep = [f for f in files if mode_for(f) in (mode, None)]
    other = [f for f in files if mode_for(f) not in (mode, None)]
    if other:                       # mixed drop: the rest opens beside us
        from yotathai.bridge import launch
        for f in other:
            launch(None, f)
    engine_flags = [f for f in flags if f == "--new-window" and mode == MODE_3D]
    os.environ["YOTATHAI_FROM_HOME"] = "1"
    if sys.platform == "win32":
        return _spawn_engine_windows(mode, keep[:1], engine_flags)
    os.chdir(engine_dir(mode))
    exe = python()
    sys.stdout.flush()
    sys.stderr.flush()
    os.execv(exe, [exe, "main.py", *keep[:1], *engine_flags])


def _spawn_engine_windows(mode: str, files: list[str], flags: list[str]) -> None:
    """Windows has no real exec: os.execv starts a new process and the
    parent just ends, handing the caller a meaningless exit code. So start
    the engine ourselves (``yotathai.run_engine``: the embedded Python does
    not put a script's folder on sys.path) and leave. Does not return."""
    import subprocess
    from yotathai.bridge import CREATE_NO_WINDOW, DETACHED, UTF8, log_path
    from yotathai.paths import ROOT
    cmd = [python(gui=True), *UTF8, "-m", "yotathai.run_engine", mode,
           *files, *flags]
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    with open(log_path(), "ab") as log:
        subprocess.Popen(cmd, cwd=str(ROOT), env=env, stdout=log, stderr=log,
                         stdin=subprocess.DEVNULL,
                         creationflags=DETACHED | CREATE_NO_WINDOW)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:          # noqa: BLE001 — pythonw has no streams
            pass
    os._exit(0)


def main(argv: list[str]) -> int:
    from yotathai import portable
    portable.setup()                    # no-op unless portable.flag is next to python/
    mode, files, flags = parse(argv)
    files = [str(Path(f).expanduser().resolve()) for f in files]
    if mode is None and files:
        mode = mode_for(files[0])
    if mode is not None:
        exec_engine(mode, files, flags)
        return 0                        # only reached when exec is stubbed (tests)
    from yotathai.home import run_home
    return run_home(files)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
