# SPDX-License-Identifier: GPL-3.0-or-later
"""Room labels for Yotathai Plan: name + kind + level + outline of each room,
kept inside the model (``plugin_data["yotathai_rooms"]``), used to colour room
floors on plans. See ``docs/room-labels-usage-691101.md``."""
from . import fill, geometry, kinds, store          # noqa: F401
from .fill import room_fills                        # noqa: F401
