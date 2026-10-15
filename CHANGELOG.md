# Changelog

## 2026-10-10

### Added
- `findMissingChunksInStore` logs the time of each array: `check_array start <path>` and
  `check_array end <path> seconds=... bytes=... chunks=... rate_gbps=...` (bytes of the chunks
  read in this session), and prints a `checked in ... s` line per array.
- `findMissingChunksInStore(..., checkpointSignal=None)`: with a signal, e.g. `signal.SIGUSR1`
  sent by SLURM before the time limit, the chunks checked so far in the unfinished arrays are
  saved to `<store>.check.partial`; a later session reads only their remaining chunks. The
  `.check` report is unchanged, and the partial file is removed when all arrays are checked.

### Changed
- zarr 3.4.1 or newer is required (`uv.lock`: 3.4.1, was 3.1.5). With it, a zero-size shard is
  reported as corrupt as well as zero-size, like a zero-size chunk; older versions read an empty
  shard as not written.

## 2026-10-04

### Added
- The diagnoser accepts a group of a store as input, e.g. `d3hp003.zarr/P1D_mean_atm`.
- The `.diag` file is nested by group, like the `.check` report, with the totals of each group
  under `"__total__"`; the members of the subgroups in the `.dist` file are nested the same way and
  keep their order. New helpers `nestDiagReport`, `flattenDiagReport`, `nestDistReport` and
  `flattenDistReport` in `zarrcurator.storetree`. Older flat files are still read.

### Changed
- A store with nested groups that is larger than the target size is split group by group, so a
  tarball holds the arrays of one group only, e.g. one HEALPix zoom level. Subgroups and tarballs
  are named by the group, e.g. `P1D_mean_atm_zoom_11_3.tar`. Stores without nested groups are split
  and named as before.
- The number of threads for the chunks of an array scales with their number (`numThreadsForChunks`)
  and is capped by the CPUs available to the process (e.g. a SLURM allocation): 4 threads per CPU
  for I/O-bound work, one per CPU for the CPU-bound corruption check; `ZARRCURATOR_MAX_THREADS`
  overrides the cap. This applies in `findMissingChunksInStore` and in the diagnoser, which now
  lists all files of an array first and sizes them in parallel, also for chunks in sub
  directories (`/` separator).
- `displayStoreSunburst` shows the group hierarchy of a store.

- `findMissingChunksInStore` checks several arrays at once when `ZARRCURATOR_MULTITHREAD=1`
  (8 by default, `ZARRCURATOR_ARRAY_WORKERS`), with thread pools shared by all arrays; the
  report keeps the order of the store, and an interrupted check keeps the finished arrays.
- `diagnoseStore` keeps the entries diagnosed so far in `<store>.diag.checkpoint` and continues
  from it in a later session, with the same result as a single session; the `.diag` is written
  atomically and the checkpoint removed when it is complete.
- The dispatcher skips tarballs that already exist completely in the working directory, so the
  tarballs of a store can be created in several sessions. Tarballs are written as `<name>.tar.part`
  and renamed when complete; an existing incomplete tarball is created again.

### Fixed
- The distributor no longer fails for stores whose name does not contain a frequency
  (`<experiment>_<frequency>_...`); their frequency is `ALL`, as for object stores.
- The diagnoser keeps absolute paths of local stores, and no longer raises `KeyError` for zero-size
  files in `diagnoseStore`.

### Removed
- `dispatch(freq, zoomLevel, subGroupID)` and `Dispatcher.createTarForFrequencyHealPixLevelSubGroup`,
  which were unused and failed for split stores; use `dispatchStoreToTarStores`.
- Unused diagnoser methods `findMissingChunksInZarr`, `findChunkSize`, `get_dir_size` and `find_size`.

## 2026-10-01

### Changed
- `findMissingChunksInStore` rewrites the `.check` report (as one valid JSON object) after each
  array and, if the report already exists, skips the arrays it lists, so the check of a large
  store can be resumed in a later session. Reports written in the older appended format are read.
- The `.check` report is nested by group instead of keyed by array path; each array entry has
  `"type": "array"` and its `path`. New helpers `nestCheckReport` and `flattenCheckReport` convert
  between the two layouts. Older flat reports are still read when resuming.

## 2026-09-30

