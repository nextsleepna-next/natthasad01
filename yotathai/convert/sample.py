# SPDX-License-Identifier: GPL-3.0-or-later
"""The sample house the home screen offers: a two-storey modern house with a
pool, written as an .igz: ``python -m yotathai.convert.sample out.igz``.

The recipe (``modern_house.recipe``) is plain script text built only from the
program's own helpers (box / wall / prism / revolve), run the same way as
``yotathai-ai build-3d``."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from yotathai.convert._common import run, save_model, use_3d_engine

RECIPE = Path(__file__).with_name("modern_house.recipe")


def build(path: Path) -> dict:
    use_3d_engine()
    from core import bim
    from core.ai import _recipe_helpers
    from core.scene import Scene
    scene = Scene()
    ns = dict(_recipe_helpers(scene))
    ns.update({"scene": scene, "bim": bim, "tag": bim.tag_group,
               "__name__": "__recipe__"})
    exec(compile(RECIPE.read_text(encoding="utf-8"), str(RECIPE), "exec"), ns)
    save_model(scene, path)
    return {"model": str(path), "groups": len(scene.groups)}


def main(argv) -> dict:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out", type=Path)
    return build(ap.parse_args(argv).out)


if __name__ == "__main__":
    sys.exit(run(main))
