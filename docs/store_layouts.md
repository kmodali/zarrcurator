# Store Layouts

zarrcurator diagnoses, splits and archives zarr stores in all of these layouts, and
creates Kerchunk references for the resulting tarballs:

| Layout | Supported |
| ------ | --------- |
| zarr v2 and zarr v3 | yes |
| Chunk key separators `.` and `/` | yes: v2 `0.1` / `0/1`, v3 `c.0.1` / `c/0/1`, and v3 with the `v2` key encoding |
| Nested groups (e.g. written with `xarray.DataTree.to_zarr`) | yes |
| Sharded arrays (zarr v3 `sharding_indexed`) | yes, see Sharding below |

A store must open with xarray: every array needs dimension names (`_ARRAY_DIMENSIONS`
in zarr v2, `dimension_names` in zarr v3). Stores written with xarray have them; stores
written with plain zarr may not. `dispatchStoreToTarStores` checks this first (with
`checkStoreOpensWithXarray`) and raises a `ValueError` before diagnosing, splitting or
archiving a store xarray cannot open.

## Nested groups

In a store with nested groups, each array is handled by its path from the store root,
e.g. `atmos/ocean/salinity`.

- **Diagnosis** records the size of each array by its path, and the metadata files of each
  group, e.g. `atmos/.zgroup` (v2) or `atmos/zarr.json` (v3). The `.diag` file is nested by
  group, like the `.check` report, e.g. `{store: {"atmos": {"ocean": {"salinity": {...}}}}}`;
  each entry has `"type": "array"` (or `"file"` for metadata files) and its `path`, e.g.
  `atmos/ocean/salinity`. Each group holds the totals of its arrays, metadata files and sub
  groups under `"__total__"`, e.g. `{"size": 1024, "count": 12}` (names starting with `__`
  are reserved in zarr v3); the store totals `size` and `count` stay at the store level.
  `flattenDiagReport` gives the diagnosis keyed by entry path; `.diag` files written flat by
  older versions still load.
- **Distribution**: in the `.dist` file, the `groupMembers` of each subgroup are nested by group
  in the same way, with `"__total__": {"size": ..., "members": ...}` for each group. Each member
  keeps its original name as `path` (coordinate variables are given by absolute path) and its
  position as `index`, as the order of the members matters, e.g. the first member of a `chunk`
  subgroup is the array to split. `flattenDistReport` gives the members as a list again; `.dist`
  files written flat by older versions still load.
- **`findMissingChunksInStore`** checks every array in the store, including those in nested
  groups. The `.check` report is nested by group, e.g. `{"atmos": {"ocean": {"salinity": {...}}}}`;
  each array entry has `"type": "array"` and its `path`, e.g. `/atmos/ocean/salinity`.
  `flattenCheckReport` gives the report keyed by array path.
- **Splitting**: a store larger than the target size is split group by group, so a tarball never
  mixes the arrays of different groups, e.g. of different HEALPix zoom levels (`multiscales/zoom_0`,
  …, `multiscales/zoom_11`). The arrays of a group are packed into tarballs of about the target
  size. Arrays are not split inside these `var` tarballs, so a `var` tarball can be larger than
  the target; only an array that is itself larger than the target is split into `chunk` tarballs
  of its chunks. Groups with metadata
  files only (e.g. the store root) go with the first group that has arrays. A store that fits the
  target size is archived whole, in one tarball.
- **Names**: the subgroups of a split store, and so their tarballs, are named by the store, the
  group and a number counted per group, e.g. `P1D_mean_atm_zoom_11_3.tar`, or
  `P1D_mean_atm_zoom_11_15_1.tar` for the tarballs of an array split into its chunks. A group is
  labelled by its name, or by its path with `_` for `/` if several groups have that name (e.g.
  `atmos_zoom_0`, `ocean_zoom_0`). Subgroups of the root group, e.g. of a store without nested
  groups, are named by the store and the number only, e.g. `ngc4008_P1D_7_3.tar`.
- **Coordinates**: each tarball gets the coordinate variables of its arrays. A group can use
  the coordinates of the groups above it, as in an xarray DataTree, so each coordinate is looked
  up in the array's own group first, then in its parent groups up to the store root.
- **Tarballs** contain the metadata of every group from the store root down to their arrays,
  so each tarball opens with `xarray.open_datatree`.

## Sharding

In a sharded array each shard is one file, so zarrcurator handles shards like chunks:

- `findMissingChunksInStore` checks the shards (`expected_chunks` counts shards). A shard of
  zero size is reported under `zero_size` and, as it cannot be read, also under `corrupt`, like a
  zero-size chunk (zarr 3.4.1 and newer; older versions read an empty shard as not written).
- Arrays larger than the target size are split into tarballs of whole shards. A shard cannot be
  split, so a single shard larger than the target size makes a tarball larger than the target.
- The Kerchunk references point to the inner chunks: the index of each shard is read from the
  tarball (at the end or the start of the shard, its `crc32c` checksum verified) and each inner
  chunk becomes a reference to its byte range. A corrupted shard index raises a `ValueError`.

Nested sharding, a codec applied after `sharding_indexed`, and shard index codecs other than
`bytes` with an optional `crc32c` are not supported and raise a `ValueError`.

## Kerchunk references

`createKerchunkReferenceFileForTar` writes the references of one tarball;
`convertKerchunkReferenceFilesOfZarrStoreToParquet` merges the references of all tarballs of a
store (`<store>_*_Offset_kerchunk.json`) into one parquet reference of the whole store
(`<store>.parq`).

- The tarballs of a store are parts of it, so their references are merged: each chunk of a data
  variable is in one tarball; metadata and coordinate variables are in several and are kept once,
  after checking that their content is the same. A key with a different content in two tarballs
  raises a `ValueError`.
- The references are written in the zarr v2 layout. For zarr v3 stores the metadata is translated
  to zarr v2 and the chunks are referenced unchanged, which works for the `bytes` codec followed by
  at most one compressor (`zstd`, `gzip`, `blosc` or a `numcodecs.*` codec). The reopened data is
  zarr v2.
- The references of different stores are not combined: tarballs are not concatenated along `time`.

Opening the references of a store without nested groups:

```python
import fsspec
import xarray as xr

mapper = fsspec.get_mapper(
    "reference://", fo="work/mystore.parq", remote_protocol="file"
)
ds = xr.open_dataset(mapper, engine="zarr", consolidated=False, zarr_format=2)
```

Opening the references of a store with nested groups needs `consolidated=True`, as fsspec's
listing of parquet references does not find nested groups:

```python
tree = xr.open_datatree(
    "reference://",
    engine="zarr",
    consolidated=True,
    zarr_format=2,
    storage_options={"fo": "work/mystore.parq", "remote_protocol": "file"},
)
```

## Synthetic test stores

`python -m zarrcurator.synthetic_store` generates small stores in each of these layouts, with
anomalies injected for the diagnostics, see the README. The fixture in
`tests/data/synthetic_experiment` holds one store per layout and frequency.
