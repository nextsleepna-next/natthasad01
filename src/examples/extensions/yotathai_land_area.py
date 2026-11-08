# SPDX-License-Identifier: GPL-3.0-or-later
"""ขยายที่ดินตามพื้นที่จริง — ปรับผิวที่ดินให้ได้ไร่-งาน-ตารางวาที่ระบุ (ส่วนเสริมของ Yotathai).

ใช้กับผิวที่ช่างวาดทับภาพแผนที่/โฉนดที่ดึงเข้าโปรแกรม: เลือกผิว 1 ผิว แล้วเลือก
Extensions ▸ ขยายที่ดินตามพื้นที่… กรอกพื้นที่จริงเป็นไร่ งาน ตารางวา
โปรแกรมจะขยาย (หรือย่อ) ผิวทั้งผืนให้ได้พื้นที่นั้นพอดี โดยรักษารูปร่างเดิม
(ขยายเท่ากันทุกทิศรอบจุดกึ่งกลางผิว) และใส่เส้นบอกระยะความยาวทุกด้านให้
พร้อมกัน. ภาพแผนที่พื้นหลังจะขยายตามด้วย (ปิดได้) เพื่อให้ยังทับกับรูปร่างอยู่.
ย้อนกลับ (Undo) ได้ครั้งเดียวจบ.

หน่วยไทย: 1 ไร่ = 4 งาน, 1 งาน = 100 ตร.ว., 1 ตร.ว. = 4 ตร.ม. (1 ไร่ = 1,600 ตร.ม.)
หน่วยของโมเดลคือเมตร.
"""
from __future__ import annotations

import math

from PySide6.QtGui import QVector3D
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QSpinBox, QVBoxLayout,
)

from core.history import (
    Command, ScaleImagePlanesCommand, ScaleVerticesCommand,
)
from tools.base import Tool

SQM_PER_WAH = 4.0           # 1 ตารางวา = 4 ตารางเมตร
WAH_PER_NGAN = 100.0
NGAN_PER_RAI = 4.0
SQM_PER_RAI = SQM_PER_WAH * WAH_PER_NGAN * NGAN_PER_RAI     # 1,600


def to_sqm(rai: float, ngan: float, wah: float) -> float:
    """ไร่-งาน-ตารางวา → ตารางเมตร."""
    return ((rai * NGAN_PER_RAI + ngan) * WAH_PER_NGAN + wah) * SQM_PER_WAH


