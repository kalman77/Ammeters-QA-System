import threading

from src.infrastructure.emulators.running_emulator import RunningEmulator


def serve_emulator(
    running_emulator: RunningEmulator,
    stop_event: threading.Event,
) -> None:
    """Run one emulator server and expose thread failures to the coordinator."""
    try:
        running_emulator.emulator.start_server(
            ready_event=running_emulator.ready_event,
            stop_event=stop_event,
        )
    except BaseException as exc:
        running_emulator.startup_error = exc
        running_emulator.ready_event.set()
