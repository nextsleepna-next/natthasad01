# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared by the converters: the 3D engine on sys.path, saving, reporting."""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

from yotathai.paths import SRC_3D


def use_3d_engine() -> None:
    """Put the 3D engine first on sys.path (its ``core``/``formats``)."""
    path = str(SRC_3D)
    if path not in sys.path:
        sys.path.insert(0, path)


def rgb_only(scene) -> None:
    """The .glb writer takes RGB; the helpers' defaults are RGBA."""
    for mesh in [scene.mesh] + [g.mesh for g in scene.groups]:
        for f in mesh.faces:
            c = f.attrs.get("color")
            if c is not None and len(c) == 4:
                f.attrs["color"] = tuple(c[:3])


def save_model(scene, igz: Path, glb: Path | None = None) -> None:
    from formats.igz import save_scene
    rgb_only(scene)
    igz = Path(igz)
    igz.parent.mkdir(parents=True, exist_ok=True)
    save_scene(scene, igz)
    if glb is not None:
        from formats.gltf import save_glb
        save_glb(scene, Path(glb))


def run(main, argv=None) -> int:
    """Call ``main(argv) -> dict``; print the report (JSON with --json,
    readable otherwise). Errors become ``{"ok": false, "error": ...}``."""
    from yotathai import portable
    if portable.setup() is not None:
        portable.register_ezdxf_fonts()
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]
    try:
        report = main(argv)
        report = {"ok": True, **report}
        code = 0
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — every failure is reported
        report = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        if not as_json:
            traceback.print_exc()
        code = 1
    if as_json:
        print(json.dumps(report, ensure_ascii=False, default=str))
    else:
        for k, v in report.items():
            print(f"{k}: {v}")
    return code
