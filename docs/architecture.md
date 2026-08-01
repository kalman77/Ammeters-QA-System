# Architecture

The combined Phase 1 through Phase 4 implementation uses a small Clean
Architecture–style separation.
The goal is to keep policies and models independent from socket and YAML
implementations and from console output while avoiding unnecessary framework
code.

## Dependency direction

```text
main.py
  -> bootstrap
       -> application use case
       -> infrastructure adapters
       -> presentation adapter

examples / API users
  -> AmmeterTestFramework facade
       -> measurement, sampling, and analysis use cases
       -> infrastructure adapters
       -> result serialization

application
  -> domain models
  -> application ports

infrastructure
  -> domain models
  -> application error contracts
  -> existing Ammeters adapters

domain
  -> Python standard library only
```

The application layer imports neither `Ammeters` nor `src.infrastructure`.
Instead, the bootstrap layer and public framework facade inject the emulator
starter, emulator stopper, measurement client, monotonic clock, and UTC clock
through application port protocols. Phase 3 also injects a sleeper, keeping
wall-clock sleeping out of the fixed-deadline scheduling policy.

## Responsibilities

| Layer | Responsibility |
|---|---|
| Domain | Immutable settings, measurements, sampling slots/results, statistical analyses, statuses, and error details |
| Application | Normalize selectors, resolve sampling plans, validate readings, and execute measurement, sampling, and statistical-analysis use cases through abstract ports |
| Infrastructure/config | Load YAML and extract runtime or sampling configuration |
| Infrastructure/emulators | Register, start, monitor, join, and stop emulators |
| Infrastructure/clients | Adapt socket-client failures to application errors |
| Infrastructure/time | Provide monotonic and timezone-aware UTC clocks plus sleeping |
| Bootstrap | Select concrete adapters and compose dependencies |
| Presentation | Format console tables and serialize typed results |
| `AmmeterTestFramework` | Expose typed and serialized public APIs and compose their default adapters |
| `main.py` | Preserve the public entry point and CLI error boundary |

## File granularity

Each dataclass has its own module:

- `AmmeterSettings`
- `NetworkSettings`
- `RuntimeSettings`
- `Measurement`
- `MeasurementError`
- `MeasurementResult`
- `SamplingSettings`
- `SampleResult`
- `SamplingResult`
- `CurrentStatistics`
- `SamplingAnalysis`
- `RunningEmulator`

Each extracted Phase 2, Phase 3, or Phase 4 operation also has a dedicated
module:

- YAML loading
- Positive-number resolution
- Runtime configuration resolution
- Emulator serving
- Emulator startup
- Thread joining
- Emulator shutdown
- Ammeter-type normalization and settings selection
- Current validation and running-emulator measurement
- Single-ammeter and smoke-test use cases
- Socket-client error adaptation
- Monotonic and UTC clock access
- Smoke-test and typed-result table formatting
- Smoke-test and typed-result printing
- Typed-result serialization
- Sampling-setting extraction and resolution
- Framework config/override selection
- Fixed-deadline waiting and scheduled-sample collection
- Ammeter sampling orchestration
- Sleep adaptation
- Sampling-result formatting and printing
- Sampling-result serialization
- Current-statistics calculation
- Successful-sample analysis
- Analysis-result formatting and printing
- Analysis-result serialization
- Application composition

Protocol classes are similarly separated under `src/application/ports`.
The framework itself remains one cohesive facade: its methods select between
the typed single/all APIs and their serialized compatibility forms.

## Phase 2 result contract

`AmmeterTestFramework.measure()` is the canonical API and returns an immutable
`MeasurementResult`. A result contains the normalized ammeter type, status,
timezone-aware UTC timestamp, whole-operation elapsed time, current and unit,
request latency, and structured errors.

Status invariants are enforced by the domain model:

- `SUCCESS` requires a measurement and no errors.
- `FAILED` requires one or more errors and no measurement.
- `PARTIAL` requires both a valid measurement and one or more errors.

Expected startup, request, validation, and shutdown failures become
`MeasurementError` entries with stable `MeasurementErrorCode` values.
Configuration failures and invalid or unsupported selectors raise typed caller
exceptions before a measurement run begins.

`run_test()` executes `measure()` and passes its result through the dedicated
`measurement_result_to_dict()` presentation adapter. Enum values become strings,
UTC timestamps use an ISO 8601 `Z` suffix, and errors become dictionaries, so
the returned structure can be passed directly to a JSON encoder.

`measure_all()` and `run_all_tests()` apply the typed and serialized contracts,
respectively, to every configured ammeter.

## Phase 3 sampling contract

`SamplingSettings` stores the fully resolved count (`N`), duration (`D`), and
frequency (`F`) and enforces `N = D * F`. The application resolver accepts any
two values and derives the third, or validates a complete triple. A duration and
frequency must produce a whole-number count. Count, duration, and frequency are
bounded before startup to prevent accidental unbounded loops, allocations, or
platform sleep durations. The public limits are 100,000 measurements, 86,400
seconds (24 hours), and 10,000 Hz per sampling run.

The schedule treats the duration as a half-open window `[0, D)`. Slot `i` has a
fixed target at `i / F` and ends at `(i + 1) / F`. All targets derive from one
monotonic origin rather than the completion time of the previous request, which
prevents accumulated drift.

The sleeper and monotonic clock are application ports. The concrete `time.sleep`
and `time.monotonic` adapters remain in infrastructure and are injected by the
framework facade. Deterministic tests can therefore advance a fake clock without
real delays.

