from typing import Iterable

from src.domain.models.measurement_result import MeasurementResult


def format_measurement_results_table(
    results: Iterable[MeasurementResult],
) -> str:
    """Return typed measurement results as an aligned console table."""
    headers = (
        "Ammeter",
        "Status",
        "Current",
        "Unit",
        "Latency (ms)",
        "Error",
    )
    rows = []
    for result in results:
        error_text = "; ".join(
            f"{error.code.value}: {error.message}"
            for error in result.errors
        )
        rows.append(
            (
                result.ammeter_type.upper(),
                result.status.value.upper(),
                (
                    f"{result.current:.6f}"
                    if result.current is not None
                    else "-"
                ),
                result.unit,
                (
                    f"{result.request_latency_seconds * 1000:.3f}"
                    if result.request_latency_seconds is not None
                    else "-"
                ),
                error_text or "-",
            )
        )

    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]
    border = "+" + "+".join(
        f"-{'-' * width}-" for width in widths
    ) + "+"
    header = (
        f"| {headers[0]:<{widths[0]}} "
        f"| {headers[1]:<{widths[1]}} "
        f"| {headers[2]:>{widths[2]}} "
        f"| {headers[3]:<{widths[3]}} "
        f"| {headers[4]:>{widths[4]}} "
        f"| {headers[5]:<{widths[5]}} |"
    )
    body = [
        (
            f"| {ammeter:<{widths[0]}} "
            f"| {status:<{widths[1]}} "
            f"| {current:>{widths[2]}} "
            f"| {unit:<{widths[3]}} "
            f"| {latency:>{widths[4]}} "
            f"| {error:<{widths[5]}} |"
        )
        for ammeter, status, current, unit, latency, error in rows
    ]

    return "\n".join(
        [
            "Ammeter Test Results",
            border,
            header,
            border,
            *body,
            border,
        ]
    )
