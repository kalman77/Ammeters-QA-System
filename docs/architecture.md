# Architecture

The combined Phase 1 through Phase 3 implementation uses a small Clean
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
       -> application use cases
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
| Domain | Immutable settings, measurements, sampling slots/results, statuses, and error details |
| Application | Normalize selectors, resolve sampling plans, validate readings, and execute measurement/sampling use cases through abstract ports |
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
- `RunningEmulator`

Each extracted, Phase 2, or Phase 3 operation also has a dedicated module:

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
and other statistical analysis remain Phase 4 responsibilities.

## Public and compatibility contracts

The architecture retains the earlier interfaces and adds the Phase 3 sampling
contracts:

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
module lists include the Phase 2/3 measurement, sampling, validation, timing,
presentation, and serialization components. Dependency checks also keep domain
models independent from outer layers and prevent application policies from
importing infrastructure, presentation, bootstrap, framework, YAML, or system
time implementations directly.
