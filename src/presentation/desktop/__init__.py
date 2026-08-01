"""Desktop presentation adapter for the ammeter test framework."""

from src.presentation.desktop.run_service import (
    DesktopRunService,
    FaultInjection,
    RunCancelled,
    RunRequest,
    StopToken,
)


__all__ = [
    "DesktopRunService",
    "FaultInjection",
    "RunCancelled",
    "RunRequest",
    "StopToken",
    "main",
]


def main(argv=None) -> int:
    """Start the desktop console, importing Qt only when it is needed."""
    from src.presentation.desktop.app import main as run_desktop

    return run_desktop(argv)
