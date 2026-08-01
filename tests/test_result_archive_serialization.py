import copy
import json
import math
import unittest

from src.application.errors.unsupported_archive_schema_error import (
    UnsupportedArchiveSchemaError,
)
from src.domain.models.run_metadata_entry import RunMetadataEntry
from src.infrastructure.persistence.archived_test_run_from_dict import (
    archived_test_run_from_dict,
)
from src.presentation.serialization.archived_test_run_to_dict import (
    ARCHIVE_SCHEMA_VERSION,
    archived_test_run_to_dict,
)
from tests.result_archive_fixtures import (
    build_archived_test_run,
    build_failed_archived_test_run,
    build_partial_archived_test_run,
)


class ResultArchiveSerializationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.archived_run = build_archived_test_run()
        self.document = archived_test_run_to_dict(self.archived_run)

    def test_typed_archive_round_trips_through_json(self) -> None:
        json_document = json.dumps(
            self.document,
            allow_nan=False,
            sort_keys=True,
        )

        restored = archived_test_run_from_dict(json.loads(json_document))

        self.assertEqual(restored, self.archived_run)
        self.assertEqual(
            archived_test_run_to_dict(restored),
            self.document,
        )
        self.assertEqual(
            restored.analysis.statistics.mean_current,
            2.0,
        )
        self.assertEqual(
            tuple(entry.key for entry in restored.metadata),
            ("firmware", "operator"),
        )

    def test_failed_no_statistics_archive_round_trips(self) -> None:
        archived_run = build_failed_archived_test_run()

        restored = archived_test_run_from_dict(
            json.loads(
                json.dumps(
                    archived_test_run_to_dict(archived_run),
                    allow_nan=False,
                )
            )
        )

        self.assertEqual(restored, archived_run)
        self.assertIsNone(restored.analysis.statistics)

    def test_partial_archive_preserves_failures_and_statistics(
        self,
    ) -> None:
        archived_run = build_partial_archived_test_run()

        restored = archived_test_run_from_dict(
            json.loads(
                json.dumps(
                    archived_test_run_to_dict(archived_run),
                    allow_nan=False,
                )
            )
        )

        self.assertEqual(restored, archived_run)
        self.assertEqual(
            restored.analysis.statistics.measurements_count,
            1,
        )

    def test_all_metadata_scalar_types_and_unicode_round_trip(
        self,
    ) -> None:
        archived_run = build_archived_test_run(
            metadata=(
                RunMetadataEntry("approved", True),
                RunMetadataEntry("comment", None),
                RunMetadataEntry("iteration", 7),
                RunMetadataEntry("operator", "ניר"),
                RunMetadataEntry("temperature_c", 24.5),
            )
        )

        restored = archived_test_run_from_dict(
            json.loads(
                json.dumps(
                    archived_test_run_to_dict(archived_run),
                    allow_nan=False,
                    ensure_ascii=False,
                )
            )
        )

        self.assertEqual(restored.metadata, archived_run.metadata)

    def test_rejects_non_mapping_and_missing_archive_fields(self) -> None:
        with self.assertRaises(ValueError):
            archived_test_run_from_dict([])

        missing_run_id = copy.deepcopy(self.document)
        del missing_run_id["run_id"]
        with self.assertRaises((KeyError, ValueError)):
            archived_test_run_from_dict(missing_run_id)

    def test_rejects_unsupported_integer_schema_version(self) -> None:
        document = copy.deepcopy(self.document)
        document["schema_version"] = ARCHIVE_SCHEMA_VERSION + 1

        with self.assertRaises(UnsupportedArchiveSchemaError):
            archived_test_run_from_dict(document)

    def test_rejects_missing_or_non_integer_schema_as_malformed(
        self,
    ) -> None:
        malformed_versions = ("missing", "1", True, None)
        for schema_version in malformed_versions:
            with self.subTest(schema_version=schema_version):
                document = copy.deepcopy(self.document)
                if schema_version == "missing":
                    del document["schema_version"]
                else:
                    document["schema_version"] = schema_version

                with self.assertRaises(ValueError):
                    archived_test_run_from_dict(document)

    def test_rejects_contradictory_derived_statistics(self) -> None:
        document = copy.deepcopy(self.document)
        document["analysis"]["statistics"]["mean_current"] = 999.0

        with self.assertRaisesRegex(
            ValueError,
            "contradicts its sampling result",
        ):
            archived_test_run_from_dict(document)

    def test_accepts_cross_runtime_rounding_of_derived_statistics(
        self,
    ) -> None:
        document = copy.deepcopy(self.document)
        standard_deviation = document["analysis"]["statistics"][
            "standard_deviation_current"
        ]
        document["analysis"]["statistics"][
            "standard_deviation_current"
        ] = math.nextafter(standard_deviation, 0.0)

        restored = archived_test_run_from_dict(document)

        self.assertEqual(restored, self.archived_run)

    def test_rejects_contradictory_analysis_summary(self) -> None:
        document = copy.deepcopy(self.document)
        document["analysis"]["summary"]["analyzed_samples"] = 1

        with self.assertRaisesRegex(
            ValueError,
            "contradicts its sampling result",
        ):
            archived_test_run_from_dict(document)

    def test_rejects_equal_but_differently_typed_summary_values(
        self,
    ) -> None:
        document = copy.deepcopy(self.document)
        analyzed_samples = document["analysis"]["summary"][
            "analyzed_samples"
        ]
        document["analysis"]["summary"]["analyzed_samples"] = float(
            analyzed_samples
        )

        with self.assertRaisesRegex(
            ValueError,
            "contradicts its sampling result",
        ):
            archived_test_run_from_dict(document)

    def test_rejects_noncanonical_extra_or_invalid_archive_data(self) -> None:
        extra_field = copy.deepcopy(self.document)
        extra_field["unexpected"] = True
        with self.assertRaisesRegex(ValueError, "not canonical"):
            archived_test_run_from_dict(extra_field)

        invalid_timestamp = copy.deepcopy(self.document)
        invalid_timestamp["archived_at_utc"] = "2026-08-01T12:00:00"
        with self.assertRaisesRegex(ValueError, "timezone-aware UTC"):
            archived_test_run_from_dict(invalid_timestamp)

        invalid_metadata = copy.deepcopy(self.document)
        invalid_metadata["metadata"] = []
        with self.assertRaisesRegex(ValueError, "metadata must be a mapping"):
            archived_test_run_from_dict(invalid_metadata)

    def test_rejects_nested_sampling_or_measurement_corruption(self) -> None:
        invalid_status = copy.deepcopy(self.document)
        invalid_status["analysis"]["sampling_result"]["samples"][0][
            "result"
        ]["status"] = "unknown"
        with self.assertRaises(ValueError):
            archived_test_run_from_dict(invalid_status)

        invalid_current = copy.deepcopy(self.document)
        invalid_current["analysis"]["sampling_result"]["samples"][0][
            "result"
        ]["current"] = float("inf")
        with self.assertRaises(ValueError):
            archived_test_run_from_dict(invalid_current)


if __name__ == "__main__":
    unittest.main()
