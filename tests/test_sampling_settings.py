import math
import unittest
from dataclasses import FrozenInstanceError
from types import MappingProxyType

from src.application.errors.sampling_configuration_error import (
    SamplingConfigurationError,
)
from src.application.use_cases.resolve_sampling_settings import (
    resolve_sampling_settings,
)
from src.domain.models.sampling_settings import SamplingSettings
from src.infrastructure.config.read_sampling_settings import (
    read_sampling_settings,
)


class SamplingSettingsTests(unittest.TestCase):
    def test_derives_each_missing_value_from_the_other_two(self) -> None:
        cases = (
            (
                (5, None, 2),
                SamplingSettings(
                    measurements_count=5,
                    total_duration_seconds=2.5,
                    sampling_frequency_hz=2.0,
                ),
            ),
            (
                (5, 2.5, None),
                SamplingSettings(
                    measurements_count=5,
                    total_duration_seconds=2.5,
                    sampling_frequency_hz=2.0,
                ),
            ),
            (
                (None, 2.5, 2),
                SamplingSettings(
                    measurements_count=5,
                    total_duration_seconds=2.5,
                    sampling_frequency_hz=2.0,
                ),
            ),
        )

        for provided, expected in cases:
            with self.subTest(provided=provided):
                self.assertEqual(
                    resolve_sampling_settings(*provided),
                    expected,
                )

    def test_accepts_consistent_three_value_plan_and_normalizes_numbers(
        self,
    ) -> None:
        settings = resolve_sampling_settings(6, 2, 3)

        self.assertEqual(settings.measurements_count, 6)
        self.assertEqual(settings.total_duration_seconds, 2.0)
        self.assertIsInstance(settings.total_duration_seconds, float)
        self.assertEqual(settings.sampling_frequency_hz, 3.0)
        self.assertIsInstance(settings.sampling_frequency_hz, float)

    def test_accepts_floating_point_rounding_when_deriving_count(self) -> None:
        settings = resolve_sampling_settings(None, 0.3, 10.0)

        self.assertEqual(settings.measurements_count, 3)
        self.assertTrue(
            math.isclose(
                settings.total_duration_seconds
                * settings.sampling_frequency_hz,
                3.0,
            )
        )

    def test_rejects_fewer_than_two_configured_values(self) -> None:
        invalid_values = (
            (None, None, None),
            (5, None, None),
            (None, 1.0, None),
            (None, None, 5.0),
        )

        for provided in invalid_values:
            with self.subTest(provided=provided):
                with self.assertRaisesRegex(
                    SamplingConfigurationError,
                    "at least two",
                ):
                    resolve_sampling_settings(*provided)

    def test_rejects_invalid_measurement_counts(self) -> None:
        invalid_counts = (True, 0, -1, 2.5, "2")

        for count in invalid_counts:
            with self.subTest(count=count):
                with self.assertRaisesRegex(
                    SamplingConfigurationError,
                    "positive integer",
                ):
                    resolve_sampling_settings(count, 1.0, None)

    def test_rejects_invalid_duration_and_frequency_values(self) -> None:
        invalid_values = (
            True,
            0,
            -0.1,
            math.nan,
            math.inf,
            "2.0",
        )

        for value in invalid_values:
            for field_name, provided in (
                (
                    "total_duration_seconds",
                    (2, value, None),
                ),
                (
                    "sampling_frequency_hz",
                    (2, None, value),
                ),
            ):
                with self.subTest(field=field_name, value=value):
                    with self.assertRaisesRegex(
                        SamplingConfigurationError,
                        field_name,
                    ):
                        resolve_sampling_settings(*provided)

    def test_rejects_non_integral_derived_count(self) -> None:
        with self.assertRaisesRegex(
            SamplingConfigurationError,
            "whole number",
        ):
            resolve_sampling_settings(None, 1.0, 2.5)

    def test_extreme_values_raise_the_typed_configuration_error(self) -> None:
        with self.assertRaises(SamplingConfigurationError):
            resolve_sampling_settings(None, 1e308, 2.0)
        with self.assertRaises(SamplingConfigurationError):
            resolve_sampling_settings(10**1000, None, 1e-300)

    def test_rejects_fractional_large_count_and_resource_excesses(self) -> None:
        with self.assertRaisesRegex(
            SamplingConfigurationError,
            "whole number",
        ):
            resolve_sampling_settings(None, 9_999.999995, 10.0)

        with self.assertRaisesRegex(
            SamplingConfigurationError,
            "measurements_count =",
        ):
            resolve_sampling_settings(100_000, 9_999.999995, 10.0)

        invalid_values = (
            (100_001, 1.0, None),
            (1, 86_401.0, None),
            (1, None, 10_001.0),
        )
        for provided in invalid_values:
            with self.subTest(provided=provided):
                with self.assertRaises(SamplingConfigurationError):
                    resolve_sampling_settings(*provided)

    def test_rejects_inconsistent_three_value_plan(self) -> None:
        with self.assertRaisesRegex(
            SamplingConfigurationError,
            "measurements_count =",
        ):
            resolve_sampling_settings(5, 2.0, 2.0)

    def test_sampling_settings_enforce_consistency_when_built_directly(
        self,
    ) -> None:
        invalid_settings = (
            (True, 1.0, 1.0),
            (0, 1.0, 1.0),
            (1, 0.0, 1.0),
            (1, 1.0, math.inf),
            (2, 1.0, 1.0),
            (100_001, 1.0, 100_001.0),
            (1, 86_401.0, 1.0 / 86_401.0),
            (1, 1.0 / 10_001.0, 10_001.0),
        )

        for values in invalid_settings:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    SamplingSettings(*values)

    def test_sampling_settings_are_immutable(self) -> None:
        settings = SamplingSettings(
            measurements_count=5,
            total_duration_seconds=2.5,
            sampling_frequency_hz=2.0,
        )

        with self.assertRaises(FrozenInstanceError):
            settings.measurements_count = 10

    def test_reads_and_resolves_sampling_mapping(self) -> None:
        settings = read_sampling_settings(
            {
                "testing": {
                    "sampling": {
                        "measurements_count": 4,
                        "total_duration_seconds": None,
                        "sampling_frequency_hz": 8,
                    }
                }
            }
        )

        self.assertEqual(
            settings,
            SamplingSettings(
                measurements_count=4,
                total_duration_seconds=0.5,
                sampling_frequency_hz=8.0,
            ),
        )

        proxy_settings = read_sampling_settings(
            MappingProxyType(
                {
                    "testing": MappingProxyType(
                        {
                            "sampling": MappingProxyType(
                                {
                                    "measurements_count": 1,
                                    "total_duration_seconds": 0.5,
                                    "sampling_frequency_hz": 2.0,
                                }
                            )
                        }
                    )
                }
            )
        )
        self.assertEqual(proxy_settings.measurements_count, 1)

    def test_rejects_missing_or_non_mapping_sampling_configuration(
        self,
    ) -> None:
        invalid_configs = (
            {},
            {"testing": None},
            {"testing": []},
            {"testing": {}},
            {"testing": {"sampling": None}},
            {"testing": {"sampling": []}},
        )

        for config in invalid_configs:
            with self.subTest(config=config):
                with self.assertRaises(SamplingConfigurationError):
                    read_sampling_settings(config)


if __name__ == "__main__":
    unittest.main()
