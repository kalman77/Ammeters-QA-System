from enum import Enum


class MeasurementStatus(str, Enum):
    """Outcome of one ammeter measurement attempt."""

    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
