# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Yotathai — on top of IngeCAD and IngeTrazo
# (Marco Sumari Tellez and contributors).
"""Yotathai: one app for Thai builders, two engines underneath.

* ``ingecad-src/`` — the 2D drafting engine (Yotathai CAD, from IngeCAD);
* ``src/``         — the 3D modelling engine (Yotathai 3D, from IngeTrazo).

The two engines keep their own processes (both have top-level packages
called ``core``/``views``/``formats``, so they can never share one Python
interpreter). This package is the thin shell around them: the launcher and
home screen (``python -m yotathai``), the 2D <-> 3D converters
(``yotathai.convert``) and the helpers each engine uses to hand a file to
the other (``yotathai.bridge``). Nothing here imports either engine at
module level.
"""
