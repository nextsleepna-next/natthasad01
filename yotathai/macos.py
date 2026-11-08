# SPDX-License-Identifier: GPL-3.0-or-later
"""macOS niceties without PyObjC: the app name in the menu bar.

Run from source, every engine is the Homebrew ``Python.app`` to macOS, so
the bold application menu said «Python». Renaming the main bundle's
``CFBundleName`` before Qt starts Cocoa is the long-standing fix (what
py2app-less tools do); done through the Objective-C runtime with ctypes.
Every call is best-effort: anything unexpected leaves the name alone.
"""
from __future__ import annotations

import sys


def set_app_name(name: str) -> bool:
    """Call BEFORE the QApplication exists. True when the name was set."""
    if sys.platform != "darwin":
        return False
    try:
        import ctypes
        import ctypes.util

        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        ctypes.cdll.LoadLibrary(ctypes.util.find_library("Foundation"))
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        send_ptr = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value

        def send(receiver, selector, *args, argtypes=()):
            proto = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p,
                                     ctypes.c_void_p, *argtypes)
            fn = proto(send_ptr)
            return fn(receiver, objc.sel_registerName(selector), *args)

        def nsstring(text: str):
            cls = objc.objc_getClass(b"NSString")
            return send(cls, b"stringWithUTF8String:", text.encode("utf-8"),
                        argtypes=(ctypes.c_char_p,))

        bundle = send(objc.objc_getClass(b"NSBundle"), b"mainBundle")
        if not bundle:
            return False
        done = False
        for getter in (b"localizedInfoDictionary", b"infoDictionary"):
            info = send(bundle, getter)
            if not info:
                continue
            # A mutable dictionary answers setObject:forKey:; an immutable
            # one would raise inside Cocoa, so ask first.
            if not send(info, b"respondsToSelector:",
                        objc.sel_registerName(b"setObject:forKey:"),
                        argtypes=(ctypes.c_void_p,)):
                continue
            for key in ("CFBundleName", "CFBundleDisplayName"):
                send(info, b"setObject:forKey:", nsstring(name), nsstring(key),
                     argtypes=(ctypes.c_void_p, ctypes.c_void_p))
            done = True
        return done
    except Exception:          # noqa: BLE001 — cosmetic, never fatal
        return False
