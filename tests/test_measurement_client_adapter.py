import unittest
from unittest.mock import patch

from Ammeters.client import AmmeterClientError
from src.application.errors.measurement_request_error import (
    MeasurementRequestError,
)
from src.infrastructure.clients.read_ammeter_current import (
    read_ammeter_current,
)


class MeasurementClientAdapterTests(unittest.TestCase):
    @patch(
        "src.infrastructure.clients.read_ammeter_current."
        "request_current_from_ammeter"
    )
    def test_passes_transport_settings_and_returns_current(
        self,
        request_current,
    ) -> None:
        request_current.return_value = 1.25

        current = read_ammeter_current(
            43210,
            b"MEASURE",
            host="127.0.0.1",
            connect_timeout_seconds=1.0,
            read_timeout_seconds=2.0,
        )

        self.assertEqual(current, 1.25)
        request_current.assert_called_once_with(
            43210,
            b"MEASURE",
            host="127.0.0.1",
            connect_timeout_seconds=1.0,
            read_timeout_seconds=2.0,
        )

    @patch(
        "src.infrastructure.clients.read_ammeter_current."
        "request_current_from_ammeter"
    )
    def test_maps_transport_errors_to_the_application_contract(
        self,
        request_current,
    ) -> None:
        transport_error = AmmeterClientError("connection refused")
        request_current.side_effect = transport_error

        with self.assertRaisesRegex(
            MeasurementRequestError,
            "connection refused",
        ) as raised:
            read_ammeter_current(
                43210,
                b"MEASURE",
                host="127.0.0.1",
                connect_timeout_seconds=1.0,
                read_timeout_seconds=2.0,
            )

        self.assertIs(raised.exception.__cause__, transport_error)


if __name__ == "__main__":
    unittest.main()
