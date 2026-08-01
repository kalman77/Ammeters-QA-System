import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.application.errors.result_management_configuration_error import (
    ResultManagementConfigurationError,
)
from src.infrastructure.config.read_result_archive_directory import (
    read_result_archive_directory,
)


class ResultManagementConfigurationTests(unittest.TestCase):
    def test_rejects_missing_or_invalid_configuration_shapes(
        self,
    ) -> None:
        invalid_configurations = (
            [],
            {},
            {"result_management": None},
            {"result_management": []},
            {"result_management": {}},
            {"result_management": {"archive_directory": None}},
            {"result_management": {"archive_directory": 1}},
            {"result_management": {"archive_directory": "  "}},
        )
        for config in invalid_configurations:
            with self.subTest(config=config):
                with self.assertRaises(
                    ResultManagementConfigurationError
                ):
                    read_result_archive_directory(
                        config,
                        "config.yaml",
                    )

    def test_resolves_trimmed_relative_path_without_creating_it(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary_directory:
            config_path = (
                Path(temporary_directory) / "config" / "ammeter.yaml"
            )
            expected = (
                config_path.parent / "history" / "archive"
            ).resolve()

            resolved = read_result_archive_directory(
                {
                    "result_management": {
                        "archive_directory": " history/archive "
                    }
                },
                config_path,
            )

            self.assertEqual(resolved, expected)
            self.assertFalse(resolved.exists())

    def test_preserves_absolute_archive_path(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            expected = (
                Path(temporary_directory) / "absolute-history"
            ).resolve()

            resolved = read_result_archive_directory(
                {
                    "result_management": {
                        "archive_directory": str(expected)
                    }
                },
                "ignored.yaml",
            )

            self.assertEqual(resolved, expected)
            self.assertFalse(resolved.exists())

    def test_invalid_config_path_is_a_typed_error(self) -> None:
        with self.assertRaises(ResultManagementConfigurationError):
            read_result_archive_directory(
                {
                    "result_management": {
                        "archive_directory": "history"
                    }
                },
                None,
            )


if __name__ == "__main__":
    unittest.main()
