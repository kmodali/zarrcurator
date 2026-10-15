# Overview

zarrcurator analyzes Zarr stores for completeness and sizing, supports visualization,
and can package selected content into tar archives for downstream archival workflows.

## Build Documentation

From the repository root:

```bash
sphinx-build -b html docs docs/_build/html
sphinx-build -b pdf docs docs/_build/pdf
```

Generated artifacts:

- HTML index: docs/_build/html/index.html
- PDF: docs/_build/pdf/zarrcurator.pdf

## Regenerate API Docstring Page

```bash
python scripts/generate_api_docstrings.py
```

## Object Store Credentials

zarrcurator supports anonymous-first access for supported S3 endpoints.
If a store is private, you can set credentials explicitly via utility APIs.

Preferred helper:

```python
import zarrcurator

zarrcurator.setObjectStoreCredentials(
	accessKey="AWS_ACCESS_KEY_ID",  # or literal access key value
	secretKey="AWS_SECRET_ACCESS_KEY",  # or literal secret value
)
```

Per-call credentials are also accepted by store-facing utilities such as:

- diagnoseStore(..., accessKey=..., secretKey=...)
- findMissingChunksInStore(..., accessKey=..., secretKey=...)
- displayStoreSunburst(..., accessKey=..., secretKey=...)

The generated `.check` report from `findMissingChunksInStore` includes per-variable
`missing`, `zero_size`, `corrupt`, and `unexpected` chunk lists, nested by group (see
[Store Layouts](store_layouts.md); `flattenCheckReport` gives it keyed by array path). It is rewritten after
each array. If the report already exists when `findMissingChunksInStore` starts, the
arrays it lists (with unchanged shape, chunks and shards) are skipped, so the check of
a large store can be split over several sessions. Delete the report to check all
arrays again.

An array is written to the report only when it is finished. For arrays that take long
(e.g. 2 TiB arrays of `zoom_11`), pass `checkpointSignal`, e.g.
`findMissingChunksInStore(store, checkpointSignal=signal.SIGUSR1)`: when that signal
arrives, the chunks checked so far in the unfinished arrays (and the corrupt chunks
among them) are saved to `<store>.check.partial`, and a later session reads only the
remaining chunks of those arrays (if their shape, chunks and shards are unchanged).
The signal handler is installed only when the function runs in the main thread, and the
previous handler is restored at the end. The partial file is removed when all arrays are
checked. The progress is saved only when the signal arrives: an array interrupted
without it is checked again from its start.

Each array is timed: the log has `check_array start <path>` and
`check_array end <path> seconds=... bytes=... chunks=... rate_gbps=...` lines, and the
output a `checked in ... s: ... bytes ..., ... GB/s` line. The bytes are those of the
chunks read in this session.

Chunk keys are recognised for zarr v2 (`0.1`, `0/1`) and zarr v3 (`c/0/1`, `c.0.1`,
and the v2-style encoding without the `c` prefix). In the report, `zero_size` and
`corrupt` list the chunk keys as found in the store, while `missing` lists
dot-separated chunk coordinates (e.g. `0.0.1`) regardless of layout. A zero-size
chunk cannot be read, so it is also listed under `corrupt`. All arrays are checked,
including those in nested groups; sharded arrays are checked by shard. See
[Store Layouts](store_layouts.md) for zarr v2/v3, nested groups (DataTree) and sharding,
and [Known Issues and Limitations](known_issues.md).

## Synthetic Test Stores

`python -m zarrcurator.synthetic_store` creates small stores with injected anomalies
for end-to-end checks:

- `--zarr-formats 2,3` selects the formats and `--separators .,/` the chunk key
  separators; without `--separators` each format uses its default (v2 `.`, v3 `/`).
- `--shards 4,4,8` also creates the zarr v3 stores with sharded data variables; the
  shard shape must be a multiple of the chunk shape `2,4,4`.
- `--layouts flat,tree` also creates stores with nested groups: `time` in the root
  group, `lat`, `lon`, `temp` and `humidity` in `/atmos`, and `salinity` in
  `/atmos/ocean`, which uses the coordinates of the groups above it.

The variant is tagged in the store name, only where it differs from the default, e.g.
`syntheticexp_P1D_000_z2slash.zarr` or `syntheticexp_P1D_000_z3shardtree.zarr`. The
`manifest.json` written next to the stores records each store's variant, the array the
anomalies are injected into (`temp`, or `atmos/ocean/salinity` in a tree) and the
anomalies, with paths relative to its own directory.

## Creating Tarballs

`dispatchStoreToTarStores(...)` supports both local-disk and object-store Zarr
backends. It first checks that the store opens with xarray (`xarray.open_datatree`)
and raises a `ValueError` otherwise, before any diagnosis or tarball is made.

The distributor splits a store larger than the target size into subgroups, one tarball each.
A store with nested groups (e.g. HEALPix zoom levels `multiscales/zoom_0` … `zoom_11`) is split
group by group, so a tarball never mixes zoom levels; the tarballs are named after the group,
e.g. `P1D_mean_atm_zoom_11_3.tar`. Every tarball carries the metadata of the whole store and
the data of its subgroup. See [Store Layouts](store_layouts.md) for the details.

## Large Stores and Several Sessions

The steps that read a whole store can be interrupted and continued in a later session, by
calling them again in the same working directory. For `findMissingChunksInStore`, the `.check`
report serves as checkpoint, and with `checkpointSignal` the `.check.partial` file keeps the
progress inside unfinished arrays (see above).