### Added
- Stores with nested groups (e.g. written with `xarray.DataTree.to_zarr`): the diagnoser records
  arrays by their path (e.g. `atmos/ocean/salinity`), `findMissingChunksInStore` checks all arrays,
  groups that fit the target size are kept in one tarball, coordinates are looked up in the parent
  groups, and tarballs contain the metadata of all enclosing groups so they open with
  `xarray.open_datatree`. New module `zarrcurator.storetree`.
- zarr v3 stores in the Kerchunk step: their metadata is translated to zarr v2 and the chunks are
  referenced unchanged (new module `zarrcurator.zarrmetadata`).
- Sharded zarr v3 arrays in the Kerchunk step: the shard indexes are read (checksum verified) and
  each inner chunk is referenced.
- `checkStoreOpensWithXarray`: `dispatchStoreToTarStores` now fails with a `ValueError` before any
  diagnosis or tarball if xarray cannot open the store (e.g. arrays without dimension names).
- `mergeKerchunkReferences`: merges the references of the tarballs of a store.
- `zarrcurator.synthetic_store`: `--shards` and `--layouts flat,tree` options; all arrays carry
  dimension names; the manifest records `shards`, `layout` and `anomaly_array`.
- Documentation pages [Store Layouts](docs/store_layouts.md) and
  [Known Issues and Limitations](docs/known_issues.md).

### Changed
- The Kerchunk step merges the references of all tarballs of a store instead of combining them with
  `MultiZarrToZarr` along `time`; references of different stores are no longer combined.
- `dispatchStoreToTarStores` no longer opens the dataset to infer a zoom level and frequency it did
  not use.
- The test fixture `tests/data/synthetic_experiment` was regenerated with all store variants
  (one store per variant and frequency).

### Fixed
- Time-invariant variables (e.g. `orog(cell)`) were concatenated along `time` in the parquet
  references and read back as `(time, cell)` with only the first row filled.
- Chunks not written (holding only the fill value) read back as `[nan]` references from the parquet
  references of most arrays; the references are now written without pandas categoricals.
- Arrays of nested groups larger than the target size were skipped without being archived.
- The Kerchunk key rewrite broke keys of arrays in nested groups (e.g. `z1/cell/.zarray`).
- Stores xarray cannot open failed only at the end of `dispatchStoreToTarStores`, after diagnosis
  and distribution, with a `KeyError`.

### Testing
- `python -m pytest` prints a summary table of the results per test class, with tests and subtests
  and what each class covers (`tests/conftest.py`); options `--summary-table-file` and
  `--no-summary-table`. All test classes have a docstring for it.
- `zarrcurator.synthetic_store` gained a `--separators` option (`separators=` in
  `create_synthetic_experiment`) to generate zarr v2 and v3 stores with both `.` and `/`
  chunk key separators. Non-default layouts are named `..._z2slash.zarr` / `..._z3dot.zarr`.
- Synthetic `manifest.json` now stores paths relative to its directory and records each
  store's `separator`, so the committed fixture works from any checkout.
- Added `test_synthetic_store_layouts_report_injected_anomalies`, checking that
  `findMissingChunksInStore` reports the injected anomalies for all four layouts.

### Tooling
- `logs/` is now git-ignored.

## 2026-07-15

### Repository Reorganization
- Consolidated test scripts under top-level `tests` directory.
- Updated test module execution paths from package-internal locations to `tests.*`.
- Added pytest discovery configuration with `testpaths = ["tests"]`.

### Reliability and Quality
- Added broad unit/regression coverage for core package modules.
- Fixed multiple runtime issues around storage detection, constructor mismatches, and path handling.

### Observability
- Introduced structured logging across key modules (`config`, `diagnoser`, `dispatcher`, `distributor`, `utils`).
- Added CLI/environment-based logging level configuration.

### Performance
- Reduced memory overhead in dispatcher object-store tar creation by preferring streamed writes.
- Avoided unnecessary list materialization in selected diagnoser thread-map paths.

### Tooling
- Added `zarrcurator.benchmark` micro-benchmark harness for elapsed-time and peak-memory measurement.

### Packaging and Release
- Hardened package metadata for publishing (description, classifiers, keywords, URLs).
- Added optional dependency groups for `dev` and `docs` installs.
- Switched to single-source versioning (`pyproject.toml`) with runtime version derived from package metadata.
- Added release helper script `scripts/release.py` for version bump and optional tag creation.
- Added release checklist and process guide in `RELEASE.md`.
- Added GitHub Actions Trusted Publishing workflow at `.github/workflows/publish-pypi.yml`.
- Added version consistency CI workflow at `.github/workflows/version-consistency.yml`.
