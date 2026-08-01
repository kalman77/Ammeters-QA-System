import io
import socket
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import main as application
from Ammeters.Circutor_Ammeter import CircutorAmmeter
from Ammeters.Entes_Ammeter import EntesAmmeter
from Ammeters.Greenlee_Ammeter import GreenleeAmmeter
from Ammeters.base_ammeter import AmmeterEmulatorBase
from Ammeters.client import AmmeterClientError, request_current_from_ammeter
from src.utils.config import load_config


class FixedAmmeter(AmmeterEmulatorBase):
    @property
    def get_current_command(self) -> bytes:
        return b"MEASURE_FIXED"

    def measure_current(self) -> float:
        return 12.5


class PhaseOneTests(unittest.TestCase):
    def _new_ammeter_threads(
        self, baseline: set[int]
    ) -> list[threading.Thread]:
        return [
            thread
            for thread in threading.enumerate()
            if thread.name.startswith("ammeter-") and id(thread) not in baseline
        ]

    def _start_fixed_ammeter(
        self,
    ) -> tuple[FixedAmmeter, threading.Event, threading.Thread]:
        ready_event = threading.Event()
        stop_event = threading.Event()
        ammeter = FixedAmmeter(0)
        thread = threading.Thread(
            target=ammeter.start_server,
            kwargs={"ready_event": ready_event, "stop_event": stop_event},
            name="test-fixed-ammeter",
        )
        thread.start()
        self.addCleanup(self._stop_thread, stop_event, thread)
        self.assertTrue(ready_event.wait(2.0), "emulator did not become ready")
        return ammeter, stop_event, thread

    def _stop_thread(
        self, stop_event: threading.Event, thread: threading.Thread
    ) -> None:
        stop_event.set()
        thread.join(2.0)
        self.assertFalse(thread.is_alive(), "emulator thread did not stop")

    def _temporary_config(
        self,
        directory: str,
        *,
        greenlee_port: int = 0,
        entes_port: int = 0,
        circutor_port: int = 0,
    ) -> Path:
        config_path = Path(directory) / "config.yaml"
        config_path.write_text(
            f"""
network:
  host: "127.0.0.1"
  connect_timeout_seconds: 1.0
  read_timeout_seconds: 1.0
  startup_timeout_seconds: 2.0
  shutdown_timeout_seconds: 2.0
ammeters:
  greenlee:
    port: {greenlee_port}
    command: "TEST_GREENLEE"
  entes:
    port: {entes_port}
    command: "TEST_ENTES"
  circutor:
    port: {circutor_port}
    command: "TEST_CIRCUTOR"
""".strip(),
            encoding="utf-8",
        )
        return config_path

    def test_shipped_config_defines_the_canonical_protocols(self) -> None:
        config = load_config(application.DEFAULT_CONFIG_PATH)
        ammeters = config["ammeters"]

        self.assertEqual(
            {name: meter["port"] for name, meter in ammeters.items()},
            {"greenlee": 5000, "entes": 5001, "circutor": 5002},
        )
        self.assertEqual(
            ammeters["circutor"]["command"],
            "MEASURE_CIRCUTOR -get_measurement -current",
        )
        self.assertEqual(len({meter["port"] for meter in ammeters.values()}), 3)

    def test_client_returns_a_float_and_server_stops(self) -> None:
        ammeter, stop_event, thread = self._start_fixed_ammeter()

        current = request_current_from_ammeter(
            ammeter.port,
            b"MEASURE_FIXED",
            connect_timeout_seconds=1.0,
            read_timeout_seconds=1.0,
        )

        self.assertEqual(current, 12.5)
        stop_event.set()
        thread.join(2.0)
        self.assertFalse(thread.is_alive())

    def test_invalid_command_raises_a_clear_client_error(self) -> None:
        ammeter, _, _ = self._start_fixed_ammeter()

        with self.assertRaisesRegex(AmmeterClientError, "invalid measurement"):
            request_current_from_ammeter(
                ammeter.port,
                b"WRONG_COMMAND",
                connect_timeout_seconds=1.0,
                read_timeout_seconds=1.0,
            )

    def test_server_reassembles_a_fragmented_command(self) -> None:
        ammeter, _, _ = self._start_fixed_ammeter()

        with socket.create_connection(
            ("127.0.0.1", ammeter.port), timeout=1.0
        ) as client:
            client.sendall(b"MEASURE_")
            threading.Event().wait(0.02)
            client.sendall(b"FIXED\n")
            received = bytearray()
            while b"\n" not in received:
                chunk = client.recv(1024)
                if not chunk:
                    break
                received.extend(chunk)

        self.assertEqual(bytes(received), b"12.5\n")

    def test_client_reassembles_a_fragmented_response(self) -> None:
        ready_event = threading.Event()
        server_error = []

        def serve_fragmented_response(listener: socket.socket) -> None:
            try:
                listener.listen()
                ready_event.set()
                conn, _ = listener.accept()
                with conn:
                    request = bytearray()
                    while b"\n" not in request:
                        chunk = conn.recv(1024)
                        if not chunk:
                            raise RuntimeError("client closed before sending a frame")
                        request.extend(chunk)
                    conn.sendall(b"12")
                    threading.Event().wait(0.02)
                    conn.sendall(b".5\n")
            except BaseException as exc:
                server_error.append(exc)
                ready_event.set()

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
            thread = threading.Thread(
                target=serve_fragmented_response,
                args=(listener,),
            )
            thread.start()
            try:
                self.assertTrue(ready_event.wait(1.0))
                self.assertEqual(
                    request_current_from_ammeter(
                        port,
                        b"MEASURE_FIXED",
                        connect_timeout_seconds=1.0,
                        read_timeout_seconds=1.0,
                    ),
                    12.5,
                )
            finally:
                thread.join(2.0)

        self.assertFalse(thread.is_alive())
        self.assertEqual(server_error, [])

    def test_idle_client_does_not_block_server_shutdown(self) -> None:
        ammeter, stop_event, thread = self._start_fixed_ammeter()

        with socket.create_connection(("127.0.0.1", ammeter.port), timeout=1.0):
            stop_event.set()
            thread.join(0.5)

        self.assertFalse(thread.is_alive())

    def test_server_can_restart_immediately_on_the_same_port(self) -> None:
        port = 0
        for _ in range(3):
            ready_event = threading.Event()
            stop_event = threading.Event()
            ammeter = FixedAmmeter(port)
            thread = threading.Thread(
                target=ammeter.start_server,
                kwargs={"ready_event": ready_event, "stop_event": stop_event},
            )
            thread.start()
            try:
                self.assertTrue(ready_event.wait(2.0))
                port = ammeter.port
                self.assertEqual(
                    request_current_from_ammeter(
                        port,
                        b"MEASURE_FIXED",
                        connect_timeout_seconds=1.0,
                        read_timeout_seconds=1.0,
                    ),
                    12.5,
                )
            finally:
                stop_event.set()
                thread.join(2.0)
            self.assertFalse(thread.is_alive())

    def test_main_returns_all_measurements_and_can_repeat(self) -> None:
        expected = {"greenlee": 1.25, "entes": 2.5, "circutor": 3.75}
        baseline_threads = {
            id(thread)
            for thread in threading.enumerate()
            if thread.name.startswith("ammeter-")
        }

        with TemporaryDirectory() as directory:
            config_path = self._temporary_config(directory)
            output = io.StringIO()
            with (
                patch.object(
                    GreenleeAmmeter,
                    "measure_current",
                    return_value=expected["greenlee"],
                ),
                patch.object(
                    EntesAmmeter,
                    "measure_current",
                    return_value=expected["entes"],
                ),
                patch.object(
                    CircutorAmmeter,
                    "measure_current",
                    return_value=expected["circutor"],
                ),
                redirect_stdout(output),
            ):
                for _ in range(3):
                    self.assertEqual(application.main(config_path), expected)

        summary = output.getvalue()
        self.assertIn("| GREENLEE | 1.250000 | A", summary)
        self.assertIn("| ENTES    | 2.500000 | A", summary)
        self.assertIn("| CIRCUTOR | 3.750000 | A", summary)
        self.assertEqual(self._new_ammeter_threads(baseline_threads), [])

    def test_startup_failure_is_reported_and_other_servers_are_stopped(self) -> None:
        baseline_threads = {
            id(thread)
            for thread in threading.enumerate()
            if thread.name.startswith("ammeter-")
        }
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied_socket:
            occupied_socket.bind(("127.0.0.1", 0))
            occupied_socket.listen()
            occupied_port = occupied_socket.getsockname()[1]

            with TemporaryDirectory() as directory:
                config_path = self._temporary_config(
                    directory,
                    entes_port=occupied_port,
                )
                with self.assertRaisesRegex(
                    RuntimeError, "Unable to start the entes emulator"
                ):
                    application.main(config_path, emit=False)

        self.assertEqual(self._new_ammeter_threads(baseline_threads), [])

    def test_constructor_failure_stops_previously_started_server(self) -> None:
        baseline_threads = {
            id(thread)
            for thread in threading.enumerate()
            if thread.name.startswith("ammeter-")
        }
        with TemporaryDirectory() as directory:
            config_path = self._temporary_config(directory)
            with (
                patch.object(
                    EntesAmmeter,
                    "__init__",
                    side_effect=RuntimeError("constructor failed"),
                ),
                self.assertRaisesRegex(RuntimeError, "constructor failed"),
            ):
                application.main(config_path, emit=False)

        self.assertEqual(self._new_ammeter_threads(baseline_threads), [])


if __name__ == "__main__":
    unittest.main()
