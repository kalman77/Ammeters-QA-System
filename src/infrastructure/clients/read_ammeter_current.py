from Ammeters.client import (
    AmmeterClientError,
    request_current_from_ammeter,
)
from src.application.errors.measurement_request_error import (
    MeasurementRequestError,
)


def read_ammeter_current(
    port: int,
    command: bytes,
    *,
    host: str,
    connect_timeout_seconds: float,
    read_timeout_seconds: float,
) -> float:
    """Adapt socket client errors to the application measurement contract."""
    try:
        return request_current_from_ammeter(
            port,
            command,
            host=host,
            connect_timeout_seconds=connect_timeout_seconds,
            read_timeout_seconds=read_timeout_seconds,
        )
    except AmmeterClientError as exc:
        raise MeasurementRequestError(str(exc)) from exc
