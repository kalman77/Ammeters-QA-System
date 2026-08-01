# Ammeter Emulators

This project provides localhost emulators for Greenlee, ENTES, and CIRCUTOR
ammeters. Each emulator runs in its own thread and returns a simulated current
measurement through a small TCP protocol.

Commands and responses are newline-framed on the wire so TCP fragmentation
cannot produce partial measurements. The server also accepts the original exact
command bytes without a newline for compatibility with existing callers.

## Requirements

- Python 3.9 or newer
- PyYAML 6.0 or newer

Create a project-local environment and install the runtime dependency:

```sh
python -m venv .venv
```

Linux/macOS:

```sh
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Phase 1 was verified with Python 3.14.6 and PyYAML 6.0.3. No other external
libraries are required or were installed.

## Run the emulator smoke test

From the project directory:

```sh
python main.py
```

`main.py` reads the host, ports, commands, and timeouts from
`config/config.yaml`. It starts all three servers, waits until their listening
sockets are ready, requests one current measurement from each, prints the
results, and stops every server thread.

Results are displayed in an aligned console table:

```text
Ammeter Measurement Results
+----------+-----------+------+
| Ammeter  |   Current | Unit |
+----------+-----------+------+
| GREENLEE |  0.420000 | A    |
| ENTES    | 72.500000 | A    |
| CIRCUTOR |  0.030000 | A    |
+----------+-----------+------+
```

The callable `main.main()` also returns the measurements as:

```python
{
    "greenlee": 0.42,
    "entes": 72.5,
    "circutor": 0.03,
}
```

Values change on every run because the emulator inputs are random.

## Unified test framework (Phase 2)

`AmmeterTestFramework` is the public API for measuring one configured ammeter.
The canonical `measure()` method returns an immutable `MeasurementResult`:

```python
from src.testing.test_framework import AmmeterTestFramework

framework = AmmeterTestFramework()
result = framework.measure("greenlee")

print(result.ammeter_type)             # greenlee
print(result.status.value)             # success, failed, or partial
print(result.current, result.unit)     # for example: 0.42 A
print(result.request_latency_seconds)
print(result.errors)
```

Ammeter names are stripped and matched case-insensitively. The supported names
are available through `framework.ammeter_types`. Use `measure_all()` to receive
a `dict[str, MeasurementResult]` in configured execution order.

`run_test()` preserves a dictionary-oriented API. It executes the same typed
measurement and serializes the result into JSON-friendly values:

```python
result = framework.run_test("greenlee")
```

```python
{
    "ammeter_type": "greenlee",
    "status": "success",
    "timestamp_utc": "2026-08-01T09:30:00Z",
    "elapsed_seconds": 0.012,
    "current": 0.42,
    "unit": "A",
    "request_latency_seconds": 0.004,
    "errors": [],
}
```

`run_all_tests()` returns the same serialized shape for every configured
ammeter.

### Status and error semantics

| Status | Measurement fields | Errors |
|---|---|---|
| `success` | `current` and request latency are present | Empty |
| `failed` | `current` and request latency are `None` | One or more operational errors |
| `partial` | A valid measurement is present | A later shutdown error is recorded |

Operational failures are returned in `errors` with stable codes:
`emulator_start_failed`, `measurement_request_failed`,
`invalid_measurement`, and `emulator_stop_failed`. Invalid selectors and
configuration are caller errors rather than measurement outcomes:

- `FrameworkConfigurationError` means the YAML could not be loaded or resolved.
- `InvalidAmmeterTypeError` means the selector was not a non-empty string.
- `UnsupportedAmmeterError` means the normalized name is not configured.

### Run the example

From the project root, invoke the example as a module so project imports resolve
consistently:

```sh
python -m examples.run_tests
```

The example calls `measure_all()` and prints the typed results, including status,
latency, and structured error details.

### Phase 2 boundary

The Phase 2 methods perform exactly one measurement request for each selected
ammeter. They remain available unchanged alongside the Phase 3 sampling API.

## Precise sampling (Phase 3)

`sample()` runs a fixed sampling window for one ammeter and returns an immutable
`SamplingResult`. `sample_all()` applies the same resolved schedule to every
configured ammeter:

```python
framework = AmmeterTestFramework()