def from_sqm(sqm: float) -> tuple:
    """ตารางเมตร → (ไร่, งาน, ตารางวา) โดยไร่/งานเป็นจำนวนเต็ม."""
    wah_total = sqm / SQM_PER_WAH
    rai = int(wah_total // (WAH_PER_NGAN * NGAN_PER_RAI))
    wah_total -= rai * WAH_PER_NGAN * NGAN_PER_RAI
    ngan = int(wah_total // WAH_PER_NGAN)
    wah_total -= ngan * WAH_PER_NGAN
    return rai, ngan, wah_total


def fmt_thai_area(sqm: float) -> str:
    rai, ngan, wah = from_sqm(sqm)
    return f"{rai} ไร่ {ngan} งาน {wah:.2f} ตร.ว. ({sqm:,.2f} ตร.ม.)"


def _selected_face(scene):
    from core.mesh import Face
    faces = [e for e in scene.selection
             if isinstance(e, Face) and e in scene.mesh.faces]
    return faces[0] if len(faces) == 1 else None


def edge_dimensions(points: list, centroid: QVector3D, normal: QVector3D):
    """One Dimension per side of the polygon, the line pushed OUTSIDE the
    shape by ~4 % of its size so it never lies across the land."""
    from core.dimension import Dimension
    size = max((p - centroid).length() for p in points) or 1.0
    gap = 0.04 * size
    dims = []
    for i, a in enumerate(points):
        b = points[(i + 1) % len(points)]
        d = b - a
        if d.length() < 1e-9:
            continue
        out = QVector3D.crossProduct(d.normalized(), normal)
        mid = (a + b) * 0.5
        if QVector3D.dotProduct(out, mid - centroid) < 0:
            out = -out
        dims.append(Dimension(a, b, out.normalized() * gap))
    return dims


class FitLandCommand(Command):
    """Scale the land face to the target area, scale the reference images
    with it, and add a dimension on every side — ONE undo step."""

    def __init__(self, face, target_sqm: float, scale_images: bool) -> None:
        self.face = face
        self.target_sqm = float(target_sqm)
        self.scale_images = scale_images
        self.factor = 1.0
        self._parts: list = []
        self._dims: list = []

    def do(self, scene) -> None:
        if self._parts:                                   # redo
            for p in self._parts:
                p.do(scene)
            for d in self._dims:
                d.bind(scene)
                scene.dimensions.append(d)
            scene.version += 1
            return
        face = self.face
        current = face.area()
        if current < 1e-9 or self.target_sqm <= 0:
            raise ValueError("พื้นที่ผิวหรือพื้นที่เป้าหมายเป็นศูนย์")
        self.factor = math.sqrt(self.target_sqm / current)
        center = face.centroid()
        positions = [v.position for v in face.loop]
        self._parts.append(ScaleVerticesCommand(positions, center, self.factor))
        if self.scale_images:
            images = [im for im in scene.image_planes
                      if not getattr(im, "locked", False)]
            if images:
                self._parts.append(
                    ScaleImagePlanesCommand(images, center, self.factor))
        for p in self._parts:
            p.do(scene)
        pts = [QVector3D(v.position) for v in face.loop]
        self._dims = edge_dimensions(pts, face.centroid(), face.normal())
        for d in self._dims:
            d.bind(scene)
            scene.dimensions.append(d)
        scene.version += 1

    def undo(self, scene) -> None:
        for d in self._dims:
            if d in scene.dimensions:
                scene.dimensions.remove(d)
        for p in reversed(self._parts):
            p.undo(scene)
        scene.version += 1


class LandDialog(QDialog):
    def __init__(self, viewport, face):
        super().__init__(viewport.window())
        self.viewport, self.face = viewport, face
        self.setWindowTitle("ขยายที่ดินตามพื้นที่")
        now = face.area()
        info = QLabel("พื้นที่ผิวตอนนี้: " + fmt_thai_area(now))
        self.rai = QSpinBox()
        self.rai.setRange(0, 100000)
        self.rai.setSuffix(" ไร่")
        self.ngan = QSpinBox()
        self.ngan.setRange(0, 3)
        self.ngan.setSuffix(" งาน")
        self.wah = QDoubleSpinBox()
        self.wah.setRange(0, 99.99)
        self.wah.setDecimals(2)
        self.wah.setSuffix(" ตร.ว.")
        r, n, w = from_sqm(now)
        self.rai.setValue(r)
        self.ngan.setValue(min(n, 3))
        self.wah.setValue(min(w, 99.99))
        self.total = QLabel()
        self.images = QCheckBox("ขยายภาพแผนที่พื้นหลังตามไปด้วย")
        self.images.setChecked(True)
        row = QHBoxLayout()
        for w_ in (self.rai, self.ngan, self.wah):
            row.addWidget(w_)
        form = QFormLayout()
        form.addRow("พื้นที่จริงตามโฉนด", row)
        form.addRow("รวม", self.total)
        ok = QPushButton("ปรับขนาดที่ดิน")
        ok.setDefault(True)
        cancel = QPushButton("ยกเลิก")
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        btns = QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        lay = QVBoxLayout(self)
        lay.addWidget(info)
        lay.addLayout(form)
        lay.addWidget(self.images)
        lay.addLayout(btns)
        for w_ in (self.rai, self.ngan, self.wah):
            w_.valueChanged.connect(self._refresh)
        self._refresh()

    def target_sqm(self) -> float:
        return to_sqm(self.rai.value(), self.ngan.value(), self.wah.value())

    def _refresh(self) -> None:
        self.total.setText(f"{self.target_sqm():,.2f} ตร.ม.")


class LandAreaTool(Tool):
    name = "ขยายที่ดินตามพื้นที่…"
    shortcut = None
    description = ("เลือกผิวที่ดิน แล้วระบุพื้นที่จริงเป็นไร่ งาน ตารางวา "
                   "ผิวจะถูกขยายให้ได้พื้นที่นั้นพร้อมเส้นบอกความยาวทุกด้าน")

    def on_activate(self, viewport):
        face = _selected_face(viewport.scene)
        if face is None:
            QMessageBox.information(
                viewport.window(), "ขยายที่ดินตามพื้นที่",
                "กรุณาเลือกผิวที่ดิน 1 ผิวก่อน (คลิกที่ผิวที่วาดทับแผนที่)")
            return
        dlg = LandDialog(viewport, face)
        if not dlg.exec():
            return
        cmd = FitLandCommand(face, dlg.target_sqm(), dlg.images.isChecked())
        viewport.history.execute(cmd)
        viewport.notify_scene_changed()
        viewport.flash_status(
            f"ขยายที่ดินเป็น {fmt_thai_area(dlg.target_sqm())} "
            f"(ขยาย ×{cmd.factor:.4f})", 6000)

    def on_deactivate(self, viewport):
        pass
