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
libraries are required or were installed. Phase 4 statistical analysis uses
Python's standard-library `statistics` module, so it does not add NumPy, SciPy,
pandas, or another runtime dependency. Phase 5 persistence likewise uses only
standard-library UUID, JSON, temporary-file, and filesystem support.

The optional [desktop console](#desktop-console) is the only part of the
project that needs GUI dependencies (`PySide6` and `pyqtgraph`). Every
library, CLI, and example path continues to work without them.

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
`sampling_slot_missed`. No late catch-up request is issued, and a missed slot is
never retried; [per-slot retries](#per-slot-retries) only re-issue a request
inside a slot that is still live. A request
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
its reporting are implemented separately by the Phase 4 APIs below.

## Statistical result analysis (Phase 4)

`analyze()` samples one configured ammeter and returns an immutable
`SamplingAnalysis`. The analysis retains the complete `SamplingResult` for
provenance and adds an optional immutable `CurrentStatistics` value:

```python
from src.testing.test_framework import AmmeterTestFramework

framework = AmmeterTestFramework()
analysis = framework.analyze(
    "greenlee",
    measurements_count=10,
    sampling_frequency_hz=5.0,
)

print(analysis.sampling_result.status.value)
if analysis.statistics is not None:
    print(analysis.statistics.measurements_count)
    print(analysis.statistics.mean_current)
    print(analysis.statistics.median_current)
    print(analysis.statistics.standard_deviation_current)
    print(analysis.statistics.minimum_current)
    print(analysis.statistics.maximum_current)
```

`analyze_all()` returns a `dict[str, SamplingAnalysis]` in configured ammeter
order. Both methods accept the same count, duration, and frequency arguments as
the Phase 3 sampling APIs and execute one new sampling window per selected
ammeter.

Only slots whose nested measurement status is `success` contribute a current
value. Failed and missed slots are excluded from the statistics, but they are
not discarded: the original sampling result, aggregate status, per-slot errors,
and timing remain attached to the analysis.

The reported metrics are:

| Field | Definition |
|---|---|
| `measurements_count` | Number of successful samples used |
| `mean_current` | Arithmetic mean |
| `median_current` | Middle value, or mean of the two middle values |
| `standard_deviation_current` | Population standard deviation |
| `minimum_current` | Smallest successful current |
| `maximum_current` | Largest successful current |
| `unit` | Amperes (`A`) |

Population standard deviation is intentional: the successful readings are
treated as the complete observed population for that sampling run, so the
calculation divides by `N`, not `N - 1`. The implementation uses Python's
standard-library `statistics` support and validates that every analyzed current
is finite.

Edge cases have explicit results:

- One successful sample produces identical mean, median, minimum, and maximum,
  with a population standard deviation of `0.0`.
- A run with no successful samples produces `statistics=None`; no fabricated
  zero or `NaN` metrics are returned.
- A partial sampling run still produces statistics when at least one slot
  succeeded. Its `partial` status and all excluded-slot or lifecycle errors
  remain visible in the attached `SamplingResult`.

`run_analysis()` and `run_all_analyses()` expose the same single/all operations
as JSON-friendly dictionaries. The serialized result includes ammeter identity,
status, timestamp, unit, analyzed/excluded/failed/missed counts, the metrics
(or `null` when there is no usable data), and the complete serialized sampling
result. It also labels the deviation method as `population`.

### Run the analysis example

From the project root:

```sh
python -m examples.run_analysis
```

The example samples every configured ammeter and prints an aligned table:

```text
Ammeter Statistical Analysis
+----------+---------+--------------+---------------+----------+------------+----------------+----------+----------+--------+
| Ammeter  | Status  | Used/Planned | Failed/Missed | Mean (A) | Median (A) | Pop StdDev (A) |  Min (A) |  Max (A) | Errors |
+----------+---------+--------------+---------------+----------+------------+----------------+----------+----------+--------+
| GREENLEE | SUCCESS |          5/5 |           0/0 | 0.420000 |   0.420000 |       0.014142 | 0.400000 | 0.440000 | -      |
+----------+---------+--------------+---------------+----------+------------+----------------+----------+----------+--------+
```

Actual values vary because the emulator inputs are random. `Used/Planned`
makes successful-sample filtering visible, while `Failed/Missed` and `Errors`
preserve the reason excluded samples were not analyzed.

### Phase 4 boundary

Phase 4 implements the required descriptive statistics and their reporting.
The visualization and performance-consistency items remain optional bonus work
and are deliberately deferred. Unique run identifiers, metadata archives,
historical retrieval, and result comparison belong to Phase 5 result management
and are not part of this phase.

## Per-slot retries

By default the framework issues exactly one request per sampling slot. A
configured retry policy lets a slot re-issue its request without weakening the
fixed-deadline schedule:

```yaml
testing:
  retry:
    max_attempts: 3
    retry_delay_seconds: 0.01
```

`max_attempts` counts the first request, so `1` (the default) means no retries.
Both values are bounded: at most 10 attempts per slot and a 60-second backoff.
A delay without more than one attempt is a configuration error rather than a
silently ignored value.

Per-call overrides work like the sampling overrides:

```python
analysis = framework.analyze(
    "greenlee",
    measurements_count=20,
    sampling_frequency_hz=10.0,
    max_attempts=3,
    retry_delay_seconds=0.01,
)
```

### Retries never move a deadline

Every attempt, including its backoff, has to finish inside the slot's own
half-open window `[i / F, (i + 1) / F)`. Before waiting, the policy checks
whether the backoff would land at or past the slot end; if it would, the slot
stops retrying instead of sleeping into the next deadline. A slot therefore
still produces exactly one result, and slot `i + 1` keeps its original target.

### What a retried slot records

- A slot that succeeds on any attempt is `SUCCESS` with no errors. Its
  `request_attempts` count is the evidence that retries were used.
- A slot that exhausts its attempts is `FAILED` and reports the **last**
  failure.
- A missed slot issues no request at all and records `request_attempts: 0`.
- `started_elapsed_seconds` is the first attempt's start and
  `request_latency_seconds` belongs to the final attempt.
- `SamplingResult` stores the policy it executed under, so an archived run
  distinguishes "retries were allowed but unnecessary" from "retries were never
  permitted".

Serialized sampling results gain a `retry` block, a per-sample
`request_attempts`, and a `summary.retried_samples` counter.

## Result management (Phase 5)

Phase 5 adds an append-only archive for completed `SamplingAnalysis` values.
The result-management API is exposed lazily through `framework.results`, so
constructing the framework or using any Phase 1 through Phase 4 method does not
touch the filesystem or require result-management configuration.

```python
from datetime import datetime, timezone

from src.testing.test_framework import AmmeterTestFramework

framework = AmmeterTestFramework()
analysis = framework.analyze("greenlee")

archived = framework.results.archive(
    analysis,
    metadata={
        "operator": "Nir",
        "board": "prototype-a",
        "ambient_temperature_c": 24.5,
    },
)

same_run = framework.results.get(archived.run_id)
recent_greenlee_runs = framework.results.find(
    ammeter_type="greenlee",
    archived_from_utc=datetime(2026, 8, 1, tzinfo=timezone.utc),
    has_statistics=True,
    limit=10,
)
```

`archive()` returns an immutable `ArchivedTestRun` containing a canonical UUID,
a timezone-aware UTC archive timestamp, deterministically ordered metadata, and
the complete analysis. Metadata values are restricted to JSON scalars: strings,
booleans, integers, finite floats, and `None`. The original sampling settings,
samples, timing, status, errors, and derived statistics therefore remain
attached to the archived run.

One run accepts at most 50 metadata entries. Keys must be trimmed strings no
longer than 64 characters, and string values are limited to 1,024 characters.

`archive_all()` archives a mapping of analyses in its existing order and
returns one independently identified archive per ammeter:

```python
analyses = framework.analyze_all()
archived_by_ammeter = framework.results.archive_all(
    analyses,
    metadata={"test_campaign": "power-board-regression"},
)
```

Each archive is a separate append-only operation; the method does not claim
batch-transaction semantics. A completed earlier write remains durable if a
later archive fails.

### Retrieval and filtering

`get(run_id)` validates a canonical UUID and retrieves exactly one typed run.
`find()` returns complete typed archives newest-first and supports these
optional filters:

- ammeter type;
- result status (`success`, `partial`, or `failed`);
- archive time range;
- exact metadata key/value matches;
- presence or absence of calculated statistics;
- result limit.

Archive time filtering uses the half-open range
`[archived_from_utc, archived_until_utc)`. All supplied metadata entries must
match, while an omitted filter leaves that property unrestricted. A missing
archive directory represents an empty history for `find()`; `get()` still
reports a typed not-found error for an absent run ID. A query limit is capped at
10,000 runs.

### Historical comparison

`compare()` accepts one baseline ID and one or more distinct candidate IDs:

```python
baseline_run = archived
candidate_run = framework.results.archive(
    framework.analyze("greenlee"),
    metadata={"board": "prototype-a", "iteration": 2},
)
comparison = framework.results.compare(
    baseline_run.run_id,
    (candidate_run.run_id,),
)
```

Every numeric delta is defined as:

```text
candidate value - baseline value
```

The comparison covers successful-measurement count, mean, median, population
standard deviation, minimum, and maximum. A candidate has
`statistics_delta=None` when it or the baseline has no usable statistics.
`same_ammeter_type` and `same_sampling_settings` are reported explicitly so a
caller can identify unlike runs.

This comparison is descriptive. It does not infer a true current, rank ammeter
accuracy, or declare one measurement method more reliable. Those decisions
belong to the separate accuracy-assessment bonus work.

Run the complete archive/list/compare example with:

```sh
python -m examples.run_result_management
```

It prints one aligned archive-history table and one baseline/candidate
comparison table. Running it creates two new append-only records in the
configured archive.

### Durable JSON archive

The default adapter stores one versioned UTF-8 JSON document per run, named
with its UUID. Documents include `schema_version: 1`, identity, archive time,
metadata, and the full serialized Phase 4 analysis. Writes use a temporary file
in the archive directory, flush it before installation, and publish with an
atomic no-overwrite filesystem operation. POSIX filesystems therefore need
same-directory hard-link support; Windows uses its atomic no-replace rename
semantics. An unsupported filesystem reports a typed storage error rather than
falling back to a clobber-prone write. Existing run IDs are never overwritten.
Temporary files are excluded from listing and cleaned up after failed writes.
Paths and publication use standard-library APIs rather than shell commands or
platform-specific path syntax.

One archive document is limited to 256 MiB. The limit is checked before
publication and again before decoding, bounding malformed or unexpectedly
large historical input.

Reads reconstruct the immutable domain models and recalculate derived analysis
fields. Unsupported schema versions, malformed JSON, unexpected fields, and
statistics that contradict the stored sampling result are reported as typed
result-management errors instead of being silently accepted. Recalculated
floating statistics allow only a small eight-ULP difference, which preserves
Python 3.9/newer runtime compatibility without accepting materially different
statistics.

`archived_test_run_to_dict()` and `historical_comparison_to_dict()` provide
JSON-friendly public representations when a caller does not need typed models.

Caller mistakes such as invalid IDs, metadata, filters, or comparison sets raise
typed validation errors. A missing run, ID collision, inaccessible archive,
corrupt document, or unsupported schema raises a distinct result-management
error. These failures are not converted into measurement statuses because they
occur outside the ammeter run itself.

### Phase 5 boundary

Phase 5 completes unique run identification, metadata archiving, durable local
storage, historical retrieval, and descriptive comparison. Visualization,
performance-consistency evaluation, and relative-accuracy or reliability
ranking remain optional bonus work.

## Desktop console

`src/presentation/desktop/` is an optional PySide6 front end for the same
public framework APIs. It is a presentation adapter: it drives
`AmmeterTestFramework` and `AmmeterResultManager` and adds no domain,
application, or infrastructure behaviour.

```sh
python -m pip install -r requirements.txt
python desktop_app.py
# or: python -m src.presentation.desktop --config config/config.yaml
```

### Pages

| Page | Purpose |
|---|---|
| Run | Select ammeters, resolve a sampling window and retry budget, watch samples stream in live, and archive each analysis |
| Results | Filter the archive, inspect statistics, samples, charts, and the raw archive document, and export JSON or CSV |
| Compare | Choose one baseline plus candidates and read candidate-minus-baseline deltas as a table and a chart |

Shortcuts: `Ctrl+1/2/3` navigate, `Ctrl+R` starts a run, `Esc` stops one,
`F5` reloads the archive, and `Ctrl+F` focuses the results filter.

### Live streaming and cancellation

`AmmeterTestFramework` already accepts its client, clock, and sleeper ports as
constructor arguments, so the desktop layer supplies decorated versions instead
of changing the framework:

- `LiveAmmeterClient` wraps `read_ammeter_current`, streams every request to the
  UI as it completes, and optionally injects communication failures, invalid
  readings, outliers, or extra latency at the transport boundary. Injected
  failures reach the framework as ordinary `MeasurementRequestError` or
  non-finite values, so the resulting statuses and statistics are produced by
  the real Phase 3/4 policies.
- `CancellableSleeper` slices scheduled waits and raises `RunCancelled` once a
  stop is requested. The sampling use case shuts its emulators down in a
  `finally` block, so a stopped run releases its sockets; the interrupted
  window is discarded rather than archived, and already-completed ammeters keep
  their analyses.

Sampling runs on a `QThread` worker, and streamed samples are batched before
crossing to the GUI thread so high frequencies stay responsive.

### Retries in the console

The Run page exposes attempts-per-slot and backoff, shows the slot window the
retries have to fit inside, and counts recovered slots live. Progress tracks
slots reached rather than requests issued, so a retried run still reports one
unit of progress per slot. The Results page adds an `Attempts` column, a
`RETRIED SLOTS` tile, and the archived policy in the statistics tab.

### Window derivation

The Run page collects the measurement count `N` and frequency `F` and lets the
existing application resolver derive `D = N / F`, so the desktop controls
cannot express a window that violates `N = D × F`.

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

The result archive is configured separately:

```yaml
result_management:
  archive_directory: "../results"
```

Archive documents are written at schema version 2, which adds the retry policy
and per-slot attempt counts. Version-1 archives written before retries existed
remain readable: they are re-encoded as version 1 when their canonical form is
verified, so no stored file has to be rewritten. A version-1 document that
contains retry fields is treated as corruption rather than silently upgraded.

Relative archive paths are resolved from the directory containing the selected
configuration file, not from the process working directory. The directory is
created only when the first archive save is requested. Missing or invalid
result-management configuration is resolved only when `framework.results` is
requested, leaving all earlier APIs usable with legacy configuration files.

## Project structure

- `main.py`: thin public entry point and CLI exception boundary
- `src/domain/models/`: immutable settings, measurement/sampling results,
  statistical analyses, archives, queries, and comparisons, one dataclass per
  module
- `src/application/ports/`: dependency contracts used by application logic
- `src/application/use_cases/`: selection, validation, measurement,
  fixed-deadline sampling, bounded retries, analysis, archival, retrieval,
  query, and comparison workflows
- `src/application/errors/`: typed selector, configuration, operational, and
  result-management errors
- `src/infrastructure/config/`: YAML loading and configuration resolution
- `src/infrastructure/emulators/`: registry and lifecycle adapters, one
  operation per module
- `src/infrastructure/clients/`: measurement transport adapters
- `src/infrastructure/time/`: UTC, monotonic clock, and sleep adapters
- `src/infrastructure/identifiers/`: canonical run-ID generation
- `src/infrastructure/persistence/`: append-only versioned JSON archive adapters
  and typed reconstruction
- `src/bootstrap/`: dependency composition
- `src/presentation/console/`: smoke-test, measurement, sampling, analysis,
  archive-history, and historical-comparison tables
- `src/presentation/serialization/`: JSON-friendly measurement, sampling, and
  analysis/archive/comparison serialization
- `src/presentation/desktop/`: optional PySide6 console (theme, formatters,
  view models, decorated ports, worker, charts, and pages)
- `desktop_app.py`: convenience entry point for the desktop console
- `Ammeters/`: existing emulator and socket infrastructure adapters
- `config/config.yaml`: runtime, sampling, and result-management configuration
- `src/testing/`: public `AmmeterTestFramework` facade and lazy result manager
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

## Phase 4 additions

- Added immutable current-statistics and sampling-analysis domain contracts.
- Added mean, median, population standard deviation, minimum, and maximum over
  successful samples only.
- Added explicit singleton, no-successful-data, and partial-run semantics.
- Added typed `analyze()`/`analyze_all()` and JSON-friendly
  `run_analysis()`/`run_all_analyses()` APIs.
- Added analysis serialization with full sampling provenance.
- Added an aligned statistical table and runnable module example.
- Used only Python's standard library for analysis; no external analysis
  dependency was added.
- Deferred visualization and performance-consistency bonus work, and kept
  archival/result management assigned to Phase 5.

## Phase 5 additions

- Added immutable archived-run, metadata, query, statistics-delta, and
  historical-comparison contracts.
- Added canonical UUID generation and complete versioned analysis provenance.
- Added append-only atomic JSON storage with typed corruption, schema,
  collision, and not-found errors.
- Added lazy `framework.results` access with archive, archive-all, get, find,
  and compare operations.
- Added deterministic newest-first filtering by ammeter, status, half-open UTC
  interval, metadata, statistics availability, and limit.
- Defined every historical metric delta as candidate minus baseline and kept
  accuracy/reliability ranking outside Phase 5.

## Run tests

```sh
python -m unittest discover -s tests -v
```