result = framework.sample("greenlee")
results_by_ammeter = framework.sample_all()
```

Sampling uses `measurements_count` (`N`), `total_duration_seconds` (`D`), and
`sampling_frequency_hz` (`F`). Configure any two values and the framework
derives the third. If all three are supplied, they must satisfy:

```text
N = D * F
```

The schedule is a half-open window `[0, D)`. Sample `i` targets `i / F`, so the
default `N=5`, `D=1.0`, `F=5.0` configuration targets `0.0`, `0.2`, `0.4`,
`0.6`, and `0.8` seconds. When `D` and `F` derive `N`, their product must be a
whole number.

Sampling settings are read lazily. Constructing the framework and using the
Phase 2 APIs does not require a sampling section. The
`framework.sampling_settings` property resolves the YAML values on demand.

Callers may override the YAML values for one call:

```python
result = framework.sample(
    "greenlee",
    measurements_count=10,
    sampling_frequency_hz=5.0,
)
```

Providing any override selects explicit-override mode; override values are not
merged with YAML. Supply at least two explicit values, and the third is derived.
Invalid, incomplete, non-positive, non-finite, fractional-count, or inconsistent
settings raise `SamplingConfigurationError`.

To prevent accidental unbounded runs, one sampling call is limited to 100,000
slots, 24 hours, and 10,000 Hz. Values beyond those limits are rejected before
an emulator starts.

`run_sampling_test()` returns one JSON-friendly sampling dictionary.
`run_all_sampling_tests()` returns serialized sampling results for every
ammeter. Each dictionary includes the resolved settings, successful/failed/missed
counts, per-slot scheduled and actual timing, timing error, nested measurement
results, and lifecycle errors.

### Fixed deadlines and missed slots

Every target is anchored to one monotonic start time, so request latency does not
accumulate as schedule drift. Each slot occupies
`[i / F, (i + 1) / F)`.

If an earlier request is slow and a later slot is at or beyond its end before
it can start, that slot is recorded as a failed sample with
`sampling_slot_missed`. No late catch-up request or retry is issued. A request
that starts inside its slot still owns that slot even if it completes late.
Consequently, every started run contains exactly `N` slot results while its
duration remains bounded by the configured window plus completion of at most the
final in-flight request and shutdown.

Sampling status follows the existing result vocabulary:

| Status | Meaning |
|---|---|
| `success` | Every slot contains a valid measurement and no lifecycle error occurred |
| `partial` | At least one slot succeeded and at least one slot or lifecycle operation failed |
| `failed` | No usable measurement was collected |

### Run the sampling example

From the project root:

```sh
python -m examples.run_sampling
```

The example samples every configured ammeter and prints a summary containing
good/total slots, missed slots, configured and actual window duration, frequency,
maximum observed drift, and error codes.

### Phase 3 boundary

Phase 3 records raw measurements and timing/error metadata but does not calculate
mean, median, standard deviation, minimum, or maximum. Statistical analysis and
its reporting are deferred explicitly to Phase 4.

## Configured protocols

`config/config.yaml` is the runtime source of truth.

| Ammeter | Default port | Command |
|---|---:|---|
| Greenlee | 5000 | `MEASURE_GREENLEE -get_measurement` |
| ENTES | 5001 | `MEASURE_ENTES -get_data` |
| CIRCUTOR | 5002 | `MEASURE_CIRCUTOR -get_measurement -current` |

The same configuration file defines connection, read, startup, and shutdown
timeouts. Port `0` may be used in test configurations to let the operating
system choose a free port.

It also defines the default sampling window:

```yaml
testing:
  sampling:
    measurements_count: 5
    total_duration_seconds: 1.0
    sampling_frequency_hz: 5.0
```

Any two sampling values are sufficient; setting the derived value to `NULL` is
valid.

## Project structure

- `main.py`: thin public entry point and CLI exception boundary
- `src/domain/models/`: immutable settings, measurement results, and sampling
  results, one dataclass per module
- `src/application/ports/`: dependency contracts used by application logic
- `src/application/use_cases/`: selection, validation, measurement, and
  fixed-deadline sampling workflows
- `src/application/errors/`: typed selector, configuration, and operational
  errors
- `src/infrastructure/config/`: YAML loading and configuration resolution
- `src/infrastructure/emulators/`: registry and lifecycle adapters, one
  operation per module
- `src/infrastructure/clients/`: measurement transport adapters
- `src/infrastructure/time/`: UTC, monotonic clock, and sleep adapters
- `src/bootstrap/`: dependency composition
- `src/presentation/console/`: smoke-test, typed-result, and sampling tables
- `src/presentation/serialization/`: JSON-friendly result serialization
- `Ammeters/`: existing emulator and socket infrastructure adapters
- `config/config.yaml`: runtime and sampling configuration
- `src/testing/`: public `AmmeterTestFramework` facade
- `examples/`: framework usage examples
- `tests/`: behavioral and architecture regression tests

See [Architecture](docs/architecture.md) for dependency direction and design
decisions.

## Phase 1 fixes

- Activated the previously empty ammeter configuration.
- Aligned the runtime ports with the documented `5000`, `5001`, and `5002`
  assignments.
- Corrected the documented CIRCUTOR command to include the emulator's required
  `-current` suffix.
- Changed the client to return a validated finite `float` instead of only
  printing socket data.
- Added bounded connection/read timeouts and clear invalid-response errors.
- Added complete-frame reads so fragmented TCP commands or values cannot be
  mistaken for complete messages.
- Replaced the fixed startup delay with a listener-readiness signal.
- Added cooperative server shutdown, bounded thread joins, ephemeral-port
  support, and socket-address reuse for reliable repeated runs.
- Corrected the incomplete framework module's missing type import and the
  example's original `run_test` call signature.
- Refactored the Phase 1 implementation into domain, application,
  infrastructure, bootstrap, and presentation layers. `main.py` now delegates
  to the bootstrap layer instead of owning configuration and thread lifecycle.

## Phase 2 additions

- Added a unified, typed single-ammeter measurement API.
- Added immutable measurements, result envelopes, statuses, and structured
  error details.
- Added JSON-friendly `run_test()` and `run_all_tests()` compatibility APIs.
- Added validated selector handling, UTC timestamps, elapsed time, and request
  latency.
- Added typed-result console presentation and a runnable module example.
- Kept sampling mechanics deferred to Phase 3.

## Phase 3 additions

- Added configuration-driven and per-call sampling with two-of-three value
  derivation.
- Added immutable per-slot and aggregate sampling results.
- Added drift-resistant monotonic scheduling and explicit missed-slot reporting.
- Added typed and JSON-friendly single/all sampling APIs.
- Added a sampling summary table and runnable module example.
- Kept statistical analysis deferred to Phase 4.

## Run tests

```sh
python -m unittest discover -s tests -v
```
