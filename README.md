# zarrcurator

zarrcurator analyzes Zarr stores for completeness and sizing, supports visualization, and can package selected content into tar archives for downstream archival workflows.

## Repository Layout

- `src/zarrcurator`: package source code
- `tests`: repository-level test suite

## Contributing

Contribution workflow, coding rules, testing expectations, and PR guidelines are documented in `CONTRIBUTING.md`.

## Installation

zarrcurator requires Python 3.12 or newer and zarr 3.4.1 or newer (the version in `uv.lock`).
Older zarr versions read a zero-size shard as not written, so the check did not report it as
corrupt.

Install from a local clone (recommended for development):

```bash
cd /path/to/zarrcurator
python -m pip install -e .
```

Install as a regular package from a local clone:

```bash
cd /path/to/zarrcurator
python -m pip install .
```

Build wheel/sdist and install the wheel:

```bash
cd /path/to/zarrcurator
python -m pip install build
python -m build
python -m pip install dist/*.whl
```

Optional: install development tooling used in this repository:

```bash
cd /path/to/zarrcurator
python -m pip install -e .[dev]
```

Optional: install documentation tooling:

```bash
cd /path/to/zarrcurator
python -m pip install -e .[docs]
```

## Development Commands

Run unit test suite:

```bash
python -m pytest
python -m tests.test_all_modules
python -m tests.regression_test
```

`python -m pytest` ends with a summary table of the results per test class (tests and
subtests passed, failed and skipped, and what each class covers, from its docstring).
`--summary-table-file=summary.md` also writes it to a file, `--no-summary-table` turns it off.

Run the store layout tests (zarr v2 and v3, `.` and `/` separators, nested groups, sharding):

```bash
python -m pytest tests/test_all_modules.py -k TestChunkKeySeparators
python -m pytest tests/test_all_modules.py -k TestDataTreeStores
python -m pytest tests/test_all_modules.py -k TestZarrV3Metadata
python -m pytest tests/test_all_modules.py -k TestSyntheticStoreVariants
python -m pytest tests/regression_test.py -k synthetic_store_layouts
```

Run focused config/object-store tests:

```bash
python -m unittest tests.test_all_modules.TestConfigAndSubgroup
```

Generate API documentation from source docstrings:

```bash
python scripts/generate_api_docstrings.py
```

Build Read the Docs style documentation (HTML and PDF):

```bash
python -m sphinx -b html docs docs/_build/html
python -m sphinx -b pdf docs docs/_build/pdf
```

## Releases

Repository release process and checklist are documented in `RELEASE.md`.

Bump package version (single-source in `pyproject.toml`):

```bash
python scripts/release.py --bump patch
```

Automated publishing is configured via GitHub Actions Trusted Publishing:

- `.github/workflows/publish-pypi.yml`
- tag push `v*` publishes to PyPI
- manual `workflow_dispatch` supports TestPyPI and PyPI targets

Version consistency CI is configured via:

- `.github/workflows/version-consistency.yml`

Run pre-commit quality checks (lint, type checks, spell checks, and hygiene checks):

```bash
python -m pip install pre-commit
pre-commit install
pre-commit run --all-files
```

Run benchmark harness:

```bash
python -m zarrcurator.benchmark --help
python -m zarrcurator.benchmark --synthetic --phase diagnose
python -m zarrcurator.benchmark --synthetic --phase both
```

Create a synthetic Zarr experiment to test diagnose/distribute/dispatch flows:

```bash
cd src
python -m zarrcurator.synthetic_store --output-dir ../tests/data/synthetic_experiment --clean --zarr-formats 2,3 --run-smoke
```

By default each format uses its own chunk key separator (v2 `0.1`, v3 `c/0/1`), no
sharding and a flat layout (all arrays in the root group). These options add variants:

- `--separators .,/`: both chunk key separators for each format.
- `--shards 4,4,8`: the zarr v3 stores also with sharded data variables (shard shape of
  `time,lat,lon`, a multiple of the chunk shape `2,4,4`).
- `--layouts flat,tree`: also stores with nested groups, as written from an xarray DataTree:
  `time` in the root group, `lat`, `lon`, `temp` and `humidity` in `/atmos`, and `salinity`
  in `/atmos/ocean`, which uses the coordinates of the groups above it.

All variants, as in the committed fixture:

