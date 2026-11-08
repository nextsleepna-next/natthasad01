# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Yotathai — built on IngeTrazo (Marco Sumari Tellez and contributors).
"""Live reload: the model on screen follows the file on disk.

An AI (or any other program) may rebuild the ``.igz`` a window has open.
Instead of a second window, this window reads the file again:

* nothing unsaved here -> it reloads by itself, keeping the camera, the
  hidden layers and the hidden objects, and says so in the status bar;
* unsaved edits here -> it never overwrites them: a button in the status
  bar offers the reload (the edits it throws away are first put in the
  recoverable auto-save folder);
* the window's own saves are not outside edits: ``mark_synced`` records
  the file as it was just read or written.

Each window also listens on its own local socket (registered through
``yotathai.live``) so ``yotathai_ai open FILE`` can raise this window
instead of starting another.
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QObject, QFileSystemWatcher, QTimer
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import QApplication, QPushButton


#: Quiet time before the file is looked at; it must then show the same
#: size and time on two looks in a row (the writer is done) to be read.
SETTLE_MS = 800
#: A safety net for file systems whose change events get lost (cloud drives).
POLL_MS = 3000


def _signature(path: Path | None):
    """(mtime_ns, size) of ``path``; None when it is not there."""
    try:
        st = os.stat(path)
    except (OSError, TypeError):
        return None
    return (st.st_mtime_ns, st.st_size)


class LiveReload(QObject):
    def __init__(self, window) -> None:
        super().__init__(window)
        self.window = window
        self._path: Path | None = None
        self._synced = None            # the file's signature when we last read/wrote it
        self._known: dict = {}         # projects in tabs (0.6.0): the same, per file left behind
        self._looked = None            # the signature seen by the last settle look
        self._button: QPushButton | None = None
        self._shell = None             # yotathai.live, when this is a Yotathai tree

        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._on_event)
        self._watcher.directoryChanged.connect(self._on_event)
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(SETTLE_MS)
        self._settle.timeout.connect(self._settled)
        self._poll = QTimer(self)
        self._poll.setInterval(POLL_MS)
        self._poll.timeout.connect(self._on_event)
        self._poll.start()
        self._listen()
        self.follow_document()
        self._register()

    # ---- which file ------------------------------------------------------
    def _document(self) -> Path | None:
        w = self.window
        if getattr(w, "_workspace", None) is not None:
            return self._path           # a side workspace: keep watching the parked model
        path = getattr(w, "_current_path", None)
        if path is None or Path(path).suffix.lower() != ".igz":
            return None
        return Path(path)

    def follow_document(self) -> None:
        """The window's document changed (opened, saved as, new): watch that file."""
        path = self._document()
        if path == self._path:
            return
        old = self._watcher.files() + self._watcher.directories()
        if old:
            self._watcher.removePaths(old)
        if self._path is not None:
            # Another tab came to the front: remember what this one has read,
            # so a rewrite while it waits in the back is still seen.
            self._known[self._path] = self._synced
        self._path = path
        stale = path is not None and path in self._known
        self._synced = self._known.pop(path) if stale else _signature(path)
        self._looked = None
        self._settle.stop()
        self._hide_button()
        self._rewatch()
        self._register()
        if stale:
            self._on_event()            # changed meanwhile: reload / offer it

    def mark_synced(self) -> None:
        """The window just read or wrote its file: that is not an outside edit."""
        self.follow_document()
        self._synced = _signature(self._path)
        self._looked = None
        self._settle.stop()
        self._hide_button()
        self._rewatch()

    def _rewatch(self) -> None:
        """A rewrite that replaces the file drops it from the watcher: add it again."""
        if self._path is None:
            return
        have = set(self._watcher.files()) | set(self._watcher.directories())
        want = [str(self._path.parent)]
        if self._path.exists():
            want.append(str(self._path))
        missing = [p for p in want if p not in have]
        if missing:
            self._watcher.addPaths(missing)

    # ---- noticing a change -----------------------------------------------
    def _on_event(self, *_args) -> None:
        if self._path is None:
            return
        self._rewatch()
        sig = _signature(self._path)
        if sig is None or sig == self._synced:
            return
        if not self._settle.isActive():
            self._settle.start()

    def _settled(self) -> None:
        sig = _signature(self._path)
        if sig is None or sig == self._synced:
            self._looked = None
            return
        if sig != self._looked:         # still being written: look again
            self._looked = sig
            self._settle.start()
            return
        self._looked = None
        self._apply()

    def _apply(self, raise_window: bool = False) -> None:
        w = self.window
        if QApplication.activeModalWidget() is not None:
            self._settle.start()        # a dialog is open: not now
            return
        if getattr(w, "_workspace", None) is not None or w._is_dirty():
            self._show_button()
        else:
            self.reload()
        if raise_window:
            w.show()
            w.raise_()
            w.activateWindow()

    # ---- reloading -------------------------------------------------------
    def reload(self, discard: bool = False) -> bool:
        """Read the file again. ``discard`` throws away unsaved edits (after
        keeping a copy in the auto-save «discarded» folder)."""
        w = self.window
        path = self._path
        if path is None or not path.is_file():
            return False
        if getattr(w, "_workspace", None) is not None and not w.leave_workspace():
            return False
        scene = w.viewport.scene
        if w._is_dirty():
            if not discard:
                return False
            from core import autosave
            try:
                autosave.write(scene, path)
            except Exception:  # noqa: BLE001 — recovery must never block
                pass
            autosave.clear(path)        # moves it to «descartados»: recoverable
        w.viewport.end_group_edit()
        camera = w._camera_dict()
        from core.purge import iter_groups
        hidden = {g.name for g in iter_groups(scene.groups) if getattr(g, "hidden", False)}
        layers = {ly.name: (ly.visible, ly.locked) for ly in scene.layers}
        if not w.open_path(path, reload=True):
            return False
        scene = w.viewport.scene
        for ly in scene.layers:
            if ly.name in layers:
                ly.visible, ly.locked = layers[ly.name]
        for g in iter_groups(scene.groups):
            if g.name in hidden:
                g.hidden = True
        w._apply_camera_dict(camera)
        scene.version += 1              # redraw with the restored view state
        w.viewport.notify_scene_changed()
        w._saved_version = scene.version
        w._update_title()
        from datetime import datetime
        w.statusBar().showMessage(
            f"โหลดโมเดลล่าสุดแล้ว ({datetime.now():%H:%M:%S})", 8000)
        return True

    # ---- the "changed outside" button ------------------------------------
    def _show_button(self) -> None:
        if self._button is None:
            b = QPushButton(self.window)
            b.setText("ไฟล์ถูกแก้จากภายนอก — กดเพื่อโหลดใหม่ "
                      "(งานที่ยังไม่บันทึกจะหาย)")
            b.setCursor(self.window.cursor())
            b.setStyleSheet("QPushButton { background: #ff8a1f; color: #1d1d1f; "
                            "border: 0; padding: 3px 10px; font-weight: bold; }"
                            "QPushButton:hover { background: #ffa04d; }")
            b.clicked.connect(lambda: self.reload(discard=True))
            self.window.statusBar().addPermanentWidget(b)
            self._button = b
        self._button.show()

    def _hide_button(self) -> None:
        if self._button is not None:
            self._button.hide()

    # ---- `yotathai_ai open FILE` ------------------------------------------
    def _listen(self) -> None:
        self._server = None
        try:
            from yotathai import live
        except Exception:  # noqa: BLE001 — a plain checkout has no shell
            return
        self._shell = live
        server = QLocalServer(self)
        name = f"yotathai3d-win-{os.getpid()}"
        QLocalServer.removeServer(name)
        if not server.listen(name):
            return
        server.newConnection.connect(self._on_request)
        self._server = server
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._goodbye)

    def _register(self) -> None:
        if self._shell is None or self._server is None:
            return
        try:
            self._shell.register(self._path, self._server.fullServerName())
        except OSError:
            pass

    def _goodbye(self) -> None:
        if self._shell is not None:
            self._shell.unregister()
        if self._server is not None:
            QLocalServer.removeServer(self._server.serverName())

    def _on_request(self) -> None:
        conn = self._server.nextPendingConnection()
        if conn is None:
            return
        reply = b"no\n"
        if conn.waitForReadyRead(300):
            line = bytes(conn.readAll()).decode("utf-8", "replace").strip()
            kind, _, path = line.partition("\t")
            if kind == "reload" and self._path is not None and path \
                    and os.path.exists(path) and os.path.samefile(path, self._path):
                reply = b"ok\n"
                QTimer.singleShot(0, self._reload_requested)
        conn.write(reply)
        conn.flush()
        conn.waitForBytesWritten(300)
        conn.disconnectFromServer()

    def wants(self, path) -> bool:
        """True when ``path`` is the file this window has open."""
        try:
            return self._path is not None and os.path.samefile(path, self._path)
        except OSError:
            return False

    def reload_requested(self) -> None:
        """Somebody asked to open the file this window already shows: read it
        again if it changed (never over unsaved work) and bring the window up."""
        self._reload_requested()

    def _reload_requested(self) -> None:
        sig = _signature(self._path)
        if sig is not None and sig != self._synced:
            self._apply(raise_window=True)
        else:
            w = self.window
            w.show()
            w.raise_()
            w.activateWindow()


def install(window) -> None:
    """Give ``window`` its live reload (best-effort: never blocks the window)."""
    try:
        window.live_reload = LiveReload(window)
    except Exception:  # noqa: BLE001
        import traceback
        traceback.print_exc()
