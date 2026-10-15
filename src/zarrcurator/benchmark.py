"""Micro-benchmark harness for zarrcurator.

Run examples:
  python -m zarrcurator.benchmark --synthetic
  python -m zarrcurator.benchmark --store-path /path/to/store.zarr --phase diagnose
  python -m zarrcurator.benchmark --synthetic --phase both --log-level INFO
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import tempfile
import time
import tracemalloc
from pathlib import Path

from .cli import configure_logging
from .config import configObj
from .diagnoser import Diagnoser
from .dispatcher import Dispatcher
from .subgroup import SubGroup


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def _bytes_to_mib(value: int) -> float:
    return value / (1024 * 1024)


def _run_with_metrics(func):
    tracemalloc.start()
    t0 = time.perf_counter()
    func()
    elapsed = time.perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "elapsed_secs": round(elapsed, 6),
        "peak_mem_mib": round(_bytes_to_mib(peak), 3),
    }


def _write_bytes(path: Path, size: int) -> None:
    path.write_bytes(b"0" * size)


def create_synthetic_store(
    root_dir: Path,
    variables: int,
    chunks_per_var: int,
    chunk_size_bytes: int,
) -> Path:
    """Create a lightweight local zarr-like directory tree for benchmarking I/O paths."""

    store = root_dir / "synthetic_P1D_0.zarr"
    store.mkdir(parents=True, exist_ok=True)
    (store / ".zattrs").write_text("{}", encoding="utf-8")
    (store / ".zgroup").write_text('{"zarr_format":2}', encoding="utf-8")

    for idx in range(variables):
        var_dir = store / f"var_{idx:03d}"
        var_dir.mkdir(parents=True, exist_ok=True)
        (var_dir / ".zarray").write_text('{"zarr_format":2,"shape":[1],"chunks":[1],"dtype":"|u1"}', encoding="utf-8")
        (var_dir / ".zattrs").write_text("{}", encoding="utf-8")

        for chunk_id in range(chunks_per_var):
            _write_bytes(var_dir / str(chunk_id), chunk_size_bytes)

    return store


class _BenchDistributor:
    def __init__(self, subgroup: SubGroup, target_size: int) -> None:
        self.frequencySubGroupDict = {"P1D": {"1": subgroup}}
        self.targetSize = target_size


def benchmark_diagnose(store_path: Path, work_dir: Path, json_name: str) -> dict:
    def _job():
        # Diagnoser currently normalizes local single-store paths with strip(os.path.sep),
        # so run from root to keep stripped absolute paths resolvable for benchmarks.
        prev_cwd = os.getcwd()
        try:
            os.chdir(os.path.sep)
            configObj.setZarrStorePath(str(store_path))
            configObj.setWorkingDir(str(work_dir))
            configObj.setJsonFile(json_name)
            diag = Diagnoser()
            diag.update()
        finally:
            os.chdir(prev_cwd)

    return _run_with_metrics(_job)


def benchmark_dispatch(store_path: Path, work_dir: Path, target_size: int) -> dict:
    def _job():
        configObj.setZarrStorePath(str(store_path))
        configObj.setWorkingDir(str(work_dir))
        subgroup = SubGroup([(str(store_path), 1)], "zarr", [], [])
        distributor = _BenchDistributor(subgroup, target_size)
        dispatcher = Dispatcher("bench", distributor)
        dispatcher.createTarForFrequencySubGroupDict()
        dispatcher.executor(-1)

    return _run_with_metrics(_job)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="zarrcurator micro-benchmark harness")
    parser.add_argument("--store-path", default=None, help="Path to an existing local .zarr store")
    parser.add_argument("--work-dir", default=None, help="Working directory for benchmark outputs")
    parser.add_argument("--json-file", default="benchmark.diag.json", help="Diagnosis output filename")
    parser.add_argument("--phase", choices=["diagnose", "dispatch", "both"], default="both")
    parser.add_argument("--target-size", type=int, default=200 * 1024 * 1024 * 1024)
    parser.add_argument("--synthetic", action="store_true", help="Generate and benchmark a synthetic store")
    parser.add_argument("--synthetic-variables", type=int, default=4)
    parser.add_argument("--synthetic-chunks", type=int, default=128)
    parser.add_argument("--synthetic-chunk-size", type=int, default=1024)
    parser.add_argument("--keep-data", action="store_true", help="Keep synthetic temp data after run")
    parser.add_argument("--log-level", default=None, help="Override logging level (or use ZARRCURATOR_LOG_LEVEL)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)

    cleanup_root = None

    if args.synthetic:
        cleanup_root = Path(tempfile.mkdtemp(prefix="zarrcurator_bench_"))
        store_path = create_synthetic_store(
            cleanup_root,
            variables=args.synthetic_variables,
            chunks_per_var=args.synthetic_chunks,
            chunk_size_bytes=args.synthetic_chunk_size,
        )
        work_dir = cleanup_root / "work"
        work_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Synthetic benchmark store created at %s", store_path)
    else:
        if not args.store_path:
            raise SystemExit("--store-path is required unless --synthetic is used")
        store_path = Path(args.store_path)
        if not store_path.exists():
            raise SystemExit(f"Store path does not exist: {store_path}")

        work_dir = Path(args.work_dir) if args.work_dir else Path(tempfile.mkdtemp(prefix="zarrcurator_bench_work_"))
        work_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "store_path": str(store_path),
        "work_dir": str(work_dir),
        "phase": args.phase,
    }

    if args.phase in {"diagnose", "both"}:
        results["diagnose"] = benchmark_diagnose(store_path, work_dir, args.json_file)

    if args.phase in {"dispatch", "both"}:
        results["dispatch"] = benchmark_dispatch(store_path, work_dir, args.target_size)

    print(json.dumps(results, indent=2))

    if cleanup_root and not args.keep_data:
        shutil.rmtree(cleanup_root, ignore_errors=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
