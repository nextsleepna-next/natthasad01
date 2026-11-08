# SPDX-License-Identifier: GPL-3.0-or-later
"""Repair Thai text extracted from PDF fonts: private-use glyphs -> real marks."""
from __future__ import annotations

# Windows/Mac Thai private-use block (U+F700..U+F717): shifted vowels/tone marks.
_PUA = {
    0xF701: "ิ", 0xF702: "ี", 0xF703: "ึ", 0xF704: "ื",
    0xF705: "่", 0xF706: "้", 0xF707: "๊", 0xF708: "๋",
    0xF709: "์", 0xF70A: "่", 0xF70B: "้", 0xF70C: "๊",
    0xF70D: "๋", 0xF70E: "์", 0xF710: "ั", 0xF711: "ํ",
    0xF712: "็", 0xF713: "่", 0xF714: "้", 0xF715: "๊",
    0xF716: "๋", 0xF717: "์",
}
_TABLE = {k: v for k, v in _PUA.items()}


def fix_thai(text: str) -> str:
    """Replace private-use Thai glyphs; leave everything else untouched."""
    return text.translate(_TABLE) if text else text


def has_private_use(text: str) -> bool:
    return any(0xE000 <= ord(c) <= 0xF8FF for c in text or "")
