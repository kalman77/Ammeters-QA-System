import unittest
from types import SimpleNamespace

from src.application.use_cases.run_ammeter_smoke_test import (
    run_ammeter_smoke_test,
)
from src.domain.models.ammeter_settings import AmmeterSettings
from src.domain.models.network_settings import NetworkSettings
from src.domain.models.runtime_settings import RuntimeSettings


class AmmeterSmokeTestUseCaseTests(unittest.TestCase):
    def test_request_failure_still_stops_and_remains_primary_error(self) -> None:
        ammeter_settings = AmmeterSettings(
            name="greenlee",
            port=0,
            command=b"CONFIGURED_COMMAND",
        )
        runtime_settings = RuntimeSettings(
            network=NetworkSettings(
                host="127.0.0.1",
                connect_timeout_seconds=1.0,
                read_timeout_seconds=2.0,
                startup_timeout_seconds=3.0,
                shutdown_timeout_seconds=4.0,
            ),
            ammeters=(ammeter_settings,),
        )
        running_emulator = SimpleNamespace(
            settings=ammeter_settings,
            emulator=SimpleNamespace(port=43210),
        )
        request_error = LookupError("measurement request failed")
        shutdown_error = RuntimeError("shutdown failed")
        observed = {}

        def start_emulators(settings, stop_event):
            observed["start_settings"] = settings
            observed["stop_event"] = stop_event
            return [running_emulator]

        def request_current(port, command, **network):
            observed["request"] = (port, command, network)
            raise request_error

        def stop_emulators(running, stop_event, timeout_seconds):
            observed["stop"] = (running, stop_event, timeout_seconds)
            raise shutdown_error

        with self.assertRaises(LookupError) as raised:
            run_ammeter_smoke_test(
                runtime_settings,
                start_emulators=start_emulators,
                stop_emulators=stop_emulators,
                request_current=request_current,
            )

        self.assertIs(raised.exception, request_error)
        self.assertIs(observed["start_settings"], runtime_settings)
        self.assertEqual(observed["request"][0], 43210)
        self.assertEqual(observed["request"][1], b"CONFIGURED_COMMAND")
        self.assertEqual(
            observed["request"][2],
            {
                "host": "127.0.0.1",
                "connect_timeout_seconds": 1.0,
                "read_timeout_seconds": 2.0,
            },
        )
        stopped, stop_event, timeout_seconds = observed["stop"]
        self.assertEqual(stopped, [running_emulator])
        self.assertIs(stop_event, observed["stop_event"])
        self.assertEqual(timeout_seconds, 4.0)
