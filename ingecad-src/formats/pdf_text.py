# SPDX-License-Identifier: GPL-3.0-or-later
"""Real text for PDF plots.

ezdxf's pipeline turns every TEXT / MTEXT / ATTRIB / dimension figure into
one filled path per glyph. In a PDF that is thousands of Bezier outlines per
line (Thai: 15 MB for one A3 sheet) and the text can neither be selected nor
searched. :func:`install` replaces the pipeline's ``draw_text`` so that each
text line becomes ONE scene item drawn with ``QPainter.drawText`` -- Qt's PDF
engine then embeds a subset of the TrueType font and emits real text.

Placement is ezdxf's own: it computed the transform (position, rotation,
alignment, width factor, mirror) and the line width from its glyph metrics;
the item only swaps the glyph outlines for the font's text. The Qt line is
stretched to ezdxf's measured width so the two engines agree to a fraction of
a millimetre even if their advances differ a little (shaping, kerning).

Anything that cannot be reproduced exactly (stroke / SHX fonts, a font file
that cannot be found, a character the font lacks, text crossing a viewport
border) falls back to ezdxf's path drawing, line by line -- a plot never
loses text because of this module.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import (QFont, QFontDatabase, QFontMetricsF,
                           QTransform)
from PySide6.QtWidgets import QGraphicsItem

logger = logging.getLogger(__name__)

#: Qt pixel size the line is laid out at; the item's transform scales it to
#: drawing units, so the value only sets the shaping resolution.
_LAYOUT_PX = 1000.0
#: ezdxf/Qt widths further apart than this are not "a little shaping
#: difference" -- the text would look wrong stretched, so draw paths.
_MAX_STRETCH = (0.8, 1.25)


class _FontRecord:
    """What the plot needs to know about one TrueType file."""

    __slots__ = ("family", "weight", "italic", "upem", "baseline", "cmap")

    def __init__(self, family, weight, italic, upem, baseline, cmap):
        self.family = family
        self.weight = weight
        self.italic = italic
        self.upem = upem
        self.baseline = baseline
        self.cmap = cmap


_RECORDS: dict[str, Optional[_FontRecord]] = {}


def _load_record(path: str) -> Optional[_FontRecord]:
    """Register ``path`` with Qt (read from where it is installed, never
    copied) and describe it. Fonts such as AA Pirun map Thai glyphs at the
    TIS-620 code points 0x80-0xFF as well as at U+0E00; the duplicates are
    dropped from the in-memory cmap so the PDF's ToUnicode table maps to Thai
    and the text copies correctly (same technique as calc.py)."""
    import io

    from fontTools.ttLib import TTFont
    from PySide6.QtCore import QByteArray

    ft = TTFont(path, fontNumber=0)
    cmap = {}
    dup_removed = False
    for table in ft["cmap"].tables:
        if not table.isUnicode():
            continue
        for cp in [c for c, g in table.cmap.items()
                   if 0x80 <= c <= 0xFF and str(g).endswith("thai")]:
            del table.cmap[cp]
            dup_removed = True
        cmap.update(table.cmap)
    if dup_removed:
        buf = io.BytesIO()
        ft.save(buf)
        font_id = QFontDatabase.addApplicationFontFromData(
            QByteArray(buf.getvalue()))
    else:
        font_id = QFontDatabase.addApplicationFont(path)
    families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
    if not families:
        return None
    os2 = ft["OS/2"] if "OS/2" in ft else None
    weight = int(getattr(os2, "usWeightClass", 400) or 400)
    italic = bool(os2 is not None and (os2.fsSelection & 1)) \
        or bool(ft["head"].macStyle & 2)
    # ezdxf measures the baseline as the bottom of a lower-case "x"
    baseline = 0.0
    try:
        from ezdxf.fonts.ttfonts import TTFontRenderer

        baseline = TTFontRenderer(ft).font_measurements.baseline
    except Exception:                     # noqa: BLE001 - fall back to 0
        pass
    return _FontRecord(families[0], weight, italic,
                       float(ft["head"].unitsPerEm), float(baseline), cmap)


def _record_for(engine, font_face) -> Optional[_FontRecord]:
    """The record of the TrueType file ezdxf would draw ``font_face`` from,
    or None when it is not a plain TrueType outline font on disk."""
    from ezdxf.fonts import fonts as ezfonts

    try:
        font = engine.get_font(font_face)
    except Exception:                     # noqa: BLE001
        return None
    if font.font_render_type != ezfonts.FontRenderType.OUTLINE \
            or not hasattr(font, "glyph_cache"):
        return None
    try:
        entry = ezfonts.font_manager._font_cache[Path(font.name).name]
    except (KeyError, AttributeError):
        return None
    path = str(entry.file_path)
    if path not in _RECORDS:
        try:
            _RECORDS[path] = _load_record(path)
        except Exception as exc:          # noqa: BLE001 - unreadable font
            logger.info("PDF text: font %s unusable (%s)", path, exc)
            _RECORDS[path] = None
    return _RECORDS[path]


class TextLineItem(QGraphicsItem):
    """One line of text drawn through the painter (so a PDF gets real text).

    ``matrix`` maps glyph space (origin on the baseline at the start of the
    line, one unit = one drawing unit) into scene coordinates; ``stretch``
    scales x so the width equals ezdxf's.
    """

    def __init__(self, text, font, matrix, scale, stretch, baseline_px,
                 color, bounds):
        super().__init__()
        self._text = text
        self._font = font
        self._baseline_px = baseline_px
        self._color = color
        self._bounds = bounds
        # pixels (y down) -> glyph units (y up) -> scene
        local = QTransform.fromScale(scale * stretch, -scale)
        self._xf = local * matrix
        self.setFlag(QGraphicsItem.ItemHasNoContents, False)

    def boundingRect(self) -> QRectF:
        return self._bounds

    def paint(self, painter, option=None, widget=None) -> None:
        painter.save()
        painter.setTransform(self._xf, True)
        painter.setFont(self._font)
        painter.setPen(self._color)
        painter.drawText(QPointF(0.0, self._baseline_px), self._text)
        painter.restore()


def _qt_matrix(m) -> QTransform:
    return QTransform(m[0, 0], m[0, 1], m[1, 0], m[1, 1], m[3, 0], m[3, 1])


def install(frontend, backend) -> None:
    """Make ``frontend``'s pipeline emit :class:`TextLineItem` for text."""
    from ezdxf.addons.drawing.config import TextPolicy
    from ezdxf.addons.drawing.pipeline import prepare_string_for_rendering
    from ezdxf.math import Matrix44, Vec2

    pipeline = frontend.pipeline
    original = pipeline.draw_text
    engine = pipeline.text_engine
    fonts_made: dict[tuple, QFont] = {}

    def draw_text(text, transform, properties, cap_height, dxftype="TEXT"):
        try:
            if _emit(text, transform, properties, cap_height, dxftype):
                return
        except Exception as exc:          # noqa: BLE001 - never lose text
            logger.info("PDF text fallback: %s", exc)
        original(text, transform, properties, cap_height, dxftype)

    def _emit(text, transform, properties, cap_height, dxftype) -> bool:
        if pipeline.config.text_policy != TextPolicy.FILLING:
            return False
        if not text.strip():
            return True                   # nothing to draw (as the original)
        text = prepare_string_for_rendering(text, dxftype)
        font_face = properties.font or pipeline.default_font_face
        rec = _record_for(engine, font_face)
        if rec is None:
            return False
        if any(ord(ch) not in rec.cmap for ch in text):
            return False                  # .notdef boxes: ezdxf's job
        ez_width = engine.get_text_line_width(text, font_face, cap_height)
        if ez_width <= 0:
            return False

        # exact glyph-space extents (ezdxf's own outlines) for bounds + clip
        glyphs = engine.get_text_glyph_paths(text, font_face, cap_height)
        if not glyphs:
            return True
        xs0 = ys0 = 1e300
        xs1 = ys1 = -1e300
        for g in glyphs:
            for v in g.extents():
                xs0, xs1 = min(xs0, v.x), max(xs1, v.x)
                ys0, ys1 = min(ys0, v.y), max(ys1, v.y)
        corners = [Vec2(xs0, ys0), Vec2(xs1, ys0), Vec2(xs1, ys1), Vec2(xs0, ys1)]

        # compose the viewport (model -> paper) transforms the clipping
        # stage would apply to a path
        total = transform
        portal = pipeline.clipping_portal
        if portal.is_active:
            for stage in reversed(portal._stages):
                if stage.transform is not None:
                    total = total @ stage.transform
            placed = [Vec2(transform.transform((c.x, c.y, 0))) for c in corners]
            for p in placed:
                if portal.clip_point(p) is None:
                    return False          # touches a border: path + clip
        scene_pts = [total.transform((c.x, c.y, 0)) for c in corners]

        font = fonts_made.get((rec.family, rec.weight, rec.italic))
        if font is None:
            font = QFont(rec.family)
            font.setPixelSize(int(_LAYOUT_PX))
            font.setWeight(QFont.Weight(min(max(rec.weight, 1), 1000)))
            font.setItalic(rec.italic)
            font.setKerning(True)
            font.setHintingPreference(QFont.PreferNoHinting)
            font.setStyleStrategy(QFont.NoFontMerging)
            fonts_made[(rec.family, rec.weight, rec.italic)] = font
        qt_width = QFontMetricsF(font).horizontalAdvance(text)
        if qt_width <= 0:
            return False
        # glyph units per Qt pixel: ezdxf scales font units by cap/capHeight
        scale = engine.get_font(font_face).glyph_cache.get_scaling_factor(
            cap_height) * rec.upem / _LAYOUT_PX
        stretch = ez_width / (qt_width * scale)
        if not (_MAX_STRETCH[0] <= stretch <= _MAX_STRETCH[1]):
            return False

        xs = [p[0] for p in scene_pts]
        ys = [p[1] for p in scene_pts]
        bounds = QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
        # the item's own paint() works in scene coordinates, so the bounds
        # must be scene coordinates (not local ones) -- and the item sits at
        # the scene origin
        bp = pipeline.get_backend_properties(properties)
        color = backend._get_color(bp.color)
        item = TextLineItem(text, font, _qt_matrix(total), scale, stretch,
                            rec.baseline * _LAYOUT_PX / rec.upem, color, bounds)
        backend._add_item(item, bp.handle)
        return True

    pipeline.draw_text = draw_text