`diagnoseStore(...)` keeps the entries it has diagnosed so far in
`<store>.diag.checkpoint` in the working directory (written every 30 seconds and when the
diagnosis stops on an error). If a session is interrupted, call `diagnoseStore(...)` again in
the same working directory: it continues with the remaining entries, and the result is the
same as from a single session. The `.diag` is written under a temporary name and renamed, and
the checkpoint is removed once the `.diag` is complete. Delete the checkpoint to diagnose the
store from the start.

Tarballs that already exist completely in the working directory are skipped, so the
tarballs of a large store can be created in several sessions: run
`dispatchStoreToTarStores(...)` again in the same working directory and it continues with
the missing ones (for a variable split into chunk tarballs, with the missing bins). Each
tarball is written as `<name>.tar.part` and renamed to `<name>.tar` when complete, so an
interrupted session leaves no incomplete tarball behind; an existing tarball is also checked
(readable headers, member data within the file, end-of-archive blocks) and created again if
it is incomplete. Set `Dispatcher.skipExistingTars = False` to create all tarballs again.

## Multithreading

Diagnosis and missing-chunk detection run single-threaded by default; set
`ZARRCURATOR_MULTITHREAD=1` to run them with several threads:

- `diagnose` / `diagnoseStore` diagnose the stores of an experiment and the variables of a
  store in parallel (up to 10 threads each), and gather the sizes of the files of each variable
  in parallel on local stores (on object stores the listing already holds the sizes).
- `findMissingChunksInStore` checks several arrays at once (`arrayWorkers`: 8 by default, at
  most the number of available CPUs, or `ZARRCURATOR_ARRAY_WORKERS`), and queries their chunk
  sizes and checks their chunks for corruption in two thread pools shared by all arrays. The
  report is written after each array, in the order of the store; an interrupted check keeps
  the arrays finished so far.

The number of threads for the chunks of an array scales with their number
(`numThreadsForChunks`): 1, 10, 40 or 100 threads for fewer than 200, 200–499, 500–999, or
1000 and more chunks (for `findMissingChunksInStore`, the number of chunks of an array in
progress at once). The threads are capped by the CPUs available to the process
(`availableCpus`; within a SLURM job, the CPUs allocated to it); for
`findMissingChunksInStore` the caps are the sizes of its two shared pools:

| Work | Examples | Maximum threads |
|---|---|---|
| I/O-bound | listing files, querying chunk sizes | 4 per available CPU |
| CPU-bound | reading and decompressing chunks (corruption check) | 1 per available CPU |

For example, with 8 CPUs an array with 1000 chunks or more uses 32 threads for the size
queries and 8 for the corruption check. Set `ZARRCURATOR_MAX_THREADS` to a positive integer
to set the maximum for all work instead:

```bash
export ZARRCURATOR_MULTITHREAD=1
export ZARRCURATOR_MAX_THREADS=16
export ZARRCURATOR_ARRAY_WORKERS=8
```

The corruption check holds one decompressed chunk (or shard) per thread, so its memory grows
with the number of CPU threads, e.g. 256 threads × 192 MiB shards of `zoom_11` ≈ 50 GB plus
the compressed data.

## Running a Large Check as a SLURM Job

`findMissingChunksInStore` reads and decompresses every chunk of a store, so for a large store
it is best run as a batch job on one whole node. It runs in one process with threads, so more
nodes are not used; checking several arrays at once uses the CPUs of the node. Recommended
settings, e.g. on the `compute` partition of Levante (256 CPUs, about 240 GB, at most 8 hours):

```bash
#!/bin/bash
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=256   # whole node; threads are capped by CPUs
#SBATCH --mem=0               # all memory of the node
#SBATCH --time=08:00:00
#SBATCH --signal=B:USR1@600   # warning 10 min before the time limit

export ZARRCURATOR_MULTITHREAD=1   # several arrays at once
export OMP_NUM_THREADS=1           # one chunk per zarrcurator thread

# Near the time limit: save the progress of the unfinished
# arrays and submit a job that continues from the report
near_limit() {
    kill -USR1 "$PID"
    sbatch --dependency=afterany:$SLURM_JOB_ID "$0"
}
trap near_limit USR1
python check_store.py &            # calls findMissingChunksInStore
PID=$!
wait $PID
while kill -0 $PID 2>/dev/null; do wait $PID; done
```

where `check_store.py` ignores `USR1` outside the check (by default the signal ends
Python) and calls the check with the signal:

```python
import signal
import zarrcurator

signal.signal(signal.SIGUSR1, signal.SIG_IGN)
zarrcurator.findMissingChunksInStore(
    "/path/to/store.zarr", checkpointSignal=signal.SIGUSR1)
```

- Use a Python environment with this version of zarrcurator, e.g. the project `.venv`.
- The report `<store>.check` is written to the working directory after each array; a job that
  finds it skips the arrays it lists, so a check longer than the time limit continues in a
  follow-up job (limit the number of follow-up jobs in a real job script). Running the check in
  the background and waiting lets the job script handle the warning signal and pass it on, so
  the follow-up job also continues inside the arrays that were unfinished.
- Memory: the corruption check holds about one decompressed and one compressed chunk (or shard)
  per CPU thread; lower `ZARRCURATOR_MAX_THREADS` for stores with very large chunks.
- The job output and the log files show each array as it is checked, with its time, bytes and
  rate (`check_array end` lines).
- Measured on Levante (2026-10, `P1D_mean_atm`, 23.8 TiB, shards of up to ~180 MB): about
  0.7 GB/s on one node, i.e. about 15 TiB per 8 h job, with the node's CPUs mostly idle. The
  check is limited by the file system, so more threads do not make it faster; plan about one
  8 h job per 15 TiB.

