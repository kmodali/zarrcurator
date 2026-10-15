"""Synthetic Zarr experiment generator for zarrcurator.

This module creates local Zarr stores with predictable naming and metadata so
core zarrcurator workflows can be tested end-to-end.

Examples:
  python -m zarrcurator.synthetic_store --output-dir tests/data/synthetic_experiment
  python -m zarrcurator.synthetic_store --output-dir tests/data/synthetic_experiment --run-smoke
  python -m zarrcurator.synthetic_store --output-dir /tmp/layouts --separators .,/
  python -m zarrcurator.synthetic_store --output-dir /tmp/all --separators .,/ --shards 4,4,8 --layouts flat,tree
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
from pathlib import Path

import numpy as np
import zarr

from .cli import configure_logging
from .config import configObj
from .diagnoser import Diagnoser
from .dispatcher import Dispatcher
from .distributor import Distributor


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# Chunk key separator zarr uses by default for each format: v2 '0.1', v3 'c/0/1'.
DEFAULT_SEPARATORS = {2: ".", 3: "/"}
SEPARATOR_NAMES = {".": "dot", "/": "slash"}
LAYOUTS = ("flat", "tree")


def _create_single_store(
    store_path: Path,
    frequency: str,
    zoom: int,
    seed: int,
    zarr_format: int,
    inject_anomalies: bool,
    separator: str | None = None,
    shards: tuple[int, ...] | None = None,
    layout: str = "flat",
) -> dict:
    """Create one Zarr store with dimensions and data variables.

    ``separator`` selects the chunk key separator ('.' or '/'); None uses the
    format default. v2 keys look like '0.1' / '0/1', v3 keys like 'c.0.1' / 'c/0/1'.
    ``shards`` gives the shard shape of the data variables (zarr v3 only), None for no sharding.
    ``layout`` is 'flat' (all arrays in the root group) or 'tree' (nested groups, as written from
    an xarray DataTree): 'time' in the root group, 'lat', 'lon', 'temp' and 'humidity' in '/atmos',
    and 'salinity' in '/atmos/ocean', which uses the coordinates of the groups above it.
    All arrays carry dimension names, so the stores open with xarray. Anomalies are injected into
    'temp' of a flat store and into the nested 'atmos/ocean/salinity' of a tree store.
    """

    if separator is None:
        separator = DEFAULT_SEPARATORS[zarr_format]
    if shards is not None and zarr_format != 3:
        raise ValueError("Sharding needs zarr format 3")
    if layout not in LAYOUTS:
        raise ValueError(f"Unknown layout {layout!r}, supported: {', '.join(LAYOUTS)}")
    chunk_key_encoding = {"name": "v2" if zarr_format == 2 else "default", "separator": separator}

    rng = np.random.default_rng(seed)

    # Manifest paths are relative to the experiment directory so the fixture is portable.
    def _rel(path: Path) -> str:
        return path.relative_to(store_path.parent).as_posix()

    time_n = 8
    lat_n = 12
    lon_n = 16
    data_chunks = (2, 4, 4)
    if shards is not None and any(s % c for s, c in zip(shards, data_chunks)):
        raise ValueError(f"Shard shape {tuple(shards)} is not a multiple of the chunk shape {data_chunks}")

    root = zarr.open_group(str(store_path), mode="w", zarr_format=zarr_format)
    root.attrs.update(
        {
            "frequency": frequency,
            "zoom": zoom,
            "generator": "zarrcurator.synthetic_store",
            "synthetic": True,
            "zarr_format": zarr_format,
        }
    )
    if layout == "tree":
        atmos = root.create_group("atmos")
        ocean = atmos.create_group("ocean")
    else:
        atmos = ocean = root

    def create_array(group, name, shape, chunks, dtype, dims, sharded=False):
        kwargs = {"chunk_key_encoding": chunk_key_encoding}
        if zarr_format == 3:
            kwargs["dimension_names"] = dims
            if sharded and shards is not None:
                kwargs["shards"] = tuple(shards)
        array = group.create_array(name, shape=shape, chunks=chunks, dtype=dtype, **kwargs)
        if zarr_format == 2:
            # xarray's dimension names of zarr v2 arrays
            array.attrs["_ARRAY_DIMENSIONS"] = dims
        return array

    time_arr = create_array(root, "time", shape=(time_n,), chunks=(time_n,), dtype="i4", dims=["time"])
    lat_arr = create_array(atmos, "lat", shape=(lat_n,), chunks=(lat_n,), dtype="f4", dims=["lat"])
    lon_arr = create_array(atmos, "lon", shape=(lon_n,), chunks=(lon_n,), dtype="f4", dims=["lon"])

    time_arr[:] = np.arange(time_n, dtype=np.int32)
    lat_arr[:] = np.linspace(-90.0, 90.0, lat_n, dtype=np.float32)
    lon_arr[:] = np.linspace(0.0, 357.5, lon_n, dtype=np.float32)

    data_shape = (time_n, lat_n, lon_n)
    data_dims = ["time", "lat", "lon"]
    temp = create_array(atmos, "temp", data_shape, data_chunks, "f4", data_dims, sharded=True)
    salinity = create_array(ocean, "salinity", data_shape, data_chunks, "f4", data_dims, sharded=True)
    humidity = create_array(atmos, "humidity", data_shape, data_chunks, "f4", data_dims, sharded=True)

    temp[:] = rng.normal(loc=280.0, scale=5.0, size=temp.shape).astype(np.float32)
    salinity[:] = rng.normal(loc=34.5, scale=1.2, size=salinity.shape).astype(np.float32)
    humidity[:] = rng.uniform(low=0.0, high=100.0, size=humidity.shape).astype(np.float32)

    if zarr_format == 2:
        zarr.consolidate_metadata(str(store_path))

    anomaly_array = "atmos/ocean/salinity" if layout == "tree" else "temp"
    anomalies: dict[str, list[str]] = {
        "zero_size": [],
        "unexpected": [],
        "missing": [],
        "corrupt": [],
    }
    if inject_anomalies:
        # A zero-sized chunk exercises missing/corrupt-chunk diagnostics paths.
        # For sharded arrays the chunk files are the shards.
        chunk_candidates = [
            p
            for p in (store_path / anomaly_array).rglob("*")
            if p.is_file() and not p.name.startswith(".") and p.name not in {"zarr.json"}
        ]
        chunk_candidates = sorted(chunk_candidates)

        if len(chunk_candidates) >= 1:
            zero_path = chunk_candidates[0]
            zero_path.write_bytes(b"")
            anomalies["zero_size"].append(_rel(zero_path))

        if len(chunk_candidates) >= 2:
            missing_path = chunk_candidates[1]
            missing_path.unlink(missing_ok=True)
            anomalies["missing"].append(_rel(missing_path))

        if len(chunk_candidates) >= 3:
            corrupt_path = chunk_candidates[2]
            # Write invalid bytes so decoding this chunk fails when read as zarr data.
            corrupt_path.write_bytes(b"CORRUPTED_CHUNK_BYTES")
            anomalies["corrupt"].append(_rel(corrupt_path))

        # Unexpected artifact file exercises unexpected-file detection logic.
        artifact_path = store_path / anomaly_array / "artifact.bad"
        artifact_path.write_text("unexpected file for diagnostics\n", encoding="utf-8")
        anomalies["unexpected"].append(_rel(artifact_path))

    return {
        "store": _rel(store_path),
        "frequency": frequency,
        "zoom": zoom,
        "seed": seed,
        "zarr_format": zarr_format,
        "separator": separator,
        "shards": list(shards) if shards is not None else None,
        "layout": layout,
        "anomaly_array": anomaly_array,
        "anomalies": anomalies,
    }


def store_variant_tag(zarr_format: int, separator: str, sharded: bool, layout: str) -> str:
    """Return the tag of a store variant in store names, e.g. 'z2', 'z2slash', 'z3shard', 'z3dotshardtree'.

    Only what differs from the default (format default separator, no sharding, flat) is added.
    The tag has no '_', as store names are split on '_' by the dispatcher.
    """
    tag = f"z{zarr_format}"
    if separator != DEFAULT_SEPARATORS[zarr_format]:
        tag += SEPARATOR_NAMES[separator]
    if sharded:
        tag += "shard"
    if layout != "flat":
        tag += layout
    return tag


def create_synthetic_experiment(
    output_dir: Path,
    experiment_name: str,
    frequencies: list[str],
    stores_per_frequency: int,
    start_zoom: int,
    zarr_formats: list[int],
    inject_anomalies: bool,
    clean: bool,
    separators: list[str] | None = None,
    shards: tuple[int, ...] | None = None,
    layouts: list[str] | None = None,
) -> dict:
    """Create an experiment directory containing multiple synthetic stores.

    One set of stores is created per combination of zarr format, entry in ``separators``
    (None: only the format default), sharding and entry in ``layouts`` (None: only 'flat').
    With ``shards``, the zarr v3 stores are created both without and with sharding of the data
    variables. The variant is tagged in the store name, see store_variant_tag(), e.g.
    ``syntheticexp_P1D_000_z2slash.zarr`` or ``syntheticexp_P1D_000_z3shardtree.zarr``.
    """

    if clean and output_dir.exists():
        shutil.rmtree(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    work_dir = output_dir / "work"
    work_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "experiment": experiment_name,
        "root": ".",
        "work_dir": work_dir.relative_to(output_dir).as_posix(),
        "stores": [],
    }

    seed = 100
    for fmt in zarr_formats:
        for sep in separators or [DEFAULT_SEPARATORS[fmt]]:
            for sharded in [False] + ([True] if shards is not None and fmt == 3 else []):
                for layout in layouts or ["flat"]:
                    tag = store_variant_tag(fmt, sep, sharded, layout)
                    for freq in frequencies:
                        for idx in range(stores_per_frequency):
                            store_name = f"{experiment_name}_{freq}_{idx:03d}_{tag}.zarr"
                            store_path = output_dir / store_name
                            created = _create_single_store(
                                store_path=store_path,
                                frequency=freq,
                                zoom=start_zoom + idx,
                                seed=seed,
                                zarr_format=fmt,
                                inject_anomalies=inject_anomalies,
                                separator=sep,
                                shards=shards if sharded else None,
                                layout=layout,
                            )
                            manifest["stores"].append(created)
                            seed += 1

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    logger.info("Synthetic experiment created at %s", output_dir)

    return manifest


def run_smoke_pipeline(experiment_dir: Path, work_dir: Path, target_size_bytes: int) -> dict:
    """Run diagnose/distribute/dispatch on the generated synthetic experiment."""

    configObj.setZarrStorePath(str(experiment_dir))
    configObj.setWorkingDir(str(work_dir))
    configObj.setJsonFile("synthetic.diag.json")
    configObj.setTargetSize(target_size_bytes)

    diagnoser = Diagnoser()
    diagnoser.update()
    configObj.setDiagnoserObj(diagnoser)

    distributor = Distributor(diagnoser, target_size_bytes)
    distributor.updateFrequencyGroupDict()
    distributor.updateFrequencySubGroupDictWithSingleZarrStore()
    distributor.redistributeSubGroups()
    distributor.updateDimensionsToSubGroups()
    configObj.setDistributorObj(distributor)

    dispatcher = Dispatcher("synthetic", distributor)
    dispatcher.createTarForFrequencySubGroupDict()
    dispatcher.executor(-1)

    tar_count = 0
    for freq_groups in distributor.frequencySubGroupDict.values():
        for subgroup in freq_groups.values():
            tar_count += len(subgroup.getTarMembers())

    return {
        "stores_diagnosed": len(diagnoser.list_of_zarrs),
        "frequencies": sorted(distributor.frequencySubGroupDict.keys()),
        "tars_created": tar_count,
        "diag_json": str(work_dir / "synthetic.diag.json"),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create synthetic Zarr stores for zarrcurator feature checks")
    parser.add_argument(
        "--output-dir",
        default="tests/data/synthetic_experiment",
        help="Directory where synthetic .zarr stores and manifest are created",
    )
    parser.add_argument("--experiment-name", default="syntheticexp", help="Prefix for generated store names")
    parser.add_argument(
        "--frequencies",
        default="P1D,PT1H",
        help="Comma-separated frequencies in store names (example: P1D,PT1H)",
    )
    parser.add_argument("--stores-per-frequency", type=int, default=2)
    parser.add_argument("--start-zoom", type=int, default=1)
    parser.add_argument(
        "--zarr-formats",
        default="2,3",
        help="Comma-separated zarr formats to generate (supported: 2,3)",
    )
    parser.add_argument(
        "--separators",
        default="",
        help="Comma-separated chunk key separators to generate for each format (supported: .,/); "
        "default is each format's own default (v2 '.', v3 '/')",
    )
    parser.add_argument(
        "--shards",
        default="",
        help="Shard shape of the data variables (time,lat,lon), a multiple of the chunk shape 2,4,4 "
        "(example: 4,4,8); creates the zarr v3 stores without and with sharding. Default: no sharding",
    )
    parser.add_argument(
        "--layouts",
        default="flat",
        help="Comma-separated store layouts to generate (supported: flat,tree); 'tree' nests the "
        "arrays in groups, as written from an xarray DataTree",
    )
    parser.add_argument("--target-size-bytes", type=int, default=10 * 1024 * 1024)
    parser.add_argument("--clean", action="store_true", help="Delete output directory before generation")
    parser.add_argument(
        "--no-anomalies",
        action="store_true",
        help="Do not inject zero-sized chunk/unexpected artifact file",
    )
    parser.add_argument(
        "--run-smoke",
        action="store_true",
        help="Run diagnose/distribute/dispatch after generation",
    )
    parser.add_argument("--log-level", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)

    output_dir = Path(args.output_dir).resolve()
    frequencies = [item.strip() for item in args.frequencies.split(",") if item.strip()]
    zarr_formats = [int(item.strip()) for item in args.zarr_formats.split(",") if item.strip()]

    if not frequencies:
        raise SystemExit("At least one frequency is required")
    if any(fmt not in {2, 3} for fmt in zarr_formats):
        raise SystemExit("--zarr-formats supports only 2 and 3")
    separators = [item.strip() for item in args.separators.split(",") if item.strip()]
    if any(sep not in SEPARATOR_NAMES for sep in separators):
        raise SystemExit("--separators supports only '.' and '/'")
    shards = tuple(int(item.strip()) for item in args.shards.split(",") if item.strip()) or None
    if shards is not None and 3 not in zarr_formats:
        raise SystemExit("--shards needs zarr format 3 in --zarr-formats")
    layouts = [item.strip() for item in args.layouts.split(",") if item.strip()]
    if not layouts or any(layout not in LAYOUTS for layout in layouts):
        raise SystemExit(f"--layouts supports only {', '.join(LAYOUTS)}")

    manifest = create_synthetic_experiment(
        output_dir=output_dir,
        experiment_name=args.experiment_name,
        frequencies=frequencies,
        stores_per_frequency=args.stores_per_frequency,
        start_zoom=args.start_zoom,
        zarr_formats=zarr_formats,
        inject_anomalies=not args.no_anomalies,
        clean=args.clean,
        separators=separators or None,
        shards=shards,
        layouts=layouts,
    )

    result = {
        "created": manifest,
    }

    if args.run_smoke:
        smoke = run_smoke_pipeline(
            experiment_dir=output_dir,
            work_dir=output_dir / "work",
            target_size_bytes=args.target_size_bytes,
        )
        result["smoke"] = smoke

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
