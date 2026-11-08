# SPDX-License-Identifier: GPL-3.0-or-later
"""Hand work from one engine to the other, and back to the home screen.

Qt-free on purpose: both engines import this (each with its own ``core``
package on ``sys.path``), so everything that needs the OTHER engine runs in
a child process — the converters, and the engine itself.

On a Mac inside Yotathai.app every launch goes through ``open -n -a
Yotathai.app``: the new window is then the same app to the Dock and to
Finder (one icon, the right name), not a stray Python process.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from yotathai.paths import (IS_WINDOWS, MODE_2D, MODE_3D, ROOT, bundle,
                            mode_for, python)

#: Windows process-creation flags (0 elsewhere, so callers can pass them
#: unconditionally): no console window, and detached from ours.
CREATE_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0
DETACHED = (0x00000008 | 0x00000200) if IS_WINDOWS else 0   # DETACHED_PROCESS | NEW_PROCESS_GROUP


#: The Windows interpreter reads ._pth and then ignores PYTHONUTF8 & co, so
#: UTF-8 mode (Thai paths and messages through pipes) is asked on the command line.
UTF8 = ["-X", "utf8"] if IS_WINDOWS else []


def log_path() -> Path:
    from yotathai import portable
    folder = Path.home() / "Library" / "Logs" / "Yotathai"
    if portable.is_portable():
        folder = portable.data_dir() / "logs"
    elif IS_WINDOWS:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        folder = Path(base) / "Yotathai" / "logs"
    elif sys.platform != "darwin":
        folder = Path.home() / ".cache" / "yotathai"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "yotathai.log"


def _child_env() -> dict:
    env = dict(os.environ)
    # The engine's own folder is on sys.path through its cwd, never through
    # PYTHONPATH: one engine's ``core`` must not leak into the other.
    env.pop("PYTHONPATH", None)
    env.pop("YOTATHAI_FROM_HOME", None)
    return env


def launch(mode: str | None = None, path=None, new_window: bool = False):
    """Open ``path`` in the engine for ``mode`` (picked from the file type
    when None) in a new Yotathai window; no mode and no path = the home
    screen. Returns the child process (tests wait on it) or None."""
    if mode is None and path is not None:
        mode = mode_for(path)
    args: list[str] = []
    if mode is not None:
        args += ["--mode", mode]
    if new_window:
        args.append("--new-window")
    if path is not None:
        args.append(str(Path(path).resolve()))
    app = bundle()
    if app is not None and sys.platform == "darwin":
        cmd = ["open", "-n", "-a", str(app), "--args", *args]
    elif IS_WINDOWS:
        cmd = [python(gui=True), *UTF8, "-m", "yotathai", *args]
    else:
        cmd = [python(), "-m", "yotathai", *args]
    extra = ({"creationflags": DETACHED | CREATE_NO_WINDOW} if IS_WINDOWS
             else {"start_new_session": True})
    with open(log_path(), "ab") as log:      # the child keeps its own copy
        return subprocess.Popen(cmd, cwd=str(ROOT), env=_child_env(),
                                stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                                **extra)


def open_in_2d(path) -> None:
    launch(MODE_2D, path)


def open_in_3d(path) -> None:
    launch(MODE_3D, path)


def go_home() -> None:
    launch()


def run_converter(module: str, args: list[str], timeout: float = 600) -> dict:
    """Run ``python -m yotathai.convert.<module> ... --json`` and return its
    report. A converter that fails raises RuntimeError with its message —
    the caller shows it to the user."""
    cmd = [python(), *UTF8, "-m", f"yotathai.convert.{module}",
           *map(str, args), "--json"]
    proc = subprocess.run(cmd, cwd=str(ROOT), env=_child_env(),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout,
                          creationflags=CREATE_NO_WINDOW)
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("{")]
    report = None
    if lines:
        try:
            report = json.loads(lines[-1])
        except ValueError:
            report = None
    if proc.returncode != 0 or report is None or not report.get("ok"):
        message = (report or {}).get("error") or proc.stderr.strip()[-800:] \
            or f"exit {proc.returncode}"
        raise RuntimeError(message)
    return report
