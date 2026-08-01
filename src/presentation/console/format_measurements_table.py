from typing import Mapping


def format_measurements_table(measurements: Mapping[str, float]) -> str:
    """Return measurements as an aligned, dependency-free console table."""
    headers = ("Ammeter", "Current", "Unit")
    rows = [
        (name.upper(), f"{current:.6f}", "A")
        for name, current in measurements.items()
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]

    border = (
        f"+-{'-' * widths[0]}-"
        f"+-{'-' * widths[1]}-"
        f"+-{'-' * widths[2]}-+"
    )
    header = (
        f"| {headers[0]:<{widths[0]}} "
        f"| {headers[1]:>{widths[1]}} "
        f"| {headers[2]:<{widths[2]}} |"
    )
    body = [
        (
            f"| {name:<{widths[0]}} "
            f"| {current:>{widths[1]}} "
            f"| {unit:<{widths[2]}} |"
        )
        for name, current, unit in rows
    ]

    return "\n".join(
        [
            "Ammeter Measurement Results",
            border,
            header,
            border,
            *body,
            border,
        ]
    )
