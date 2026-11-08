# SPDX-License-Identifier: GPL-3.0-or-later
"""Converters between the two engines, each runnable on its own:

* ``python -m yotathai.convert.plan_to_model plan.dxf model.igz``  (2D -> 3D)
* ``python -m yotathai.convert.views_to_dxf  model.igz sheet.dxf`` (3D -> 2D)
* ``python -m yotathai.convert.sample        modern-house.igz``

They import the 3D engine (``src/``) and ezdxf, never the 2D engine, so the
2D app runs them as a child process and reads the one-line JSON report
that ``--json`` prints last.
"""
