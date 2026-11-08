# SPDX-License-Identifier: GPL-3.0-or-later
"""สร้างเสา — เสากลมและเสาสี่เหลี่ยมตามขนาดที่ระบุ (ส่วนเสริมของ Yotathai).

Extensions ▸ สร้างเสา… เปิดหน้าต่างให้เลือกรูปแบบเสา (กลม / สี่เหลี่ยม),
ขนาดหน้าตัด (ซม.) และความสูง (ม.) แล้วกด "เริ่มวางเสา" — เสาจะลอยตามเมาส์
คลิกตรงไหนก็วางตรงนั้น (จับจุดมุม/กึ่งกลาง/เส้น ได้เหมือนเครื่องมืออื่น) และวาง
ต้นต่อไปได้ทันที กด Esc เพื่อหยุด. เสาแต่ละต้นเป็นกลุ่มเดียว ติดแท็ก BIM
(IfcColumn) และ Undo ได้ครั้งละหนึ่งต้น.

หน่วยในโมเดลคือเมตร; หน้าตัดกรอกเป็นเซนติเมตร.
"""
from __future__ import annotations

import math

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout,
    QLabel, QPushButton, QVBoxLayout,
)

from core.history import SnapshotImport
from tools.base import Tool
from tools.place_group import PlaceGroupTool

SHAPES = ("round", "square")
SHAPE_LABELS = {"round": "เสากลม", "square": "เสาสี่เหลี่ยม"}
CONCRETE = (0.78, 0.78, 0.76, 1.0)
CIRCLE_SEGMENTS = 48


def column_outline(shape: str, width_m: float, depth_m: float,
                   cx: float = 0.0, cy: float = 0.0) -> list:
    """The (x, y) footprint, counter-clockwise, centred on (cx, cy).
    ``round`` uses ``width_m`` as the diameter; ``square`` is width × depth."""
    if shape == "round":
        r = width_m / 2.0
        return [(cx + r * math.cos(2 * math.pi * i / CIRCLE_SEGMENTS),
                 cy + r * math.sin(2 * math.pi * i / CIRCLE_SEGMENTS))
                for i in range(CIRCLE_SEGMENTS)]
    if shape == "square":
        hx, hy = width_m / 2.0, depth_m / 2.0
        return [(cx - hx, cy - hy), (cx + hx, cy - hy),
                (cx + hx, cy + hy), (cx - hx, cy + hy)]
    raise ValueError(f"unknown column shape: {shape!r}")


def build_column(scene, shape: str, width_cm: float, depth_cm: float,
                 height_m: float, x: float = 0.0, y: float = 0.0,
                 z: float = 0.0):
    """Add one column group to ``scene`` (call inside an undoable mutate)."""
    if width_cm <= 0 or height_m <= 0 or (shape == "square" and depth_cm <= 0):
        raise ValueError("ขนาดเสาและความสูงต้องมากกว่าศูนย์")
    from core import bim
    from core.ai import _recipe_helpers
    extrude = _recipe_helpers(scene)["extrude"]
    if shape == "round":
        label = f"เสากลม Ø{width_cm:g} ซม. สูง {height_m:g} ม."
    else:
        label = (f"เสา {width_cm:g}x{depth_cm:g} ซม. "
                 f"สูง {height_m:g} ม.")
    outline = column_outline(shape, width_cm / 100.0, depth_cm / 100.0, x, y)
    group = extrude(outline, z, z + height_m, name=label, color=CONCRETE)
    bim.tag_group(group, "IfcColumn", label)
    return group


def make_column_group(scene, *args, **kw):
    """A column group NOT left in the scene — for the click-to-place tool,
    which inserts it (undoably) where the user clicks."""
    group = build_column(scene, *args, **kw)
    scene.groups.remove(group)
    return group


class ColumnPlaceTool(PlaceGroupTool):
    """The column follows the cursor; each click drops one (on the ground,
    or on whatever surface/point is snapped) and the next one is ready.
    Esc stops."""
    name = "สร้างเสา"

    def __init__(self, viewport, params) -> None:
        self._params = params
        super().__init__(make_column_group(viewport.scene, *params))

    def on_click(self, ctx) -> None:
        vp = ctx.viewport
        super().on_click(ctx)           # places, then switches to Select
        vp.set_active_tool(ColumnPlaceTool(vp, self._params))
        vp.flash_status("คลิกเพื่อวางเสาต้นต่อไป — กด Esc เพื่อหยุด", 4000)


# The plugin loader makes a menu entry out of every Tool defined in this
# file and constructs it with no arguments; the placement tool is internal
# (the dialog starts it), so it must not count as "defined here".
ColumnPlaceTool.__module__ = "yotathai_column_internal"


class ColumnDialog(QDialog):
    def __init__(self, viewport):
        super().__init__(viewport.window())
        self.viewport = viewport
        self.setWindowTitle("สร้างเสา")
        form = QFormLayout()
        self.shape = QComboBox()
        for key in SHAPES:
            self.shape.addItem(SHAPE_LABELS[key], key)
        self.width = self._spin(1, 500, 20, " ซม.", 1)
        self.depth = self._spin(1, 500, 20, " ซม.", 1)
        self.height = self._spin(0.1, 100, 3.0, " ม.", 2)
        self.width_label = QLabel()
        form.addRow("รูปแบบเสา", self.shape)
        form.addRow(self.width_label, self.width)
        self.depth_label = QLabel("ความลึก (ด้านที่ 2)")
        form.addRow(self.depth_label, self.depth)
        form.addRow("ความสูงเสา", self.height)
        self.status = QLabel("")
        make = QPushButton("เริ่มวางเสา")
        make.setDefault(True)
        close = QPushButton("ปิด")
        make.clicked.connect(self._make)
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(make)
        row.addWidget(close)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.status)
        lay.addLayout(row)
        self.shape.currentIndexChanged.connect(self._sync)
        self._sync()

    @staticmethod
    def _spin(lo, hi, val, suffix, decimals):
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(decimals)
        s.setValue(val)
        s.setSuffix(suffix)
        return s

    def _sync(self) -> None:
        square = self.shape.currentData() == "square"
        self.width_label.setText("ความกว้าง" if square else "เส้นผ่านศูนย์กลาง")
        self.depth.setVisible(square)
        self.depth_label.setVisible(square)

    def _make(self) -> None:
        vp = self.viewport
        args = (self.shape.currentData(), self.width.value(),
                self.depth.value(), self.height.value())
        try:
            tool = ColumnPlaceTool(vp, args)
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        vp.set_active_tool(tool)
        vp.flash_status("เลื่อนเมาส์แล้วคลิกเพื่อวางเสา — กด Esc เพื่อหยุด", 6000)
        self.hide()


class ColumnTool(Tool):
    name = "สร้างเสา…"
    shortcut = None
    description = "สร้างเสากลมหรือเสาสี่เหลี่ยม ระบุหน้าตัด ความสูง และตำแหน่ง"

    def on_activate(self, viewport):
        self._dlg = ColumnDialog(viewport)
        self._dlg.setModal(False)
        self._dlg.show()

    def on_deactivate(self, viewport):
        pass
