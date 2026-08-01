"""Pure display helpers shared by every desktop page.

These helpers never import Qt so they can be unit tested headlessly.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Mapping, Optional


PLACEHOLDER = "—"


def finite(value: object) -> Optional[float]:
    """Return value as a finite float, or None when it is not numeric."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        parsed = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def mapping(value: object) -> Mapping[str, Any]:
    """Return value when it is a mapping, otherwise an empty mapping."""
    return value if isinstance(value, Mapping) else {}


def sequence(value: object) -> list:
    """Return value as a list when it is a non-string sequence."""
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        return []
    return list(value)


def format_number(
    value: object,
    *,
    digits: int = 4,
    suffix: str = "",
) -> str:
    """Format a finite number with a fixed significant-digit budget."""
    parsed = finite(value)
    if parsed is None:
        return PLACEHOLDER
    return f"{parsed:.{digits}g}{suffix}"


def format_current(value: object, unit: object = "A") -> str:
    """Format one current reading with its unit."""
    parsed = finite(value)
    if parsed is None:
        return PLACEHOLDER
    return f"{parsed:.4f} {str(unit or 'A')}"


def format_seconds(value: object) -> str:
    """Format a duration in seconds using a readable scale."""
    parsed = finite(value)
    if parsed is None:
        return PLACEHOLDER
    if abs(parsed) < 1.0:
        return f"{parsed * 1000:.1f} ms"
    if abs(parsed) < 120.0:
        return f"{parsed:.3f} s"
    minutes, seconds = divmod(parsed, 60.0)
    return f"{int(minutes)}m {seconds:.1f}s"


def format_milliseconds(value: object) -> str:
    """Format a seconds value as milliseconds."""
    parsed = finite(value)
    if parsed is None:
        return PLACEHOLDER
    return f"{parsed * 1000:.2f} ms"


def format_signed(value: object, *, digits: int = 4, suffix: str = "") -> str:
    """Format a delta with an explicit sign so direction is unambiguous."""
    parsed = finite(value)
    if parsed is None:
        return PLACEHOLDER
    if parsed == 0:
        return f"0{suffix}"
    return f"{parsed:+.{digits}g}{suffix}"


def format_percentage(value: object) -> str:
    """Format a 0..1 ratio as a percentage."""
    parsed = finite(value)
    if parsed is None:
        return PLACEHOLDER
    return f"{parsed * 100:.1f}%"


def format_timestamp(value: object, *, with_seconds: bool = True) -> str:
    """Format an ISO 8601 UTC timestamp for local display."""
    if not isinstance(value, str) or not value.strip():
        return PLACEHOLDER
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    local = parsed.astimezone()
    pattern = "%Y-%m-%d %H:%M:%S" if with_seconds else "%Y-%m-%d %H:%M"
    return local.strftime(pattern)


def short_run_id(run_id: object) -> str:
    """Shorten a canonical UUID for dense table columns."""
    text = str(run_id or "").strip()
    if len(text) <= 12:
        return text or PLACEHOLDER
    return f"{text[:8]}…{text[-4:]}"


def title_case(value: object) -> str:
    """Title-case an ammeter or status token for display."""
    text = str(value or "").strip()
    return text.title() if text else PLACEHOLDER
