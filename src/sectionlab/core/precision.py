"""Display precision and export precision.

Display decimals only affect what the user reads (spec S3). Calculations keep full
floating-point precision, and CSV export always writes the shortest round-trip
representation so exporting never loses digits (spec S4, decision D5).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence

MIN_DECIMALS = 0
MAX_DECIMALS = 6
DEFAULT_DECIMALS = 2


def _clamp_decimals(decimals: int) -> int:
    return max(MIN_DECIMALS, min(MAX_DECIMALS, int(decimals)))


def format_value(value: float, decimals: int) -> str:
    """Format a value for the screen, clamping the decimal count into range."""
    return f"{value:.{_clamp_decimals(decimals)}f}"


def format_full(value: float) -> str:
    """Format a value with the shortest representation that round-trips exactly."""
    return repr(float(value))


def results_to_csv(rows: Sequence[Mapping[str, float]]) -> str:
    """Render result rows as CSV: header from the first row's order, full precision values."""
    if not rows:
        return ""

    keys = list(rows[0].keys())
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(keys)
    for row in rows:
        writer.writerow([format_full(row[key]) for key in keys])
    return buffer.getvalue()
