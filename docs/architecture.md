# Architecture

The combined Phase 1 and Phase 2 implementation uses a small Clean
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
through application port protocols.

## Responsibilities

| Layer | Responsibility |
|---|---|
| Domain | Immutable settings, measurements, result envelopes, statuses, and error details |
| Application | Normalize selectors, select meters, validate readings, and execute measurement use cases through abstract ports |
| Infrastructure/config | Load YAML and resolve it into domain models |
| Infrastructure/emulators | Register, start, monitor, join, and stop emulators |
| Infrastructure/clients | Adapt socket-client failures to application errors |
| Infrastructure/time | Provide monotonic and timezone-aware UTC clocks |
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
- `RunningEmulator`

Each extracted or Phase 2 operation also has a dedicated module:

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

## Sampling boundary

Phase 2 intentionally executes one request per selected ammeter. Sampling by
measurement count, duration, or frequency—and the scheduling needed to keep
that sampling precise—belongs to Phase 3. The current sampling keys in
`config/config.yaml` are placeholders and do not affect Phase 2 execution.

## Public and compatibility contracts

The architecture retains the Phase 1 interfaces and defines the Phase 2
framework contracts:

- `main.main(config_path=..., emit=...)`
- `main.DEFAULT_CONFIG_PATH`
- `Ammeters.client.request_current_from_ammeter`
- `Ammeters.base_ammeter.AmmeterEmulatorBase`
- `src.utils.config.load_config`
- `AmmeterTestFramework.measure()` and `measure_all()` for typed results
- `AmmeterTestFramework.run_test()` and `run_all_tests()` for JSON-friendly
  dictionaries
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
module lists include the Phase 2 measurement, validation, timing, presentation,
and serialization components.
