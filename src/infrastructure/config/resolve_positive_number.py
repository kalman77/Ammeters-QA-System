import math
from typing import Any, Mapping


def resolve_positive_number(section: Mapping[str, Any], key: str) -> float:
    """Read one finite positive numeric network setting."""
    value = section.get(key)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"network.{key} must be a positive number")
    return float(value)
