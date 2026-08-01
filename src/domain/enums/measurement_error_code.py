from enum import Enum


class MeasurementErrorCode(str, Enum):
    """Stable machine-readable failure categories."""

    EMULATOR_START_FAILED = "emulator_start_failed"
    MEASUREMENT_REQUEST_FAILED = "measurement_request_failed"
    INVALID_MEASUREMENT = "invalid_measurement"
    EMULATOR_STOP_FAILED = "emulator_stop_failed"
    SAMPLING_SLOT_MISSED = "sampling_slot_missed"
