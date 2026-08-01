import copy
import math
import unittest
from dataclasses import FrozenInstanceError

from src.domain.models.runtime_settings import RuntimeSettings
from src.infrastructure.config.resolve_runtime_settings import (
    resolve_runtime_settings,
)


AMMETER_NAMES = ("greenlee", "entes", "circutor")


def valid_config() -> dict:
    return {
        "network": {
            "host": " 127.0.0.1 ",
            "connect_timeout_seconds": 1,
            "read_timeout_seconds": 2.0,
            "startup_timeout_seconds": 3,
            "shutdown_timeout_seconds": 4,
        },
        "ammeters": {
            "circutor": {"port": 0, "command": "C"},
            "greenlee": {"port": 0, "command": "G"},
            "entes": {"port": 0, "command": "E"},
        },
    }


class RuntimeSettingsTests(unittest.TestCase):
    def test_resolves_typed_immutable_settings_in_registry_order(self) -> None:
        settings = resolve_runtime_settings(valid_config(), AMMETER_NAMES)

        self.assertIsInstance(settings, RuntimeSettings)
        self.assertEqual(settings.network.host, "127.0.0.1")
        self.assertEqual(
            [ammeter.name for ammeter in settings.ammeters],
            list(AMMETER_NAMES),
        )
        self.assertEqual(
            [ammeter.command for ammeter in settings.ammeters],
            [b"G", b"E", b"C"],
        )
        with self.assertRaises(FrozenInstanceError):
            settings.network.host = "changed"

    def test_rejects_duplicate_nonzero_ports_but_allows_repeated_zero(self) -> None:
        resolve_runtime_settings(valid_config(), AMMETER_NAMES)
        config = valid_config()
        config["ammeters"]["greenlee"]["port"] = 5000
        config["ammeters"]["entes"]["port"] = 5000

        with self.assertRaisesRegex(ValueError, "duplicates port 5000"):
            resolve_runtime_settings(config, AMMETER_NAMES)

    def test_rejects_invalid_timeout_values(self) -> None:
        invalid_values = [True, 0, -1, math.nan, math.inf]
        for invalid_value in invalid_values:
            with self.subTest(value=invalid_value):
                config = valid_config()
                config["network"][
                    "read_timeout_seconds"
                ] = invalid_value
                with self.assertRaisesRegex(ValueError, "positive number"):
                    resolve_runtime_settings(config, AMMETER_NAMES)

    def test_rejects_invalid_ports(self) -> None:
        invalid_values = [True, -1, 65536, "5000"]
        for invalid_value in invalid_values:
            with self.subTest(value=invalid_value):
                config = valid_config()
                config["ammeters"]["greenlee"]["port"] = invalid_value
                with self.assertRaisesRegex(ValueError, "port must be"):
                    resolve_runtime_settings(config, AMMETER_NAMES)

    def test_rejects_missing_meter_and_line_delimited_command(self) -> None:
        missing_meter = valid_config()
        del missing_meter["ammeters"]["entes"]
        with self.assertRaisesRegex(ValueError, "ammeters.entes"):
            resolve_runtime_settings(missing_meter, AMMETER_NAMES)

        line_delimited = copy.deepcopy(valid_config())
        line_delimited["ammeters"]["entes"]["command"] = "E\nSECOND"
        with self.assertRaisesRegex(ValueError, "line delimiters"):
            resolve_runtime_settings(line_delimited, AMMETER_NAMES)
