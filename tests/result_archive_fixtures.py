from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from src.domain.enums.measurement_error_code import MeasurementErrorCode
from src.domain.enums.measurement_status import MeasurementStatus
from src.domain.models.archived_test_run import ArchivedTestRun
from src.domain.models.measurement_error import MeasurementError
from src.domain.models.measurement_result import MeasurementResult
from src.domain.models.run_metadata_entry import RunMetadataEntry
from src.domain.models.sample_result import SampleResult
from src.domain.models.sampling_analysis import SamplingAnalysis
from src.domain.models.sampling_result import SamplingResult
from src.domain.models.sampling_settings import SamplingSettings


RUN_ID = "123e4567-e89b-42d3-a456-426614174000"
SECOND_RUN_ID = "123e4567-e89b-42d3-a456-426614174001"
THIRD_RUN_ID = "123e4567-e89b-42d3-a456-426614174002"
SAMPLING_STARTED_AT = datetime(
    2026,
    8,
    1,
    12,
    0,
    tzinfo=timezone.utc,
)


def build_archived_test_run(
    *,
    run_id: str = RUN_ID,
    archived_at_utc: Optional[datetime] = None,
    ammeter_type: str = "greenlee",
    currents: Tuple[float, float] = (1.0, 3.0),
    metadata: Tuple[RunMetadataEntry, ...] = (
        RunMetadataEntry(key="firmware", value="1.4.2"),
        RunMetadataEntry(key="operator", value="Nir"),
    ),
) -> ArchivedTestRun:
    """Build one complete immutable archive fixture with two samples."""
    samples = tuple(
        SampleResult(
            sample_index=index,
            scheduled_elapsed_seconds=index * 0.5,
            started_elapsed_seconds=index * 0.5,
            completed_elapsed_seconds=index * 0.5 + 0.1,
            result=MeasurementResult(
                ammeter_type=ammeter_type,
                status=MeasurementStatus.SUCCESS,
                timestamp_utc=SAMPLING_STARTED_AT
                + timedelta(seconds=index * 0.5 + 0.1),
                elapsed_seconds=0.1,
                current=current,
                unit="A",
                request_latency_seconds=0.1,
                errors=(),
            ),
        )
        for index, current in enumerate(currents)
    )
    sampling_result = SamplingResult(
        ammeter_type=ammeter_type,
        status=MeasurementStatus.SUCCESS,
        timestamp_utc=SAMPLING_STARTED_AT + timedelta(seconds=1.1),
        elapsed_seconds=1.1,
        sampling_started_at_utc=SAMPLING_STARTED_AT,
        sampling_elapsed_seconds=1.0,
        settings=SamplingSettings(
            measurements_count=2,
            total_duration_seconds=1.0,
            sampling_frequency_hz=2.0,
        ),
        samples=samples,
        errors=(),
        unit="A",
    )
    return ArchivedTestRun(
        run_id=run_id,
        archived_at_utc=(
            archived_at_utc
            if archived_at_utc is not None
            else SAMPLING_STARTED_AT + timedelta(seconds=2.0)
        ),
        analysis=SamplingAnalysis(sampling_result=sampling_result),
        metadata=metadata,
    )


def build_failed_archived_test_run(
    *,
    run_id: str = SECOND_RUN_ID,
    ammeter_type: str = "greenlee",
    metadata: Tuple[RunMetadataEntry, ...] = (),
) -> ArchivedTestRun:
    """Build one startup-failed archive without statistical data."""
    sampling_result = SamplingResult(
        ammeter_type=ammeter_type,
        status=MeasurementStatus.FAILED,
        timestamp_utc=SAMPLING_STARTED_AT + timedelta(seconds=0.1),
        elapsed_seconds=0.1,
        sampling_started_at_utc=None,
        sampling_elapsed_seconds=None,
        settings=SamplingSettings(
            measurements_count=2,
            total_duration_seconds=1.0,
            sampling_frequency_hz=2.0,
        ),
        samples=(),
        errors=(
            MeasurementError(
                code=MeasurementErrorCode.EMULATOR_START_FAILED,
                message="startup failed",
            ),
        ),
        unit="A",
    )
    return ArchivedTestRun(
        run_id=run_id,
        archived_at_utc=SAMPLING_STARTED_AT + timedelta(seconds=2),
        analysis=SamplingAnalysis(sampling_result),
        metadata=metadata,
    )


def build_partial_archived_test_run(
    *,
    run_id: str = THIRD_RUN_ID,
    ammeter_type: str = "greenlee",
) -> ArchivedTestRun:
    """Build an archive with one successful and one failed sample."""
    successful_measurement = MeasurementResult(
        ammeter_type=ammeter_type,
        status=MeasurementStatus.SUCCESS,
        timestamp_utc=SAMPLING_STARTED_AT + timedelta(seconds=0.1),
        elapsed_seconds=0.1,
        current=2.5,
        unit="A",
        request_latency_seconds=0.1,
        errors=(),
    )
    failed_measurement = MeasurementResult(
        ammeter_type=ammeter_type,
        status=MeasurementStatus.FAILED,
        timestamp_utc=SAMPLING_STARTED_AT + timedelta(seconds=0.6),
        elapsed_seconds=0.1,
        current=None,
        unit="A",
        request_latency_seconds=None,
        errors=(
            MeasurementError(
                code=MeasurementErrorCode.MEASUREMENT_REQUEST_FAILED,
                message="request failed",
            ),
        ),
    )
    samples = (
        SampleResult(
            sample_index=0,
            scheduled_elapsed_seconds=0.0,
            started_elapsed_seconds=0.0,
            completed_elapsed_seconds=0.1,
            result=successful_measurement,
        ),
        SampleResult(
            sample_index=1,
            scheduled_elapsed_seconds=0.5,
            started_elapsed_seconds=0.5,
            completed_elapsed_seconds=0.6,
            result=failed_measurement,
        ),
    )
    sampling_result = SamplingResult(
        ammeter_type=ammeter_type,
        status=MeasurementStatus.PARTIAL,
        timestamp_utc=SAMPLING_STARTED_AT + timedelta(seconds=1.1),
        elapsed_seconds=1.1,
        sampling_started_at_utc=SAMPLING_STARTED_AT,
        sampling_elapsed_seconds=1.0,
        settings=SamplingSettings(
            measurements_count=2,
            total_duration_seconds=1.0,
            sampling_frequency_hz=2.0,
        ),
        samples=samples,
        errors=(),
        unit="A",
    )
    return ArchivedTestRun(
        run_id=run_id,
        archived_at_utc=SAMPLING_STARTED_AT + timedelta(seconds=3),
        analysis=SamplingAnalysis(sampling_result),
        metadata=(),
    )
