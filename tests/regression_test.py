"""Regression tests for high-impact bug fixes in zarrcurator.

Run with:
    /work/bm0146/k204247/miniconda3/envs/s3Dev/bin/python -m tests.regression_test
"""

import inspect
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from zarrcurator import utils
from zarrcurator.config import configVars
from zarrcurator.diagnoser import Diagnoser
from zarrcurator.dispatcher import Dispatcher
from zarrcurator.distributor import Distributor
from zarrcurator.subgroup import SubGroup


class RegressionFixesTest(unittest.TestCase):
    """Regression tests for past bug fixes, and the anomalies of every synthetic store variant."""

    def test_subgroup_tar_getters_are_distinct(self):
        subgroup = SubGroup([], "zarr", ["a.tar"], ["TAPE1"])
        self.assertEqual(subgroup.getTarMembers(), ["a.tar"])
        self.assertEqual(subgroup.getTarTapeIDs(), ["TAPE1"])

    def test_distributor_constructor_signature(self):
        sig = inspect.signature(Distributor.__init__)
        self.assertEqual(list(sig.parameters.keys()), ["self", "diagnoserObj", "targetSize"])

    def test_no_method_object_checks_in_fixed_paths(self):
        src_dispatch_store = inspect.getsource(utils.dispatchStoreToTarStores)
        self.assertNotIn("if configObj.getFileSystemObj is not None", src_dispatch_store)

        src_dispatcher = inspect.getsource(Dispatcher.createTarForZarr)
        self.assertNotIn("if configObj.getFileSystemObj is not None", src_dispatcher)

        src_distributor = inspect.getsource(Distributor.__init__)
        self.assertNotIn("if configObj.getFileSystemObj is None", src_distributor)

    def test_invalid_isinstance_pattern_removed(self):
        src = inspect.getsource(utils.findMissingChunksInStore)
        self.assertNotIn("store is isinstance(store,zarr.core.group.Group)", src)

    def test_utils_credential_function_and_signatures(self):
        self.assertTrue(hasattr(utils, "setObjectStoreCredentials"))

        update_sig = inspect.signature(utils.updateStoretoConfig)
        self.assertIn("accessKey", update_sig.parameters)
        self.assertIn("secretKey", update_sig.parameters)

        diagnose_sig = inspect.signature(utils.diagnoseStore)
        self.assertIn("accessKey", diagnose_sig.parameters)
        self.assertIn("secretKey", diagnose_sig.parameters)

        missing_sig = inspect.signature(utils.findMissingChunksInStore)
        self.assertIn("accessKey", missing_sig.parameters)
        self.assertIn("secretKey", missing_sig.parameters)

    def test_parse_object_store_url_static_utility(self):
        parsed = configVars.parse_object_store_url("https://example.org/bucket/path/to/file.zarr")
        self.assertEqual(parsed["endpoint"], "https://example.org")
        self.assertEqual(parsed["bucket"], "bucket")
        self.assertEqual(parsed["object_key"], "path/to/file.zarr")
        self.assertEqual(parsed["s3_uri"], "s3://bucket/path/to/file.zarr")

    def test_create_statistics_no_undefined_var_path(self):
        diagnoser = Diagnoser.__new__(Diagnoser)
        diagnoser.sorted_tuplelist_obj = []
        diagnoser.exp_path = "/tmp/test.zarr"

        # Should not raise AttributeError due to missing var_path.
        diagnoser.createStatistics()

    def test_find_missing_chunks_reports_zero_size(self):
        manifest_path = (
            Path(__file__).resolve().parent
            / "data"
            / "synthetic_experiment"
            / "manifest.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        store_path = str(manifest_path.parent / manifest["stores"][0]["store"])

        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                utils.findMissingChunksInStore(store_path)
            finally:
                os.chdir(old_cwd)

            report_path = Path(tmpdir) / "syntheticexp_P1D_000_z2.check"
            self.assertTrue(report_path.exists())
            report = utils.flattenCheckReport(json.loads(report_path.read_text(encoding="utf-8")))

            self.assertIn("/temp", report)
            self.assertIn("zero_size", report["/temp"])
            self.assertIn("0.0.0", report["/temp"]["zero_size"])

    def test_synthetic_store_layouts_report_injected_anomalies(self):
        from zarrcurator import synthetic_store
        from zarrcurator.chunkkeys import parseChunkKey

        # (zarr_format, separator) -> store name tag and key of the first chunk (or shard).
        first_keys = {
            (2, "."): ("z2", "0.0.0"),
            (2, "/"): ("z2slash", "0/0/0"),
            (3, "/"): ("z3", "c/0/0/0"),
            (3, "."): ("z3dot", "c.0.0.0"),
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            manifest = synthetic_store.create_synthetic_experiment(
                output_dir=tmp_path / "exp",
                experiment_name="syntheticexp",
                frequencies=["P1D"],
                stores_per_frequency=1,
                start_zoom=1,
                zarr_formats=[2, 3],
                inject_anomalies=True,
                clean=False,
                separators=[".", "/"],
                shards=(4, 4, 8),
                layouts=["flat", "tree"],
            )
            # 2 separators x 2 layouts for zarr v2, and without and with sharding for zarr v3.
            self.assertEqual(len(manifest["stores"]), 4 + 8)

            for entry in manifest["stores"]:
                fmt, sep, layout = entry["zarr_format"], entry["separator"], entry["layout"]
                sharded = entry["shards"] is not None
                tag, first_key = first_keys[(fmt, sep)]
                tag += ("shard" if sharded else "") + ("tree" if layout == "tree" else "")
                with self.subTest(zarr_format=fmt, separator=sep, sharded=sharded, layout=layout):
                    self.assertEqual(entry["store"], f"syntheticexp_P1D_000_{tag}.zarr")
                    self.assertEqual(entry["anomaly_array"], "atmos/ocean/salinity" if layout == "tree" else "temp")
                    var_prefix = f"{entry['store']}/{entry['anomaly_array']}/"
                    rel = {k: [p[len(var_prefix):] for p in v] for k, v in entry["anomalies"].items()}
                    self.assertEqual(rel["zero_size"], [first_key])

                    old_cwd = os.getcwd()
                    try:
                        os.chdir(tmpdir)
                        with mock.patch("sys.stdout"):
                            utils.findMissingChunksInStore(str(tmp_path / "exp" / entry["store"]))
                    finally:
                        os.chdir(old_cwd)

                    report_name = entry["store"][: -len(".zarr")] + ".check"
                    report = utils.flattenCheckReport(json.loads((tmp_path / report_name).read_text(encoding="utf-8")))
                    array_report = report[f"/{entry['anomaly_array']}"]
                    # Sharded arrays are checked by shard: 2 x 3 x 2 shards of 4 x 4 x 8.
                    self.assertEqual(array_report["expected_chunks"], 12 if sharded else 48)
                    self.assertEqual(array_report["zero_size"], rel["zero_size"])
                    self.assertEqual(array_report["unexpected"], rel["unexpected"])
                    # Missing chunks are reported as normalized dot-separated coordinates.
                    self.assertEqual(
                        array_report["missing"],
                        [".".join(map(str, parseChunkKey(k))) for k in rel["missing"]],
                    )
                    # A zero-size chunk or shard is unreadable too, so it is also reported as corrupt
                    # (zarr >= 3.4.1 raises for a truncated shard; older versions read it as not written).
                    expected_corrupt = rel["zero_size"] + rel["corrupt"]
                    self.assertEqual(sorted(array_report["corrupt"]), sorted(expected_corrupt))
                    # The other arrays are intact.
                    for name, other in report.items():
                        if name != f"/{entry['anomaly_array']}":
                            self.assertEqual(other["missing"] + other["zero_size"] + other["corrupt"], [], name)

    def test_dispatch_store_to_tarstores_local_backend_uses_path(self):
        fake_distributor = SimpleNamespace(frequencySubGroupDict={})

        with mock.patch.object(utils, "Dispatcher") as mock_dispatcher_cls, \
             mock.patch.object(utils.configObj, "getDistributorObj", return_value=fake_distributor), \
             mock.patch.object(utils.configObj, "setDispatcherObj"), \
             mock.patch.object(utils, "updateStoretoConfig", return_value=(None, "/tmp/local.zarr", "local.zarr")) as mock_update, \
             mock.patch.object(utils.configObj, "getZarrStorePath", return_value="/tmp/local.zarr"), \
             mock.patch.object(utils, "xr") as mock_xr, \
             mock.patch.object(utils.configObj, "getWorkingDir", return_value=tempfile.gettempdir()):

            mock_dispatcher = mock.Mock()
            mock_dispatcher_cls.return_value = mock_dispatcher
            mock_xr.open_zarr.return_value = mock.Mock(zoom="z1", frequency="P1D", sizes={})

            utils.dispatchStoreToTarStores("/tmp/local.zarr")

            mock_update.assert_called_with("/tmp/local.zarr")
            # The store is checked to open with xarray, with all its groups.
            mock_xr.open_datatree.assert_called_once_with("/tmp/local.zarr", engine="zarr")
            mock_dispatcher.createTarForFrequencySubGroupDict.assert_called_once()
            mock_dispatcher.executor.assert_called_once_with(-1)

    def test_dispatch_store_to_tarstores_object_backend_uses_store(self):
        fake_distributor = SimpleNamespace(frequencySubGroupDict={})
        fake_fs = mock.Mock()
        fake_store = mock.Mock()
        fake_store.store = "mapped-store"

        with mock.patch.object(utils, "Dispatcher") as mock_dispatcher_cls, \
             mock.patch.object(utils.configObj, "getDistributorObj", return_value=fake_distributor), \
             mock.patch.object(utils.configObj, "setDispatcherObj"), \
             mock.patch.object(utils, "updateStoretoConfig", return_value=(fake_fs, fake_store, "remote.zarr")) as mock_update, \
             mock.patch.object(utils.configObj, "getZarrStorePath", return_value="bucket/remote.zarr"), \
             mock.patch.object(utils, "xr") as mock_xr, \
             mock.patch.object(utils.configObj, "getWorkingDir", return_value=tempfile.gettempdir()):

            mock_dispatcher = mock.Mock()
            mock_dispatcher_cls.return_value = mock_dispatcher
            mock_xr.open_zarr.return_value = mock.Mock(zoom="z1", frequency="P1D", sizes={})

            utils.dispatchStoreToTarStores("https://example.org/bucket/remote.zarr")

            mock_update.assert_called_with("https://example.org/bucket/remote.zarr")
            mock_xr.open_datatree.assert_called_once_with("mapped-store", engine="zarr")
            mock_dispatcher.createTarForFrequencySubGroupDict.assert_called_once()
            mock_dispatcher.executor.assert_called_once_with(-1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
