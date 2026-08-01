import math
import time
from socket import AF_INET, SHUT_WR, SOCK_STREAM, socket


MAX_RESPONSE_BYTES = 1024


class AmmeterClientError(RuntimeError):
    """Raised when an ammeter request cannot produce a valid measurement."""


def request_current_from_ammeter(
    port: int,
    command: bytes,
    *,
    host: str = "127.0.0.1",
    connect_timeout_seconds: float = 2.0,
    read_timeout_seconds: float = 2.0,
) -> float:
    """Request and return a finite current measurement from an ammeter."""
    if not isinstance(command, bytes) or not command:
        raise ValueError("command must be non-empty bytes")
    if b"\n" in command or b"\r" in command:
        raise ValueError("command must not contain line delimiters")

    with socket(AF_INET, SOCK_STREAM) as s:
        try:
            s.settimeout(connect_timeout_seconds)
            s.connect((host, port))
            s.sendall(command + b"\n")
            s.shutdown(SHUT_WR)

            read_deadline = time.monotonic() + read_timeout_seconds
            received = bytearray()
            while True:
                remaining = read_deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("timed out waiting for a complete response")
                s.settimeout(remaining)
                chunk = s.recv(MAX_RESPONSE_BYTES - len(received))
                if not chunk:
                    break
                received.extend(chunk)
                if b"\n" in received:
                    break
                if len(received) >= MAX_RESPONSE_BYTES:
                    raise ValueError("response exceeds the maximum frame size")
        except (OSError, TimeoutError, ValueError) as exc:
            raise AmmeterClientError(
                f"Unable to read an ammeter measurement from {host}:{port}: {exc}"
            ) from exc

    if not received:
        raise AmmeterClientError(
            f"Ammeter at {host}:{port} closed the connection without a response"
        )

    data, _, _ = bytes(received).partition(b"\n")
    data = data.rstrip(b"\r")
    try:
        response = data.decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError as exc:
        raise AmmeterClientError(
            f"Ammeter at {host}:{port} returned a non-UTF-8 response"
        ) from exc

    try:
        current = float(response)
    except ValueError as exc:
        raise AmmeterClientError(
            f"Ammeter at {host}:{port} returned an invalid measurement: {response!r}"
        ) from exc

    if not math.isfinite(current):
        raise AmmeterClientError(
            f"Ammeter at {host}:{port} returned a non-finite measurement"
        )

    return current