```bash
python -m zarrcurator.synthetic_store --output-dir tests/data/synthetic_experiment --clean \
    --zarr-formats 2,3 --separators .,/ --shards 4,4,8 --layouts flat,tree --stores-per-frequency 1
```

The variant is tagged in the store name, only where it differs from the default:

| Format | Separator | Chunk key | Sharded | Layout | Store name |
| ------ | --------- | --------- | ------- | ------ | ---------- |
| v2 | `.` | `0.0.0` | no | flat | `syntheticexp_P1D_000_z2.zarr` |
| v2 | `/` | `0/0/0` | no | flat | `syntheticexp_P1D_000_z2slash.zarr` |
| v3 | `/` | `c/0/0/0` | no | flat | `syntheticexp_P1D_000_z3.zarr` |
| v3 | `.` | `c.0.0.0` | no | flat | `syntheticexp_P1D_000_z3dot.zarr` |
| v3 | `/` | `c/0/0/0` (shard) | yes | flat | `syntheticexp_P1D_000_z3shard.zarr` |
| v2 | `.` | `0.0.0` | no | tree | `syntheticexp_P1D_000_z2tree.zarr` |
| v3 | `.` | `c.0.0.0` (shard) | yes | tree | `syntheticexp_P1D_000_z3dotshardtree.zarr` |

All arrays carry dimension names, so the stores open with xarray. The generated
`manifest.json` records each store's `zarr_format`, `separator`, `shards`, `layout`, the
array the anomalies are injected into (`anomaly_array`: `temp`, or `atmos/ocean/salinity`
in a tree) and the anomalies (`zero_size`, `missing`, `corrupt`, `unexpected`). All paths in
it are relative to the manifest's directory, so the fixture works from any checkout.

## Store Layouts

zarr v2 and v3 stores with `.` or `/` chunk key separators, nested groups (e.g. written with
`xarray.DataTree.to_zarr`) and sharded arrays are supported, from diagnosis to the Kerchunk
references of the tarballs. A store must open with xarray (all arrays need dimension names);
`dispatchStoreToTarStores` checks this first and raises a `ValueError` otherwise. The Kerchunk
references of all tarballs of a store are merged into one parquet reference of the store, in
the zarr v2 layout; stores with nested groups are opened from it with `consolidated=True`.
Details and examples: [docs/store_layouts.md](docs/store_layouts.md).

## Large Stores and Several Sessions

The steps that read a whole store can be interrupted and continued in a later session, by
calling them again in the same working directory:

| Step | Kept in the working directory | Continued by |
|---|---|---|
| `diagnoseStore` | `<store>.diag.checkpoint`: the entries diagnosed so far (every 30 s) | diagnosing only the remaining entries; the `.diag` equals that of a single session, and the checkpoint is removed when the `.diag` is written |
| `findMissingChunksInStore` | `<store>.check`: rewritten after each array; with `checkpointSignal`, `<store>.check.partial`: the chunks checked so far in unfinished arrays, written when that signal arrives | skipping the arrays it lists (with unchanged shape, chunks and shards) and the chunks checked in partly checked arrays; the partial file is removed when all arrays are checked |
| `dispatchStoreToTarStores` | the tarballs; each is written as `<name>.tar.part` and renamed when complete | skipping the tarballs that exist completely (per bin for arrays split into chunk tarballs) |

To start a step from the beginning, delete its checkpoint, report or tarballs, or set
`Dispatcher.skipExistingTars = False`. Details, and recommended settings for running a large
check as a SLURM job on one whole node: [docs/overview.md](docs/overview.md).

## Known Issues and Limitations

See [docs/known_issues.md](docs/known_issues.md). In short:

- Target sizes below 1 GiB fail for arrays larger than the target size.
- A metadata file larger than the target size (e.g. the consolidated metadata of a large
  store with many groups) fails.
- Kerchunk references are zarr v2: zarr v3 codecs without a zarr v2 equivalent are rejected,
  and a single shard larger than the target size makes an oversized tarball.

## Object Store Access

For supported S3 endpoints, zarrcurator now uses this access order:

1. Try anonymous access first.
2. If anonymous access fails, try configured credentials.
3. If credentials are missing and anonymous access fails, exit with a clear error message.

You can provide credentials in three supported ways:

1. Use the new utility helper (recommended for notebooks/scripts).
2. Use config setters with environment-variable names.
3. Export environment variables directly.

Using the utility helper:

