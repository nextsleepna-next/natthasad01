# SPDX-License-Identifier: GPL-3.0-or-later
"""Which Yotathai 3D window has which file open — and a way to tell it.

Qt-free on purpose (``scripts/yotathai_ai open`` and the bridge use it
without loading an engine). Each 3D window keeps one small JSON file here
while it runs: ``{"pid", "path", "server"}``, where ``server`` is the name
of the window's own local socket (``views/live_reload.py`` listens on it).
``request_reload`` finds a live window on the same file and asks it to come
to the front and read the file again — so an AI that rebuilt the model in
the background does not open a second window for a file already on screen.
"""
from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path


def registry_dir() -> Path:
    from yotathai import portable
    if portable.is_portable():
        folder = portable.data_dir() / "live"
    elif sys.platform == "darwin":
        folder = Path.home() / "Library" / "Caches" / "Yotathai" / "live"
    elif sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        folder = Path(base) / "Yotathai" / "live"
    else:
        folder = Path.home() / ".cache" / "yotathai" / "live"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _entry_file(pid: int) -> Path:
    return registry_dir() / f"{pid}.json"


def same_file(a, b) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def register(path, server: str, pid: int | None = None) -> None:
    """Record this window's file (``None`` = no file yet) and socket."""
    pid = pid or os.getpid()
    data = {"pid": pid, "path": str(path) if path else "", "server": server}
    target = _entry_file(pid)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, target)


def unregister(pid: int | None = None) -> None:
    """Drop this window's record (a runtime marker, made again on every start)."""
    try:
        _entry_file(pid or os.getpid()).unlink(missing_ok=True)
    except OSError:
        pass


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def windows() -> list[dict]:
    """Records of the windows that are still running."""
    out = []
    for f in registry_dir().glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            pid = int(data["pid"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if _alive(pid):
            out.append(data)
    return out


def request_reload(path, timeout: float = 5.0) -> bool:
    """Ask a running window that has ``path`` open to raise itself and read
    the file again. True when one answered; False = open a new window."""
    if sys.platform == "win32":          # named pipes: not wired, open as before
        return False
    for data in windows():
        if not data.get("path") or not data.get("server"):
            continue
        if not same_file(data["path"], path):
            continue
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect(data["server"])
            sock.sendall(("reload\t" + str(Path(path).resolve()) + "\n").encode("utf-8"))
            if sock.recv(64).startswith(b"ok"):
                return True
        except OSError:
            continue
        finally:
            sock.close()
    return False