If the scheduler reaches a slot at or after its end, it creates a failed
`SampleResult` with `SAMPLING_SLOT_MISSED` and does not issue a catch-up request.
Requests are not retried. Every sampling run that starts has exactly one result
for each configured slot.

`SamplingResult` aggregates the resolved settings, scheduled/actual timing,
nested `MeasurementResult` values, and lifecycle errors:

- `SUCCESS` requires all `N` slots to succeed and no lifecycle errors.
- `PARTIAL` requires at least one successful slot plus a slot or lifecycle
  failure.
- `FAILED` requires no successful slots and at least one failure.

The framework resolves sampling lazily. Its Phase 1/2 APIs remain usable when a
custom configuration omits `testing.sampling`. Supplying any per-call override
switches to explicit-override mode: values are not merged with YAML, at least
two must be provided, and the third is derived.

`sample()` and `sample_all()` expose typed results.
`run_sampling_test()` and `run_all_sampling_tests()` serialize the same results
through `sampling_result_to_dict()`.

## Phase 3 boundary

Sampling output contains raw current values, request latency, schedule timing,
drift, and failure counts. Mean, median, standard deviation, minimum, maximum,
and their reporting are layered on separately by Phase 4.

## Phase 4 analysis contract

Phase 4 adds two immutable domain models. `CurrentStatistics` holds the number
of analyzed measurements, mean, median, population standard deviation, minimum,
maximum, and unit. `SamplingAnalysis` pairs optional statistics with the exact
`SamplingResult` from which they were derived, preserving measurement, timing,
status, and error provenance.

Phase 4 follows the existing dependency direction:

| Layer | Dedicated modules |
|---|---|
| Domain | `current_statistics.py`, `sampling_analysis.py`, `services/calculate_current_statistics.py` |
| Application | `analyze_sampling_result.py` |
| Presentation | `sampling_analysis_to_dict.py`, `format_analysis_results_table.py`, `print_analysis_results.py` |
| Public facade/example | `test_framework.py`, `examples/run_analysis.py` |

The analysis policy is split between a pure domain service and an application
use case:

- `calculate_current_statistics()` validates a finite iterable and computes
  the metrics without importing presentation, infrastructure, or the public
  framework facade.
- `analyze_sampling_result()` validates the source contract and creates a
  `SamplingAnalysis`. That immutable model selects `SUCCESS` measurements and
  derives its statistics through the domain service, so callers cannot pair a
  sampling result with conflicting metrics.

Failed and missed slots therefore never distort the numeric metrics, but they
remain present in the attached sampling result. A partial run has statistics
when one or more slots succeeded and retains its `PARTIAL` aggregate status and
errors. A run with no successful slots has `statistics=None`; the architecture
does not represent missing data as zero or `NaN`.

A singleton population has equal mean, median, minimum, and maximum and a
standard deviation of zero. For larger inputs, population standard deviation is
used intentionally because the successful values form the complete observed
population for the run. The calculation uses Python's standard-library
`statistics.mean` and `statistics.pstdev`; Phase 4 adds no NumPy, SciPy, pandas,
or other analysis dependency.

The framework facade exposes typed `analyze()` and `analyze_all()` methods.
`run_analysis()` and `run_all_analyses()` pass those typed values through the
dedicated `sampling_analysis_to_dict()` presentation adapter. Serialized output
contains summary counts, optional metrics, an explicit `population` deviation
label, and the full serialized sampling result. Console formatting and printing
are presentation-only modules, and `examples/run_analysis.py` demonstrates the
typed all-ammeter path.

## Phase 4 boundary

Required descriptive statistics and their console/serialized reporting are in
scope. Visualization and performance-consistency evaluation remain optional
bonus work. Unique run identification, metadata archives, historical retrieval,
and comparison are deferred to Phase 5 result management.

## Public and compatibility contracts

The architecture retains the earlier interfaces and adds the Phase 3 sampling
and Phase 4 analysis contracts:

- `main.main(config_path=..., emit=...)`
- `main.DEFAULT_CONFIG_PATH`
- `Ammeters.client.request_current_from_ammeter`
- `Ammeters.base_ammeter.AmmeterEmulatorBase`
- `src.utils.config.load_config`
- `AmmeterTestFramework.measure()` and `measure_all()` for typed results
- `AmmeterTestFramework.run_test()` and `run_all_tests()` for JSON-friendly
  dictionaries
- `AmmeterTestFramework.sample()` and `sample_all()` for typed sampling results
- `AmmeterTestFramework.run_sampling_test()` and
  `run_all_sampling_tests()` for JSON-friendly sampling dictionaries
- `AmmeterTestFramework.analyze()` and `analyze_all()` for typed statistical
  analyses
- `AmmeterTestFramework.run_analysis()` and `run_all_analyses()` for
  JSON-friendly analysis dictionaries
- Measurement order and console formatting
- Startup, timeout, cleanup, and error-precedence behavior

The original `Ammeters` package remains in place as an infrastructure adapter.
Moving those emulators would add compatibility risk without improving the
application dependency direction.

## Architecture checks

`tests/test_architecture.py` prevents the main entry point from accumulating
configuration, threading, socket, or concrete-emulator responsibilities again.
It also verifies one dataclass/operation per selected module and prevents the
application layer from importing infrastructure implementations. The checked
module lists include the Phase 2/3/4 measurement, sampling, analysis,
validation, timing, presentation, and serialization components. Dependency
checks also keep domain models independent from outer layers and prevent
application policies from importing infrastructure, presentation, bootstrap,
framework, YAML, or system time implementations directly.