```python
import zarrcurator

# Accepts raw values OR env-var names containing the values.
zarrcurator.setObjectStoreCredentials(
	accessKey="AWS_ACCESS_KEY_ID",
	secretKey="AWS_SECRET_ACCESS_KEY",
)
```

You can also pass credentials directly on store-facing utility calls:

```python
from zarrcurator.utils import diagnoseStore, findMissingChunksInStore

diagnoseStore(
	"https://s3.eu-dkrz-3.dkrz.cloud/mybucket/my-store.zarr",
	accessKey="AWS_ACCESS_KEY_ID",
	secretKey="AWS_SECRET_ACCESS_KEY",
)

findMissingChunksInStore(
	"https://s3.eu-dkrz-3.dkrz.cloud/mybucket/my-store.zarr",
	accessKey="AKIA...",
	secretKey="...",
)
```

Using config setters:

```python
from zarrcurator.config import configObj

# Pass environment variable names.
configObj.setaccessKey("AWS_ACCESS_KEY_ID")
configObj.setsecretKey("AWS_SECRET_ACCESS_KEY")
```

Using environment variables:

```bash
export AWS_ACCESS_KEY_ID="<ACCESS_KEY>"
export AWS_SECRET_ACCESS_KEY="<SECRET_KEY>"
```

Alternative variable names are also recognized:

- `S3_ACCESS_KEY_ID`
- `S3_SECRET_ACCESS_KEY`

## Multithreading

Store diagnosis and missing-chunk detection run single-threaded by default. To enable multithreading, set:

```bash
export ZARRCURATOR_MULTITHREAD=1
```

When enabled, diagnosis (`diagnose`, `diagnoseStore`):

- diagnoses the Zarr stores of an experiment in parallel (up to 10 threads)
- diagnoses the variables within each store in parallel (up to 10 threads)
- lists all files of each variable, including chunks in sub directories (`/` separator), and
  gathers their sizes in parallel on local stores, with the thread count scaled by the number of
  files (1, 10, 40, or 100 threads for fewer than 200, 200–499, 500–999, or 1000 and more); on
  object stores the listing already holds the sizes

When enabled, missing-chunk detection (`findMissingChunksInStore`):

- checks several arrays at once (8 by default, at most the number of available CPUs; set
  `ZARRCURATOR_ARRAY_WORKERS` to change it), so that small arrays, e.g. of low zoom levels, do not
  run one after the other
- queries chunk sizes (zero-size detection) in parallel
- checks chunk readability (corruption detection) in parallel

The size queries and readability checks of all arrays share two thread pools; each array keeps
at most as many chunks in progress as the number of its chunks gives (1, 10, 40, or 100, see
`numThreadsForChunks`). The report is written after each array, in the order of the store.
The log has a `check_array start` and a `check_array end` line per array; the end line gives
the seconds, the bytes read, the number of chunks and the rate in GB/s, so the speed of a check
can be measured per array.

The thread counts are capped by the CPUs available to the process (within a SLURM job, the CPUs
allocated to it): I/O-bound work (listing files, querying sizes) uses at most 4 threads per
CPU, CPU-bound work (reading and decompressing chunks for the corruption check) at most one
thread per CPU; for `findMissingChunksInStore` these are the sizes of the two shared pools. For
example, with 8 CPUs at most 32 threads query sizes and 8 check chunks. Set
`ZARRCURATOR_MAX_THREADS` to a positive integer to set the maximum for all work instead:

```bash
export ZARRCURATOR_MAX_THREADS=16
```

Any value other than `1` (or leaving the variable unset) keeps single-threaded mode. The active mode is reported in the logs (`mode=single-thread` / `mode=multi-thread`).

From Python, set the variable before running a diagnosis:

```python
import os

os.environ["ZARRCURATOR_MULTITHREAD"] = "1"
```

## Logging

CLI logging level can be set via:

- argument: `--log-level DEBUG`
- environment variable: `ZARRCURATOR_LOG_LEVEL=DEBUG`

During CLI usage, logs are also written to a timestamped file:

- default directory: `logs/`
- filename pattern: `zarrcurator_YYYYMMDD_HHMMSS.log`

You can override the log directory with:

- environment variable: `ZARRCURATOR_LOG_DIR=/path/to/logs`

For notebook/library usage (non-CLI), enable the same logging with:

```python
import zarrcurator

zarrcurator.enable_logging("INFO")
```
>>>>>>> pvt/beta1_0
