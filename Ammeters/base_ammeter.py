import random
import socket
import threading
import time
from abc import ABC, abstractmethod
from typing import Optional

NotImplementedErrorMsg = "Subclasses must implement this property."
MAX_MESSAGE_BYTES = 1024


class AmmeterEmulatorBase(ABC):
    def __init__(
        self,
        port: int,
        host: str = "127.0.0.1",
        command: Optional[bytes] = None,
        request_timeout_seconds: float = 2.0,
    ):
        self.port = port
        self.host = host
        self._configured_command = command
        self.request_timeout_seconds = request_timeout_seconds
        random.seed(time.time())  # Seed the random number generator for each instance

    @property
    def current_command(self) -> bytes:
        """Return the configured command, falling back to the emulator default."""
        return self._configured_command or self.get_current_command

    def start_server(
        self,
        ready_event: Optional[threading.Event] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        """
        Starts the server to listen for client requests.

        When ``stop_event`` is omitted, the server retains its original behavior
        and runs indefinitely. ``ready_event`` is signalled only after the socket
        is bound and listening.
        """
        stop_event = stop_event or threading.Event()

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.host, self.port))
            # Port 0 is useful for race-free integration tests.
            self.port = s.getsockname()[1]
            s.listen()
            s.settimeout(0.1)
            print(f"{self.__class__.__name__} is running on port {self.port}")
            if ready_event is not None:
                ready_event.set()

            while not stop_event.is_set():
                try:
                    conn, addr = s.accept()
                except socket.timeout:
                    continue

                with conn:
                    print(f"Connected by {addr}")
                    data = self._receive_command(conn, stop_event)
                    if not data or stop_event.is_set():
                        continue

                    if data == self.current_command:
                        # Call the specific measure_current() method defined in subclasses
                        current = self.measure_current()
                        response = str(current).encode("utf-8") + b"\n"
                    else:
                        response = b"ERROR: unsupported command\n"

                    try:
                        conn.sendall(response)
                    except OSError:
                        # A client may disconnect while a measurement is prepared.
                        continue

    def _receive_command(
        self,
        conn: socket.socket,
        stop_event: threading.Event,
    ) -> bytes:
        """Read one framed command while supporting the original raw protocol."""
        poll_timeout = min(0.1, self.request_timeout_seconds)
        conn.settimeout(poll_timeout)
        read_deadline = time.monotonic() + self.request_timeout_seconds
        expected_command = self.current_command
        received = bytearray()

        while not stop_event.is_set() and time.monotonic() < read_deadline:
            try:
                chunk = conn.recv(MAX_MESSAGE_BYTES - len(received))
            except socket.timeout:
                continue

            if not chunk:
                break

            received.extend(chunk)
            if b"\n" in received:
                frame, _, _ = received.partition(b"\n")
                return bytes(frame).rstrip(b"\r")

            # Preserve compatibility with callers that send the exact legacy
            # command without a delimiter and then wait for the response.
            if bytes(received) == expected_command:
                return bytes(received)

            if (
                len(received) >= MAX_MESSAGE_BYTES
                or not expected_command.startswith(received)
            ):
                break

        return bytes(received)

    @property
    @abstractmethod
    def get_current_command(self) -> bytes:
        """
        This property must be implemented by each subclass to provide the specific
        command to get the current measurement.
        """
        raise NotImplementedError(NotImplementedErrorMsg)

    @abstractmethod
    def measure_current(self) -> float:
        """
        This method must be implemented by each subclass to provide the specific
        logic for current measurement.
        """
        raise NotImplementedError(NotImplementedErrorMsg)

