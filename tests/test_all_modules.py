"""Unit tests with coverage across all zarrcurator modules.

Run with:
    /work/bm0146/k204247/miniconda3/envs/s3Dev/bin/python -m tests.test_all_modules
"""

import ast
import collections
import importlib
import io
import json
import logging
import math
import os
import signal
import sys
import tarfile
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

try:
    import fsspec
except Exception:
    fsspec = None

try:
    import numpy as np
except Exception:
    np = None

try:
    import zarr
except Exception:
    zarr = None


TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
PACKAGE_DIR = REPO_ROOT / "src" / "zarrcurator"


class TestModuleSourceCoverage(unittest.TestCase):
    """Every module of the package compiles."""

    def test_all_python_module_sources_compile(self):
        module_files = sorted(
            p for p in PACKAGE_DIR.glob("*.py") if p.name != "py.typed"
        )
        self.assertTrue(module_files)

        for module_file in module_files:
            with self.subTest(module=module_file.name):
                src = module_file.read_text(encoding="utf-8")
                compile(src, str(module_file), "exec")


class TestCoreAndCli(unittest.TestCase):
    """Core functions, the command line interface and logging setup."""

    def test_cli_main(self):
        from zarrcurator import cli

        with mock.patch("sys.argv", ["zarrcurator", "Alice"]):
            with mock.patch.object(cli, "configure_logging") as mock_configure:
                cli.main()

        mock_configure.assert_called_once_with(None)

    def test_cli_main_requires_name(self):
        from zarrcurator import cli

        with mock.patch("sys.argv", ["zarrcurator"]):
            with redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as ctx:
                    cli.main()

        self.assertEqual(ctx.exception.code, 2)

    def test_cli_main_with_log_level_arg(self):
        from zarrcurator import cli

        with mock.patch("sys.argv", ["zarrcurator", "Alice", "--log-level", "DEBUG"]):
            with mock.patch("logging.basicConfig") as mock_basic_config:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    cli.main()

        self.assertTrue(mock_basic_config.called)
        kwargs = mock_basic_config.call_args.kwargs
        self.assertEqual(kwargs["level"], 10)

    def test_configure_logging_uses_env_var(self):
        from zarrcurator import cli

        with mock.patch.dict(os.environ, {"ZARRCURATOR_LOG_LEVEL": "ERROR"}, clear=False):
            with mock.patch("logging.basicConfig") as mock_basic_config:
                level_name = cli.configure_logging(None)

        self.assertEqual(level_name, "ERROR")
        kwargs = mock_basic_config.call_args.kwargs
        self.assertEqual(kwargs["level"], 40)

    def test_configure_logging_adds_timestamped_file_handler(self):
        from zarrcurator import cli

        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(os.environ, {"ZARRCURATOR_LOG_DIR": tmpdir}, clear=False):
                with mock.patch("logging.basicConfig") as mock_basic_config:
                    cli.configure_logging("INFO")

        kwargs = mock_basic_config.call_args.kwargs
        handlers = kwargs["handlers"]
        file_handlers = [h for h in handlers if isinstance(h, logging.FileHandler)]
        self.assertEqual(len(file_handlers), 1)

        file_name = Path(file_handlers[0].baseFilename).name
        self.assertRegex(file_name, r"^zarrcurator_\d{8}_\d{6}\.log$")

    def test_enable_logging_uses_cli_configure_logging(self):
        import zarrcurator

        with mock.patch("zarrcurator.cli.configure_logging", return_value="DEBUG") as mock_cfg:
            level_name = zarrcurator.enable_logging("DEBUG")

        self.assertEqual(level_name, "DEBUG")
        mock_cfg.assert_called_once_with("DEBUG")

    def test_enable_logging_is_exported(self):
        import zarrcurator

        self.assertIn("enable_logging", zarrcurator.__all__)


class TestConfigAndSubgroup(unittest.TestCase):
    """Configuration, object-store access and subgroups."""

    def test_parse_object_store_url(self):
        from zarrcurator.config import configVars

        parsed = configVars.parse_object_store_url(
            "https://example.org/mybucket/path/to/store.zarr"
        )
        self.assertEqual(parsed["endpoint"], "https://example.org")
        self.assertEqual(parsed["bucket"], "mybucket")
        self.assertEqual(parsed["object_key"], "path/to/store.zarr")
        self.assertEqual(parsed["s3_uri"], "s3://mybucket/path/to/store.zarr")

    def test_config_roundtrip_file(self):
        from zarrcurator.config import configVars

        cfg = configVars(
            zarr_store_path="/tmp/store",
            workingDir=os.getcwd(),
            jsonFile="diag.json",
            targetSize=123,
            batchMode=True,
            debugMode=False,
            packDiscontinuousData=True,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_file = Path(tmpdir) / "cfg.json"
            cfg.toFile(str(cfg_file))

            cfg2 = configVars()
            cfg2.fromFile(str(cfg_file))

            self.assertEqual(cfg2.getJsonFile(), "diag.json")
            self.assertEqual(cfg2.getTargetSize(), 123)
            self.assertTrue(cfg2.getBatchMode())
            self.assertTrue(cfg2.getPackDiscontinuousData())

    def test_config_to_file_ignores_runtime_non_serializable_objects(self):
        from zarrcurator.config import configVars

        class _NonSerializable:
            pass

        cfg = configVars(
            zarr_store_path="/tmp/store",
            workingDir=os.getcwd(),
            jsonFile="diag.json",
            targetSize=123,
            batchMode=True,
            debugMode=False,
            packDiscontinuousData=True,
        )
        cfg.fileSystemObj = _NonSerializable()
        cfg.diagnoserObj = _NonSerializable()
        cfg.distributorObj = _NonSerializable()
        cfg.dispatcherObj = _NonSerializable()

        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_file = Path(tmpdir) / "cfg.json"
            cfg.toFile(str(cfg_file))

            data = json.loads(cfg_file.read_text(encoding="utf-8"))
            self.assertNotIn("fileSystemObj", data)
            self.assertNotIn("diagnoserObj", data)
            self.assertNotIn("distributorObj", data)
            self.assertNotIn("dispatcherObj", data)
            self.assertEqual(data["zarrStorePath"], "/tmp/store")

    def test_set_filesystem_s3_exits_when_anon_fails_and_no_credentials(self):
        from zarrcurator.config import configVars

        class _FailingFS:
            def ls(self, _path):
                raise PermissionError("Access denied")

        cfg = configVars()
        with mock.patch.dict(
            os.environ,
            {
                "AWS_ACCESS_KEY_ID": "",
                "AWS_SECRET_ACCESS_KEY": "",
                "S3_ACCESS_KEY_ID": "",
                "S3_SECRET_ACCESS_KEY": "",
            },
            clear=False,
        ):
            with mock.patch("zarrcurator.config.fsspec.filesystem", return_value=_FailingFS()) as mock_fs:
                with self.assertLogs("zarrcurator.config", level="WARNING") as logs:
                    with self.assertRaises(SystemExit):
                        cfg.setFileSystemObj("https://s3.eu-dkrz-3.dkrz.cloud/mybucket/store.zarr")

        self.assertEqual(mock_fs.call_count, 1)
        kwargs = mock_fs.call_args.kwargs
        self.assertTrue(kwargs["anon"])
        joined = "\n".join(logs.output)
        self.assertIn("Anonymous access failed", joined)
        self.assertIn("not publicly accessible and no access credentials", joined)

    def test_set_filesystem_s3_falls_back_to_credentials_after_anon_failure(self):
        from zarrcurator.config import configVars

        class _AnonFailFS:
            def ls(self, _path):
                raise PermissionError("Access denied")

        class _AuthOKFS:
            def ls(self, _path):
                return ["ok"]

        cfg = configVars(accessKey="ZA_ACCESS_ENV", secretKey="ZA_SECRET_ENV")
        with mock.patch.dict(
            os.environ,
            {
                "ZA_ACCESS_ENV": "AK",
                "ZA_SECRET_ENV": "SK",
            },
            clear=False,
        ):
            with mock.patch(
                "zarrcurator.config.fsspec.filesystem",
                side_effect=[_AnonFailFS(), _AuthOKFS()],
            ) as mock_fs:
                out_path = cfg.setFileSystemObj("https://s3.eu-dkrz-3.dkrz.cloud/mybucket/store.zarr")

        self.assertEqual(out_path, "mybucket/store.zarr")
        self.assertEqual(mock_fs.call_count, 2)
        first_kwargs = mock_fs.call_args_list[0].kwargs
        second_kwargs = mock_fs.call_args_list[1].kwargs
        self.assertTrue(first_kwargs["anon"])
        self.assertFalse(second_kwargs["anon"])
        self.assertEqual(second_kwargs["key"], "AK")
        self.assertEqual(second_kwargs["secret"], "SK")

    def test_subgroup_update_and_dict(self):
        from zarrcurator.subgroup import SubGroup, subGroup_to_dict

        sg = SubGroup([], "zarr", ["x.tar"], ["TAPE1"])
        sg.updateSubGroup(("varA", 10))
        sg.updateSubGroup([("varB", 20), ("varC", 30)])

        self.assertEqual(sg.groupSize, 60)
        self.assertEqual(sg.getTarMembers(), ["x.tar"])
        self.assertEqual(sg.getTarTapeIDs(), ["TAPE1"])

        as_dict = subGroup_to_dict(sg)
        self.assertEqual(as_dict["groupType"], "zarr")
        self.assertEqual(as_dict["groupSize"], 60)


class TestDiagnoserDistributorDispatcher(unittest.TestCase):
    """Smoke tests of the diagnoser, distributor and dispatcher."""

    def test_diagnoser_create_statistics_smoke(self):
        from zarrcurator.diagnoser import Diagnoser

        obj = Diagnoser.__new__(Diagnoser)
        obj.sorted_tuplelist_obj = []
        obj.exp_path = "/tmp/test.zarr"
        obj.createStatistics()

        obj.sorted_tuplelist_obj = [("v1", 1), ("v2", 5)]
        obj.createStatistics()

    def test_distributor_frequency_paths(self):
        from zarrcurator.distributor import Distributor

        class FakeDiagnoser:
            list_of_zarrs = ["/tmp/ngc4008_P1D_0.zarr"]
            exp_size_dict = {
                "/tmp/ngc4008_P1D_0.zarr": {
                    "size": 100,
                    "count": 10,
                    "/tmp/ngc4008_P1D_0.zarr/ta": {"size": 50, "count": 5},
                }
            }

        dist = Distributor(FakeDiagnoser(), 200)
        self.assertIn("P1D", dist.frequencyList)

        dist.updateFrequencyGroupDict()
        self.assertIn("P1D", dist.frequencyGroupDict)

        dist.updateFrequencySubGroupDictWithSingleZarrStore()
        self.assertIn("P1D", dist.frequencySubGroupDict)
        self.assertTrue(dist.frequencySubGroupDict["P1D"])

    def test_distributor_accepts_store_without_frequency_in_name(self):
        """A store not named <exp>_<freq>_..., e.g. a group of a store, has frequency 'ALL'."""
        from zarrcurator.distributor import Distributor

        store = "/tmp/d3hp003.zarr/P1D_mean_atm"

        class FakeDiagnoser:
            list_of_zarrs = [store]
            exp_size_dict = {store: {"size": 100, "count": 10, "multiscales/zoom_0/tas": {"size": 100, "count": 10}}}

        dist = Distributor(FakeDiagnoser(), 200)
        self.assertEqual(dist.frequencyList, ["ALL"])

        dist.updateFrequencyGroupDict()
        self.assertIn(store, dist.frequencyGroupDict["ALL"])

        dist.updateFrequencySubGroupDictWithSingleZarrStore()
        self.assertTrue(dist.frequencySubGroupDict["ALL"])

    def test_dist_report_is_nested_by_group(self):
        """The members of the subgroups in the '.dist' file are nested by group, in their order."""
        from zarrcurator.config import configObj
        from zarrcurator.distributor import Distributor
        from zarrcurator.storetree import flattenDistReport, nestDistReport

        store = "/tmp/tree.zarr"
        flat = {"ALL": {
            "tree_1": {"groupMembers": [[store, 37]], "groupType": "zarr",
                       "groupTarMembers": [], "groupTarTapeIDs": [], "groupSize": 37},
            "tree_2": {"groupMembers": [["z2/ocean/sst", 20], [f"{store}/z2/ocean/time", 3], ["tas", 10]],
                       "groupType": "var", "groupTarMembers": ["t.tar"], "groupTarTapeIDs": [], "groupSize": 33},
        }}
        nested = nestDistReport(flat, store)
        self.assertEqual(nested["ALL"]["tree_1"]["groupMembers"]["tree.zarr"]["type"], "store")
        members = nested["ALL"]["tree_2"]["groupMembers"]
        self.assertEqual(members["z2"]["__total__"], {"size": 23, "members": 2})
        self.assertEqual(members["z2"]["ocean"]["time"],
                         {"type": "array", "path": f"{store}/z2/ocean/time", "size": 3, "index": 1})
        self.assertEqual(nested["ALL"]["tree_2"]["groupTarMembers"], ["t.tar"])
        # The members come back in their original order, e.g. the array to split of a chunk subgroup first
        self.assertEqual(flattenDistReport(nested), flat)
        self.assertEqual(flattenDistReport(flat), flat)

        # Distributor.update loads both formats
        for report in (nested, flat):
            with self.subTest(nested=report is nested), tempfile.TemporaryDirectory() as tmpdir:
                (Path(tmpdir) / "tree.dist").write_text(json.dumps(report), encoding="utf-8")
                distributor = Distributor.__new__(Distributor)
                with mock.patch.object(configObj, "getZarrStorePath", return_value=store), \
                     mock.patch.object(configObj, "getWorkingDir", return_value=tmpdir), \
                     redirect_stdout(io.StringIO()):
                    self.assertIsNone(distributor.update())
                subGroup = distributor.frequencySubGroupDict["ALL"]["tree_2"]
                self.assertEqual(subGroup.groupMembers, flat["ALL"]["tree_2"]["groupMembers"])
                self.assertEqual(subGroup.groupSize, 33)

    def test_dispatcher_selects_subgroups_for_frequency(self):
        from zarrcurator.dispatcher import Dispatcher
        from zarrcurator.subgroup import SubGroup

        class FakeDistributor:
            frequencySubGroupDict = {
                "P1D": {
                    "1": SubGroup([("/tmp/a.zarr", 1)], "zarr", [], []),
                    "2": SubGroup([("/tmp/b.zarr", 2)], "zarr", [], []),
                }
            }

        d = Dispatcher("base", FakeDistributor())
        d.createTarForFrequencySubGroups("P1D")
        self.assertEqual(len(d.subGroups), 2)
        self.assertEqual(d.subGroupTarNames, ["1", "2"])


class TestDisplayerAndUtils(unittest.TestCase):
    """Displayer and utilities: credentials, Kerchunk step, dispatch with the xarray check."""

    def test_displayer_make_autopct(self):
        from zarrcurator.displayer import Displayer

        fn = Displayer.make_autopct([20, 80])
        pct = fn(50.0)
        self.assertTrue(pct.endswith("%"))

    def test_utils_running_in_jupyter_returns_bool(self):
        from zarrcurator import utils

        value = utils.running_in_jupyter()
        self.assertIsInstance(value, bool)

    def test_utils_initialize_sets_config(self):
        from zarrcurator import utils
        from zarrcurator.config import configObj

        with tempfile.TemporaryDirectory() as tmpdir:
            zarr_dir = Path(tmpdir) / "store.zarr"
            zarr_dir.mkdir()

            utils.initialize(
                expPath=str(zarr_dir),
                workDir=tmpdir,
                jsonFile="out.json",
                targetSize=42,
                batchMode=True,
                debugMode=False,
                packDiscontinuousData=True,
            )

            self.assertEqual(configObj.getZarrStorePath(), str(zarr_dir))
            self.assertEqual(configObj.getWorkingDir(), tmpdir)
            self.assertEqual(configObj.getJsonFile(), "out.json")
            self.assertEqual(configObj.getTargetSize(), 42)

    def test_set_object_store_credentials_with_literal_values(self):
        from zarrcurator import utils
        from zarrcurator.config import configObj

        with mock.patch.dict(os.environ, {}, clear=False):
            utils.setObjectStoreCredentials(accessKey="AK_TEST", secretKey="SK_TEST")

            self.assertEqual(os.environ["AWS_ACCESS_KEY_ID"], "AK_TEST")
            self.assertEqual(os.environ["AWS_SECRET_ACCESS_KEY"], "SK_TEST")
            self.assertEqual(os.environ["S3_ACCESS_KEY_ID"], "AK_TEST")
            self.assertEqual(os.environ["S3_SECRET_ACCESS_KEY"], "SK_TEST")
            self.assertEqual(configObj.getaccessKey(), "AWS_ACCESS_KEY_ID")
            self.assertEqual(configObj.getsecretKey(), "AWS_SECRET_ACCESS_KEY")

    def test_dispatch_store_to_tarstores_supports_disk_and_object_store(self):
        from zarrcurator import utils

        class _FakeDistributor:
            def __init__(self):
                self.frequencySubGroupDict = {"P1D": {}}

        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "subGroupTar.json"
            fake_distributor = _FakeDistributor()

            # Local disk path branch.
            with mock.patch.object(utils, "Dispatcher") as mock_dispatcher_cls, \
                  mock.patch.object(utils.configObj, "getDistributorObj", return_value=fake_distributor), \
                 mock.patch.object(utils.configObj, "setDispatcherObj"), \
                 mock.patch.object(utils, "updateStoretoConfig", return_value=(None, "/tmp/local.zarr", "local.zarr")) as mock_update, \
                 mock.patch.object(utils.configObj, "getZarrStorePath", return_value="/tmp/local.zarr"), \
                 mock.patch.object(utils.configObj, "getWorkingDir", return_value=tmpdir), \
                 mock.patch.object(utils, "xr") as mock_xr:
                mock_dispatcher = mock.Mock()
                mock_dispatcher_cls.return_value = mock_dispatcher
                mock_xr.open_zarr.return_value = mock.Mock(sizes={"cell": 192}, frequency="P1D")

                utils.dispatchStoreToTarStores("/tmp/local.zarr")

                mock_update.assert_called_with("/tmp/local.zarr")
                mock_xr.open_datatree.assert_called_once_with("/tmp/local.zarr", engine="zarr")
                mock_dispatcher.createTarForFrequencySubGroupDict.assert_called_once()
                mock_dispatcher.executor.assert_called_once_with(-1)

            # Object-store branch.
            fake_fs = mock.Mock()
            fake_store = mock.Mock()
            fake_store.store = "mapped-store"

            with mock.patch.object(utils, "Dispatcher") as mock_dispatcher_cls, \
                  mock.patch.object(utils.configObj, "getDistributorObj", return_value=fake_distributor), \
                 mock.patch.object(utils.configObj, "setDispatcherObj"), \
                 mock.patch.object(utils, "updateStoretoConfig", return_value=(fake_fs, fake_store, "remote.zarr")) as mock_update, \
                 mock.patch.object(utils.configObj, "getZarrStorePath", return_value="bucket/remote.zarr"), \
                 mock.patch.object(utils.configObj, "getWorkingDir", return_value=tmpdir), \
                 mock.patch.object(utils, "xr") as mock_xr:
                mock_dispatcher = mock.Mock()
                mock_dispatcher_cls.return_value = mock_dispatcher
                mock_xr.open_zarr.return_value = mock.Mock(sizes={"cell": 768}, frequency="P1D")

                utils.dispatchStoreToTarStores("https://example.org/bucket/remote.zarr")

                mock_update.assert_called_with("https://example.org/bucket/remote.zarr")
                mock_xr.open_datatree.assert_called_once_with("mapped-store", engine="zarr")
                mock_dispatcher.createTarForFrequencySubGroupDict.assert_called_once()
                mock_dispatcher.executor.assert_called_once_with(-1)

            self.assertTrue(output_file.exists())

    def test_create_kerchunk_reference_file_for_tar(self):
        from zarrcurator import utils
        from zarrcurator.config import configObj

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            store_dir = tmp_path / "ngc4008_P1D.zarr"
            var_dir = store_dir / "temp"
            var_dir.mkdir(parents=True)
            chunk_file = var_dir / "0"
            chunk_file.write_bytes(b"abcd")

            tar_path = tmp_path / "ngc4008_P1D_001.tar"
            with tarfile.open(tar_path, "w") as tf:
                tf.add(store_dir, arcname=store_dir.name)

            configObj.setWorkingDir(str(tmp_path))
            utils.createKerchunkReferenceFileForTar(str(tar_path))

            out_json = tmp_path / "ngc4008_P1D_001_Offset_kerchunk.json"
            self.assertTrue(out_json.is_file())

            data = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(data["version"], 1)
            self.assertIn("refs", data)
            self.assertIn("temp/0", data["refs"])

            ref = data["refs"]["temp/0"]
            self.assertEqual(ref[0], f"file://{tar_path}")
            self.assertEqual(ref[2], 4)

    def test_convert_kerchunk_reference_files_to_parquet_from_tar_references(self):
        from zarrcurator import utils
        from zarrcurator.config import configObj

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            configObj.setWorkingDir(str(tmp_path))

            # setZarrStorePath exits for local paths that do not exist.
            (tmp_path / "sample.zarr").mkdir()

            tar_payload = tmp_path / "payload.bin"
            tar_payload.write_bytes(b"0123456789")

            source_json = tmp_path / "sample_P1D_001_Offset_kerchunk.json"
            source_json.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "refs": {
                            "temp/0": [f"{tar_payload}", 0, 10],
                            "temp/0/1": [f"{tar_payload}", 0, 10],
                            "rechunker/temp/1": [f"{tar_payload}", 0, 10],
                            "zero/0": [f"{tar_payload}", 0, 0],
                        },
                    }
                ),
                encoding="utf-8",
            )

            written = []

            def _fake_refs_to_dataframe(fo, url, **kwargs):
                written.append((fo, url, kwargs))

            with mock.patch.object(utils, "ujson", json):
                with mock.patch.object(utils, "refs_to_dataframe", side_effect=_fake_refs_to_dataframe):
                    utils.convertKerchunkReferenceFilesOfZarrStoreToParquet(
                        str(tmp_path / "sample.zarr")
                    )

            copied_json = tmp_path / "sample_P1D_001_Offset_kerchunk.json.copy"
            self.assertTrue(copied_json.is_file())
            copied = json.loads(copied_json.read_text(encoding="utf-8"))

            # clear_dict removes zero-sized and rechunker refs and joins chunk indices with dots.
            self.assertIn("temp/0", copied["refs"])
            self.assertIn("temp/0.1", copied["refs"])
            self.assertNotIn("temp/0/1", copied["refs"])
            self.assertNotIn("rechunker/temp/1", copied["refs"])
            self.assertNotIn("zero/0", copied["refs"])

            # The merged references of the store's tarballs are written as parquet references.
            self.assertEqual(len(written), 1)
            self.assertEqual(written[0][1], str(tmp_path / "sample.parq"))
            self.assertEqual(written[0][0], {"version": 1, "refs": copied["refs"]})
            # URLs are not stored as categoricals, which read missing chunks wrongly.
            self.assertEqual(written[0][2], {"categorical_threshold": sys.maxsize})

    @unittest.skipUnless(fsspec is not None and np is not None and zarr is not None, "requires fsspec, numpy, zarr")
    def test_open_zarr_store_from_kerchunk_json_reference_file(self):
        """Create a tarball-backed JSON reference and open it as a Zarr array."""

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            store_dir = tmp_path / "sample.zarr"
            arr = zarr.open_array(store_dir, mode="w", shape=(4,), chunks=(2,), dtype="i4")
            arr[:] = np.array([1, 2, 3, 4], dtype="i4")

            tar_path = tmp_path / "sample_001.tar"
            with tarfile.open(tar_path, "w") as tf:
                tf.add(store_dir, arcname=store_dir.name)

            refs = {"version": 1, "refs": {}}
            prefix = "sample.zarr/"
            with tarfile.open(tar_path, "r") as tf:
                for tarinfo in tf:
                    ref_key = tarinfo.name
                    if ref_key.startswith(prefix):
                        ref_key = ref_key[len(prefix):]
                    refs["refs"][ref_key] = [
                        f"file://{tar_path}",
                        tarinfo.offset_data,
                        tarinfo.size,
                    ]

            ref_json = tmp_path / "sample_001_Offset_kerchunk.json"
            ref_json.write_text(json.dumps(refs), encoding="utf-8")

            mapper = fsspec.get_mapper(
                "reference://",
                fo=str(ref_json),
                remote_protocol="file",
            )
            reopened = zarr.open_array(mapper, mode="r")
            np.testing.assert_array_equal(reopened[:], np.array([1, 2, 3, 4], dtype="i4"))

    @unittest.skipUnless(fsspec is not None and np is not None and zarr is not None, "requires fsspec, numpy, zarr")
    def test_try_open_zarr_store_from_parquet_reference_file(self):
        """Convert a tarball-backed JSON reference to parquet and open it with xarray."""

        import pandas as pd
        import xarray as xr

        from zarrcurator import utils
        from zarrcurator.config import configObj

        if not hasattr(utils, "refs_to_dataframe"):
            self.skipTest("kerchunk reference components are unavailable")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            configObj.setWorkingDir(str(tmp_path))

            # The references are written in the zarr v2 layout.
            store_dir = tmp_path / "sample.zarr"
            ds = xr.Dataset(
                {"temp": ("time", np.array([9, 8, 7, 6], dtype="i4"))},
                coords={"time": pd.date_range("2020-01-01", periods=4, freq="D")},
            )
            ds.to_zarr(
                store_dir,
                zarr_format=2,
                consolidated=False,
                encoding={"temp": {"chunks": (2,)}, "time": {"chunks": (4,)}},
            )

            tar_path = tmp_path / "sample_001.tar"
            with tarfile.open(tar_path, "w") as tf:
                tf.add(store_dir, arcname=store_dir.name)

            # Build source kerchunk JSON the converter expects.
            refs = {"version": 1, "refs": {}}
            prefix = "sample.zarr/"
            with tarfile.open(tar_path, "r") as tf:
                for tarinfo in tf:
                    ref_key = tarinfo.name
                    if ref_key.startswith(prefix):
                        ref_key = ref_key[len(prefix):]
                    refs["refs"][ref_key] = [
                        f"file://{tar_path}",
                        tarinfo.offset_data,
                        tarinfo.size,
                    ]

            src_json = tmp_path / "sample_001_Offset_kerchunk.json"
            src_json.write_text(json.dumps(refs), encoding="utf-8")

            utils.convertKerchunkReferenceFilesOfZarrStoreToParquet(str(store_dir))

            parq_target = tmp_path / "sample.parq"
            self.assertTrue(parq_target.exists())

            mapper = fsspec.get_mapper(
                "reference://",
                fo=str(parq_target),
                remote_protocol="file",
            )
            reopened = xr.open_dataset(mapper, engine="zarr", consolidated=False, zarr_format=2)

            np.testing.assert_array_equal(reopened["temp"].values, np.array([9, 8, 7, 6], dtype="i4"))
            np.testing.assert_array_equal(reopened["time"].values, ds["time"].values)

    def test_set_object_store_credentials_with_env_var_names(self):
        from zarrcurator import utils

        with mock.patch.dict(
            os.environ,
            {"MY_ACCESS_ENV": "AK_FROM_ENV", "MY_SECRET_ENV": "SK_FROM_ENV"},
            clear=False,
        ):
            utils.setObjectStoreCredentials(
                accessKey="MY_ACCESS_ENV",
                secretKey="MY_SECRET_ENV",
            )

            self.assertEqual(os.environ["AWS_ACCESS_KEY_ID"], "AK_FROM_ENV")
            self.assertEqual(os.environ["AWS_SECRET_ACCESS_KEY"], "SK_FROM_ENV")

    def test_set_object_store_credentials_requires_both_values(self):
        from zarrcurator import utils

        with self.assertRaises(ValueError):
            utils.setObjectStoreCredentials(accessKey="ONLY_ACCESS", secretKey=None)

        with self.assertRaises(ValueError):
            utils.setObjectStoreCredentials(accessKey=None, secretKey="ONLY_SECRET")

    def test_utils_initialize_sets_credentials_when_provided(self):
        from zarrcurator import utils

        with tempfile.TemporaryDirectory() as tmpdir:
            zarr_dir = Path(tmpdir) / "store.zarr"
            zarr_dir.mkdir()

            with mock.patch.dict(os.environ, {}, clear=False):
                utils.initialize(
                    expPath=str(zarr_dir),
                    workDir=tmpdir,
                    jsonFile="out.json",
                    targetSize=42,
                    batchMode=True,
                    debugMode=False,
                    packDiscontinuousData=True,
                    accessKey="AK_INIT",
                    secretKey="SK_INIT",
                )

                self.assertEqual(os.environ["AWS_ACCESS_KEY_ID"], "AK_INIT")
                self.assertEqual(os.environ["AWS_SECRET_ACCESS_KEY"], "SK_INIT")


class TestSideEffectHeavyModules(unittest.TestCase):
    """Modules with side effects on import, checked from their source."""

    def _extract_function(self, module_path: Path, func_name: str, globals_dict=None):
        src = module_path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        node = None
        for n in tree.body:
            if isinstance(n, ast.FunctionDef) and n.name == func_name:
                node = n
                break
        self.assertIsNotNone(node, f"Function {func_name} not found")

        module = ast.Module(body=[node], type_ignores=[])
        module = ast.fix_missing_locations(module)

        env = {} if globals_dict is None else dict(globals_dict)
        exec(compile(module, str(module_path), "exec"), env)
        return env[func_name]

    def test_ocean_vars_yaml_source_has_expected_pipeline(self):
        src = (PACKAGE_DIR / "oceanVarsYAML.py").read_text(encoding="utf-8")
        self.assertIn("np.genfromtxt", src)
        self.assertIn("yaml.safe_dump", src)
        self.assertIn("ocean_variable_list.yaml", src)


@unittest.skipUnless(np is not None and zarr is not None, "requires numpy, zarr")
class TestChunkKeySeparators(unittest.TestCase):
    """Chunk keys separated by '.' (e.g. 0.1) and '/' (e.g. 0/1) for zarr v2 and v3."""

    # (zarr_format, separator) -> chunk key of chunk (0, 1) relative to the variable.
    LAYOUTS = {
        (2, "."): "0.1",
        (2, "/"): "0/1",
        (3, "/"): "c/0/1",
        (3, "."): "c.0.1",
    }

    @staticmethod
    def _make_store(store_dir, zarr_format, separator, shape=(4, 6), chunks=(2, 2)):
        name = "v2" if zarr_format == 2 else "default"
        group = zarr.open_group(str(store_dir), mode="w", zarr_format=zarr_format)
        arr = group.create_array(
            "temp",
            shape=shape,
            chunks=chunks,
            dtype="i4",
            chunk_key_encoding={"name": name, "separator": separator},
        )
        arr[:] = np.arange(math.prod(shape), dtype="i4").reshape(shape)
        return arr

    @staticmethod
    def _chunk_key(zarr_format, separator, *coord):
        key = separator.join(str(c) for c in coord)
        if zarr_format == 3:
            key = f"c{separator}{key}"
        return key

    @staticmethod
    def _var_files(var_dir):
        return {
            os.path.relpath(os.path.join(root, f), var_dir)
            for root, _, files in os.walk(var_dir)
            for f in files
        }

    def test_store_layouts_use_expected_chunk_keys(self):
        for (zarr_format, separator), key in self.LAYOUTS.items():
            with self.subTest(zarr_format=zarr_format, separator=separator):
                with tempfile.TemporaryDirectory() as tmpdir:
                    store_dir = Path(tmpdir) / "sample.zarr"
                    self._make_store(store_dir, zarr_format, separator)
                    self.assertIn(key, self._var_files(store_dir / "temp"))
                    self.assertEqual(self._chunk_key(zarr_format, separator, 0, 1), key)

    def test_num_threads_scale_with_number_of_chunks(self):
        from zarrcurator import chunkkeys
        from zarrcurator.utils import numThreadsForChunks

        env = {k: v for k, v in os.environ.items() if k != chunkkeys.ENV_MAX_THREADS}
        # With many CPUs available, the number of chunks decides.
        with mock.patch.object(chunkkeys, "availableCpus", return_value=256), mock.patch.dict(os.environ, env, clear=True):
            for num_chunks, expected in [(0, 1), (199, 1), (200, 10), (499, 10),
                                         (500, 40), (999, 40), (1000, 100), (10**6, 100)]:
                with self.subTest(num_chunks=num_chunks):
                    self.assertEqual(numThreadsForChunks(num_chunks), expected)
                    self.assertEqual(numThreadsForChunks(num_chunks, ioBound=False), expected)

    def test_num_threads_are_capped_by_available_cpus(self):
        from zarrcurator import chunkkeys

        env = {k: v for k, v in os.environ.items() if k != chunkkeys.ENV_MAX_THREADS}
        with mock.patch.dict(os.environ, env, clear=True):
            # e.g. a SLURM job with 8 CPUs: 4 threads per CPU for I/O-bound, 1 per CPU for CPU-bound work
            with mock.patch.object(chunkkeys, "availableCpus", return_value=8):
                self.assertEqual(chunkkeys.numThreadsForChunks(10**6), 32)
                self.assertEqual(chunkkeys.numThreadsForChunks(10**6, ioBound=False), 8)
                self.assertEqual(chunkkeys.numThreadsForChunks(300), 10)
                self.assertEqual(chunkkeys.numThreadsForChunks(300, ioBound=False), 8)
                self.assertEqual(chunkkeys.numThreadsForChunks(10), 1)
            with mock.patch.object(chunkkeys, "availableCpus", return_value=1):
                self.assertEqual(chunkkeys.numThreadsForChunks(10**6, ioBound=False), 1)
            # The environment variable overrides the CPU based cap, for all work.
            with mock.patch.object(chunkkeys, "availableCpus", return_value=8), \
                 mock.patch.dict(os.environ, {chunkkeys.ENV_MAX_THREADS: "16"}):
                self.assertEqual(chunkkeys.numThreadsForChunks(10**6), 16)
                self.assertEqual(chunkkeys.numThreadsForChunks(10**6, ioBound=False), 16)
                self.assertEqual(chunkkeys.numThreadsForChunks(300), 10)
            for bad in ("0", "-3", "many"):
                with self.subTest(value=bad), mock.patch.object(chunkkeys, "availableCpus", return_value=8), \
                     mock.patch.dict(os.environ, {chunkkeys.ENV_MAX_THREADS: bad}), \
                     self.assertLogs("zarrcurator.chunkkeys", "WARNING"):
                    self.assertEqual(chunkkeys.maxThreads(ioBound=False), 8)
        # The CPUs this process may run on, e.g. those of a SLURM allocation.
        self.assertEqual(chunkkeys.availableCpus(), len(os.sched_getaffinity(0)))

    def test_find_missing_chunks_in_store_handles_separators(self):
        from zarrcurator import utils

        for flag in ("0", "1"):
            for zarr_format, separator in self.LAYOUTS:
                with self.subTest(multithread=flag, zarr_format=zarr_format, separator=separator), \
                     tempfile.TemporaryDirectory() as tmpdir, \
                     mock.patch.dict(os.environ, {"ZARRCURATOR_MULTITHREAD": flag}):
                    tmp_path = Path(tmpdir)
                    store_dir = tmp_path / "sample.zarr"
                    self._make_store(store_dir, zarr_format, separator)
                    var_dir = store_dir / "temp"

                    missing_key = self._chunk_key(zarr_format, separator, 0, 0)
                    zero_key = self._chunk_key(zarr_format, separator, 0, 1)
                    corrupt_key = self._chunk_key(zarr_format, separator, 1, 2)
                    (var_dir / missing_key).unlink()
                    (var_dir / zero_key).write_bytes(b"")
                    (var_dir / corrupt_key).write_bytes(b"not-a-chunk")
                    (var_dir / "stray.txt").write_bytes(b"x")

                    old_cwd = os.getcwd()
                    try:
                        os.chdir(tmpdir)
                        with redirect_stdout(io.StringIO()):
                            utils.findMissingChunksInStore(str(store_dir))
                    finally:
                        os.chdir(old_cwd)

                    report = utils.flattenCheckReport(
                        json.loads((tmp_path / "sample.check").read_text(encoding="utf-8"))
                    )["/temp"]
                    self.assertEqual(report["expected_chunks"], 6)
                    # Missing chunks are reported as normalized dot-separated coordinates.
                    self.assertEqual(report["missing"], ["0.0"])
                    self.assertEqual(report["zero_size"], [zero_key])
                    self.assertEqual(report["unexpected"], ["stray.txt"])
                    # A zero-size chunk is unreadable too, so it is also reported as corrupt.
                    self.assertEqual(sorted(report["corrupt"]), sorted([zero_key, corrupt_key]))

    def test_diagnoser_counts_chunks_for_separators(self):
        from zarrcurator.diagnoser import Diagnoser

        for flag in ("0", "1"):
            for zarr_format, separator in self.LAYOUTS:
                with self.subTest(multithread=flag, zarr_format=zarr_format, separator=separator), \
                     tempfile.TemporaryDirectory() as tmpdir, \
                     mock.patch.dict(os.environ, {"ZARRCURATOR_MULTITHREAD": flag}):
                    store_dir = Path(tmpdir) / "sample.zarr"
                    self._make_store(store_dir, zarr_format, separator)
                    var_dir = store_dir / "temp"
                    zero_key = self._chunk_key(zarr_format, separator, 0, 1)
                    (var_dir / zero_key).write_bytes(b"")

                    files = self._var_files(var_dir)
                    expected_size = sum((var_dir / f).stat().st_size for f in files)

                    store = str(store_dir)
                    diagnoser = Diagnoser.__new__(Diagnoser)
                    diagnoser.fileSystemObj = None
                    diagnoser.exp_size_dict = {}
                    diagnoser.zeroSizeFilesDict = {store.split(".")[0]: []}
                    diagnoser.zeroSizeFilesFlag = False

                    diagnoser.diagnose_zarr(store)

                    temp = diagnoser.exp_size_dict[store]["temp"]
                    # All chunk files, including nested '/' ones, plus the array metadata.
                    self.assertEqual(temp["count"], len(files))
                    self.assertEqual(temp["size"], expected_size)
                    self.assertTrue(diagnoser.zeroSizeFilesFlag)
                    self.assertIn(str(var_dir / zero_key), diagnoser.zeroSizeFilesDict[store.split(".")[0]])

    def test_diag_report_is_nested_by_group(self):
        """The '.diag' file is nested by group; older flat files still load."""

        from zarrcurator.config import configObj
        from zarrcurator.diagnoser import Diagnoser
        from zarrcurator.storetree import flattenDiagReport, nestDiagReport

        flat = {"/tmp/tree.zarr": {
            "zarr.json": {"size": 5, "count": 1, "time": 0.0},
            "tas": {"size": 10, "count": 3, "time": 0.1},
            "z2/zarr.json": {"size": 2, "count": 1, "time": 0.0},
            "z2/ocean/sst": {"size": 20, "count": 4, "time": 0.2},
            "size": 37, "count": 9,
        }}
        nested = nestDiagReport(flat)
        store = nested["/tmp/tree.zarr"]
        self.assertEqual((store["size"], store["count"]), (37, 9))
        self.assertEqual(store["tas"]["type"], "array")
        self.assertEqual(store["zarr.json"]["type"], "file")
        self.assertEqual(store["z2"]["zarr.json"]["path"], "z2/zarr.json")
        self.assertEqual(store["z2"]["ocean"]["sst"],
                         {"type": "array", "path": "z2/ocean/sst", "size": 20, "count": 4, "time": 0.2})
        # Group totals include the metadata files and sub groups
        self.assertEqual(store["z2"]["__total__"], {"size": 22, "count": 5})
        self.assertEqual(store["z2"]["ocean"]["__total__"], {"size": 20, "count": 4})
        self.assertEqual(next(iter(store["z2"])), "__total__")
        self.assertNotIn("__total__", store)
        self.assertEqual(flattenDiagReport(nested), flat)
        self.assertEqual(flattenDiagReport(flat), flat)

        # Diagnoser.update loads both formats into the flat dictionary
        for report in (nested, flat):
            with self.subTest(nested=report is nested), tempfile.TemporaryDirectory() as tmpdir:
                (Path(tmpdir) / "tree.diag").write_text(json.dumps(report), encoding="utf-8")
                diagnoser = Diagnoser.__new__(Diagnoser)
                diagnoser.outputDir = tmpdir
                with mock.patch.object(configObj, "getZarrStorePath", return_value="/tmp/tree.zarr"), \
                     mock.patch.object(configObj, "getWorkingDir", return_value=tmpdir), \
                     redirect_stdout(io.StringIO()):
                    self.assertIsNone(diagnoser.update())
                self.assertEqual(diagnoser.exp_size_dict, flat)

    def test_sunburst_follows_group_hierarchy(self):
        """The sunburst plot nests arrays under their groups, for nested and flat '.diag' files."""

        import plotly.graph_objects as go

        from zarrcurator import utils
        from zarrcurator.storetree import nestDiagReport

        flat = {"/tmp/tree.zarr": {
            "zarr.json": {"size": 5, "count": 1},
            "z1/tas": {"size": 10, "count": 3},
            "z2/tas": {"size": 20, "count": 4},
            "z2/zarr.json": {"size": 2, "count": 1},
            "size": 37, "count": 9,
        }}
        for report in (nestDiagReport(flat), flat):
            with self.subTest(nested=report is not flat), tempfile.TemporaryDirectory() as tmpdir:
                (Path(tmpdir) / "tree.diag").write_text(json.dumps(report), encoding="utf-8")
                shown = []
                with mock.patch.object(utils, "updateStoretoConfig", return_value=(None, None, "tree.zarr")), \
                     mock.patch.object(utils.configObj, "getWorkingDir", return_value=tmpdir), \
                     mock.patch.object(go.Figure, "show", lambda fig, *a, **k: shown.append(fig)), \
                     redirect_stdout(io.StringIO()):
                    utils.displayStoreSunburst("/tmp/tree.zarr")

                trace = shown[0].data[0]
                nodes = {i: (label, parent, value) for i, label, parent, value
                         in zip(trace.ids, trace.labels, trace.parents, trace.values)}
                self.assertEqual(nodes["/tmp/tree.zarr"], ("tree.zarr", "", 37))
                self.assertEqual(nodes["/tmp/tree.zarr/z2"], ("z2", "/tmp/tree.zarr", 22))
                # Arrays with the same name in different groups are different nodes
                self.assertEqual(nodes["/tmp/tree.zarr/z1/tas"], ("tas", "/tmp/tree.zarr/z1", 10))
                self.assertEqual(nodes["/tmp/tree.zarr/z2/tas"], ("tas", "/tmp/tree.zarr/z2", 20))

    def test_diagnoser_accepts_group_of_store_as_input(self):
        """A group inside a store, e.g. 'tree.zarr/atmos', is diagnosed as a single store."""

        from zarrcurator.config import configObj
        from zarrcurator.diagnoser import Diagnoser

        for zarr_format in (2, 3):
            with self.subTest(zarr_format=zarr_format), tempfile.TemporaryDirectory() as tmpdir, \
                 mock.patch.object(configObj, "getFileSystemObj", return_value=None):
                root = zarr.open_group(str(Path(tmpdir) / "tree.zarr"), mode="w", zarr_format=zarr_format)
                group_path = str(Path(tmpdir) / "tree.zarr" / "atmos")
                arr = root.create_group("atmos").create_group("zoom_0").create_array(
                    "tas", shape=(4,), chunks=(2,), dtype="i4"
                )
                arr[:] = np.arange(4, dtype="i4")

                configObj.setZarrStorePath(group_path + os.path.sep)
                diagnoser = Diagnoser()
                self.assertEqual(diagnoser.list_of_zarrs, [group_path])

                diagnoser.diagnose_zarr(group_path)
                # 2 chunks plus .zarray and .zattrs (v2) or zarr.json (v3)
                expected_count = 4 if zarr_format == 2 else 3
                self.assertEqual(diagnoser.exp_size_dict[group_path]["zoom_0/tas"]["count"], expected_count)

    def test_kerchunk_parquet_roundtrip_handles_v2_separators(self):
        """Kerchunk combines zarr v2 references, so both v2 separators must round-trip."""

        import pandas as pd
        import xarray as xr

        from zarrcurator import utils
        from zarrcurator.config import configObj

        values = np.arange(24, dtype="i4").reshape(4, 6)
        for separator in (".", "/"):
            with self.subTest(separator=separator), tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                configObj.setWorkingDir(str(tmp_path))

                store_dir = tmp_path / "sample.zarr"
                ds = xr.Dataset(
                    {"temp": (("time", "cell"), values)},
                    coords={"time": pd.date_range("2020-01-01", periods=4, freq="D")},
                )
                ds.to_zarr(
                    store_dir,
                    zarr_format=2,
                    consolidated=False,
                    encoding={
                        "temp": {
                            "chunks": (2, 2),
                            "chunk_key_encoding": {"name": "v2", "separator": separator},
                        },
                        "time": {"chunks": (4,)},
                    },
                )
                self.assertIn(f"0{separator}1", self._var_files(store_dir / "temp"))

                tar_path = tmp_path / "sample_001.tar"
                with tarfile.open(tar_path, "w") as tf:
                    tf.add(store_dir, arcname=store_dir.name)

                with redirect_stdout(io.StringIO()):
                    utils.createKerchunkReferenceFileForTar(str(tar_path))
                    utils.convertKerchunkReferenceFilesOfZarrStoreToParquet(str(store_dir))

                # Nested '/' chunk keys are rewritten to the dot-separated v2 form.
                copied = json.loads(
                    (tmp_path / "sample_001_Offset_kerchunk.json.copy").read_text(encoding="utf-8")
                )
                self.assertIn("temp/0.1", copied["refs"])
                self.assertNotIn("temp/0/1", copied["refs"])
                zarray = json.loads(copied["refs"]["temp/.zarray"])
                self.assertEqual(zarray.get("dimension_separator", "."), ".")

                mapper = fsspec.get_mapper(
                    "reference://",
                    fo=str(tmp_path / "sample.parq"),
                    remote_protocol="file",
                )
                reopened = xr.open_dataset(mapper, engine="zarr", consolidated=False, zarr_format=2)
                np.testing.assert_array_equal(reopened["temp"].values, values)

    def _assert_create_tar_for_chunk_splits_by_first_axis(self, zarr_format, separator):
        from types import SimpleNamespace

        from zarrcurator.config import configObj
        from zarrcurator.dispatcher import Dispatcher
        from zarrcurator.subgroup import SubGroup

        gib = 1024 * 1024 * 1024
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            store_dir = tmp_path / "sample_P1D_0.zarr"
            arr = self._make_store(store_dir, zarr_format, separator, shape=(4, 6), chunks=(1, 2))
            configObj.setZarrStorePath(str(store_dir))
            configObj.setWorkingDir(tmpdir)

            dispatcher = Dispatcher(None, SimpleNamespace(targetSize=gib, frequencySubGroupDict={}))
            # Twice the target size forces the chunks into two tarballs.
            sub_group = SubGroup([("temp", 2 * gib)], "chunk", [], [])
            dispatcher.createTarForChunk(sub_group, "sample_P1D_0_temp")

            self.assertEqual(len(sub_group.groupTarMembers), 2)
            var_meta = "temp/.zarray" if zarr_format == 2 else "temp/zarr.json"
            chunk_prefix = "temp/"
            rows_per_tar = []
            tarred_chunks = []
            for tar_name in sub_group.groupTarMembers:
                with tarfile.open(tar_name) as tf:
                    names = [m.name for m in tf.getmembers() if m.isfile()]
                self.assertIn(var_meta, names)
                chunks = [
                    n[len(chunk_prefix):]
                    for n in names
                    if n.startswith(chunk_prefix) and n != var_meta and not n.startswith("temp/.z")
                ]
                tarred_chunks.extend(chunks)
                rows = set()
                for chunk in chunks:
                    parts = chunk.replace(".", "/").split("/")
                    rows.add(int(parts[1] if parts[0] == "c" else parts[0]))
                rows_per_tar.append(rows)

            expected_chunks = [
                self._chunk_key(zarr_format, separator, i, j)
                for i in range(4)
                for j in range(3)
            ]
            # Every chunk is archived exactly once.
            self.assertEqual(sorted(tarred_chunks), sorted(expected_chunks))
            # Chunks are split along the first axis: whole rows, no row in two tarballs.
            self.assertEqual(rows_per_tar, [{0, 1, 2}, {3}])

            # Extracting all tarballs restores a readable store with the original values.
            restored = tmp_path / "restored"
            for tar_name in sub_group.groupTarMembers:
                with tarfile.open(tar_name) as tf:
                    tf.extractall(restored, filter="data")
            reopened = zarr.open_group(str(restored), mode="r", zarr_format=zarr_format)
            np.testing.assert_array_equal(reopened["temp"][:], arr[:])

    def test_create_tar_for_chunk_v2_dot_separator(self):
        self._assert_create_tar_for_chunk_splits_by_first_axis(2, ".")

    def test_create_tar_for_chunk_v2_slash_separator(self):
        self._assert_create_tar_for_chunk_splits_by_first_axis(2, "/")

    def test_create_tar_for_chunk_v3_slash_separator(self):
        self._assert_create_tar_for_chunk_splits_by_first_axis(3, "/")

    def test_create_tar_for_chunk_v3_dot_separator(self):
        self._assert_create_tar_for_chunk_splits_by_first_axis(3, ".")

    def test_create_tar_for_chunk_with_missing_first_axis_row(self):
        from types import SimpleNamespace

        from zarrcurator.chunkkeys import parseChunkKey
        from zarrcurator.config import configObj
        from zarrcurator.dispatcher import Dispatcher
        from zarrcurator.subgroup import SubGroup

        gib = 1024 * 1024 * 1024
        for zarr_format, separator in self.LAYOUTS:
            for pack in (False, True):
                with self.subTest(zarr_format=zarr_format, separator=separator, pack=pack), \
                     tempfile.TemporaryDirectory() as tmpdir, \
                     mock.patch.object(configObj, "getPackDiscontinuousData", return_value=pack):
                    store_dir = Path(tmpdir) / "sample_P1D_0.zarr"
                    self._make_store(store_dir, zarr_format, separator, shape=(4, 6), chunks=(1, 2))
                    # Remove first-axis row 1, leaving the discontinuous rows 0, 2 and 3.
                    for j in range(3):
                        (store_dir / "temp" / self._chunk_key(zarr_format, separator, 1, j)).unlink()
                    configObj.setZarrStorePath(str(store_dir))
                    configObj.setWorkingDir(tmpdir)

                    dispatcher = Dispatcher(None, SimpleNamespace(targetSize=gib, frequencySubGroupDict={}))
                    sub_group = SubGroup([("temp", 2 * gib)], "chunk", [], [])
                    dispatcher.createTarForChunk(sub_group, "sample_P1D_0_temp")

                    if not pack:
                        # Discontinuous variables are skipped unless packing them is enabled.
                        self.assertEqual(sub_group.groupTarMembers, [])
                        continue

                    tarred_chunks = []
                    for tar_name in sub_group.groupTarMembers:
                        with tarfile.open(tar_name) as tf:
                            tarred_chunks.extend(
                                m.name[len("temp/"):]
                                for m in tf.getmembers()
                                if m.isfile() and m.name.startswith("temp/") and parseChunkKey(m.name[len("temp/"):])
                            )
                    expected = [
                        self._chunk_key(zarr_format, separator, i, j)
                        for i in (0, 2, 3)
                        for j in range(3)
                    ]
                    self.assertEqual(sorted(tarred_chunks), sorted(expected))

    def test_parse_chunk_key_supports_all_separators(self):
        from zarrcurator.chunkkeys import parseChunkKey

        for key in ("0.1", "0/1", "c/0/1", "c.0.1"):
            with self.subTest(key=key):
                self.assertEqual(parseChunkKey(key), (0, 1))
        self.assertEqual(parseChunkKey("7"), (7,))
        for key in (".zarray", "zarr.json", "stray.txt", "c"):
            with self.subTest(key=key):
                self.assertIsNone(parseChunkKey(key))


@unittest.skipUnless(np is not None and zarr is not None, "requires numpy, zarr")
class TestCoordinateVariablesInTarballs(unittest.TestCase):
    """Coordinate variables of the store are added to 'var' and 'chunk' tarballs."""

    GIB = 1024 * 1024 * 1024
    COORDS = ["cell", "crs", "lat", "lon", "time"]

    @staticmethod
    def _make_healpix_store(store_dir, zarr_format, with_cell_coordinate=True):
        import pandas as pd
        import xarray as xr

        nt, ncell = 8, 48
        rng = np.random.default_rng(0)
        ds = xr.Dataset(
            {
                "tas": (("time", "cell"), rng.random((nt, ncell)), {"grid_mapping": "crs"}),
                "orog": (("cell",), rng.random(ncell).astype("f4"), {"grid_mapping": "crs"}),
            },
            coords={
                "time": pd.date_range("2020-01-01", periods=nt, freq="D"),
                "lat": ("cell", np.linspace(-90, 90, ncell)),
                "lon": ("cell", np.linspace(0, 360, ncell)),
                "crs": ((), 0, {"grid_mapping_name": "healpix", "healpix_nside": 2}),
            },
        )
        if with_cell_coordinate:
            ds = ds.assign_coords(cell=np.arange(ncell))
        ds.to_zarr(
            store_dir,
            zarr_format=zarr_format,
            consolidated=False,
            encoding={"tas": {"chunks": (2, ncell)}},
        )
        return ds

    @staticmethod
    def _diagnose(store):
        from zarrcurator.diagnoser import Diagnoser

        diagnoser = Diagnoser.__new__(Diagnoser)
        diagnoser.fileSystemObj = None
        diagnoser.exp_size_dict = {}
        diagnoser.zeroSizeFilesDict = {store.split(".")[0]: []}
        diagnoser.zeroSizeFilesFlag = False
        diagnoser.diagnose_zarr(store)
        return diagnoser

    def _distributor(self, store, sub_groups):
        from zarrcurator.config import configObj
        from zarrcurator.distributor import Distributor

        distributor = Distributor.__new__(Distributor)
        distributor.diagnoserObj = self._diagnose(store)
        distributor.frequencySubGroupDict = {"P1D": sub_groups}
        with mock.patch.object(configObj, "getZarrStorePath", return_value=store), \
             mock.patch.object(configObj, "getFileSystemObj", return_value=None), \
             redirect_stdout(io.StringIO()):
            distributor.updateDimensionsToSubGroups()
        return distributor

    def test_get_zarrstore_dimensions_finds_coordinate_variables(self):
        from zarrcurator.config import configObj

        for zarr_format in (2, 3):
            for with_cell in (True, False):
                with self.subTest(zarr_format=zarr_format, with_cell=with_cell), tempfile.TemporaryDirectory() as tmpdir:
                    store = str(Path(tmpdir) / "hp_P1D_z1.zarr")
                    self._make_healpix_store(store, zarr_format, with_cell_coordinate=with_cell)
                    distributor = self._distributor(store, {})

                    with mock.patch.object(configObj, "getFileSystemObj", return_value=None):
                        coords = distributor.getZarrstoreDimensions("P1D", store)

                    # Dimension coordinates (cell, time), auxiliary coordinates (lat, lon) and the
                    # grid mapping (crs); 'cell' is only added when the store has a 'cell' array.
                    expected = self.COORDS if with_cell else [c for c in self.COORDS if c != "cell"]
                    self.assertEqual([os.path.basename(path) for path, _ in coords], expected)
                    sizes = distributor.diagnoserObj.exp_size_dict[store]
                    for path, size in coords:
                        self.assertEqual(path, os.path.join(store, os.path.basename(path)))
                        self.assertEqual(size, sizes[os.path.basename(path)]["size"])

    def test_get_zarrstore_dimensions_handles_arrays_without_dimension_names(self):
        from zarrcurator.config import configObj

        for zarr_format in (2, 3):
            with self.subTest(zarr_format=zarr_format), tempfile.TemporaryDirectory() as tmpdir:
                # Only the data variable carries dimension names, the coordinate arrays themselves do not.
                store = str(Path(tmpdir) / "plain_P1D_z1.zarr")
                group = zarr.open_group(store, mode="w", zarr_format=zarr_format)
                for name, size in (("time", 4), ("lat", 3), ("lon", 5)):
                    group.create_array(name, shape=(size,), chunks=(size,), dtype="f4")[:] = 0
                dims = ["time", "lat", "lon"]
                kwargs = {"dimension_names": dims} if zarr_format == 3 else {}
                temp = group.create_array("temp", shape=(4, 3, 5), chunks=(2, 3, 5), dtype="f4", **kwargs)
                temp[:] = 1
                if zarr_format == 2:
                    temp.attrs["_ARRAY_DIMENSIONS"] = dims
                distributor = self._distributor(store, {})
                with mock.patch.object(configObj, "getFileSystemObj", return_value=None):
                    coords = distributor.getZarrstoreDimensions("P1D", store)
                self.assertEqual([os.path.basename(path) for path, _ in coords], ["lat", "lon", "time"])

    def test_update_dimensions_to_subgroups_does_not_duplicate_members(self):
        from zarrcurator.subgroup import SubGroup

        with tempfile.TemporaryDirectory() as tmpdir:
            store = str(Path(tmpdir) / "hp_P1D_z1.zarr")
            self._make_healpix_store(store, 2)
            sizes = self._diagnose(store).exp_size_dict[store]

            # The var subgroup already holds 'time' by variable name.
            var_group = SubGroup([("orog", sizes["orog"]["size"]), ("time", sizes["time"]["size"])], "var", [], [])
            chunk_group = SubGroup([("tas", 2 * self.GIB)], "chunk", [], [])
            distributor = self._distributor(store, {"1": var_group, "2": chunk_group})

            # Running it twice must not add the coordinate variables again.
            from zarrcurator.config import configObj

            with mock.patch.object(configObj, "getZarrStorePath", return_value=store), \
                 mock.patch.object(configObj, "getFileSystemObj", return_value=None), \
                 redirect_stdout(io.StringIO()):
                distributor.updateDimensionsToSubGroups()

            var_names = [os.path.basename(m[0]) for m in var_group.groupMembers]
            self.assertEqual(sorted(var_names), sorted(["orog"] + self.COORDS))
            chunk_names = [os.path.basename(m[0]) for m in chunk_group.groupMembers]
            self.assertEqual(chunk_names, ["tas"] + self.COORDS)
            expected_var_size = sum(sizes[name]["size"] for name in var_names)
            self.assertEqual(var_group.groupSize, expected_var_size)

    def _assert_tarballs_open_with_coordinates(self, tar_names, tmp_path, ds, data_var):
        import xarray as xr

        self.assertTrue(tar_names)
        for index, tar_name in enumerate(tar_names):
            restored = tmp_path / f"restored_{data_var}_{index}"
            with tarfile.open(tar_name) as tf:
                tf.extractall(restored, filter="data")
            reopened = xr.open_zarr(restored, consolidated=False)
            self.assertEqual(sorted(reopened.coords), self.COORDS)
            self.assertEqual(list(reopened.data_vars), [data_var])
            np.testing.assert_array_equal(reopened["lat"].values, ds["lat"].values)
            np.testing.assert_array_equal(reopened["time"].values, ds["time"].values)

    def test_create_tar_for_var_and_chunk_include_coordinate_variables(self):
        from types import SimpleNamespace

        from zarrcurator.config import configObj
        from zarrcurator.dispatcher import Dispatcher
        from zarrcurator.subgroup import SubGroup

        for zarr_format in (2, 3):
            with self.subTest(zarr_format=zarr_format), tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                store = str(tmp_path / "hp_P1D_z1.zarr")
                ds = self._make_healpix_store(store, zarr_format)
                sizes = self._diagnose(store).exp_size_dict[store]

                var_group = SubGroup([("orog", sizes["orog"]["size"])], "var", [], [])
                # Twice the target size forces the chunks into two tarballs.
                chunk_group = SubGroup([("tas", 2 * self.GIB)], "chunk", [], [])
                self._distributor(store, {"1": var_group, "2": chunk_group})

                configObj.setZarrStorePath(store)
                configObj.setWorkingDir(tmpdir)
                dispatcher = Dispatcher(None, SimpleNamespace(targetSize=self.GIB, frequencySubGroupDict={}))
                dispatcher.createTarForVar(var_group, "hp_P1D_z1_1")
                dispatcher.createTarForChunk(chunk_group, "hp_P1D_z1_2")

                self.assertEqual(len(chunk_group.groupTarMembers), 2)
                self._assert_tarballs_open_with_coordinates(var_group.groupTarMembers, tmp_path, ds, "orog")
                self._assert_tarballs_open_with_coordinates(chunk_group.groupTarMembers, tmp_path, ds, "tas")


@unittest.skipUnless(np is not None and zarr is not None, "requires numpy, zarr")
class TestDataTreeStores(unittest.TestCase):
    """Stores with nested groups, as written from an xarray DataTree, for all chunk key layouts."""

    GIB = 1024 * 1024 * 1024
    GROUPS = ["", "z1", "z2", "z2/ocean"]
    ARRAYS = ["time", "z1/cell", "z1/tas", "z2/cell", "z2/ocean/sst", "z2/tas"]

    @staticmethod
    def _make_tree(store_dir, zarr_format, separator, consolidated=False):
        import pandas as pd
        import xarray as xr

        def data(ncell):
            return np.arange(4 * ncell, dtype="f4").reshape(4, ncell)

        # '/z2/ocean' uses 'time' from the root and 'cell' from '/z2'.
        tree = xr.DataTree.from_dict(
            {
                "/": xr.Dataset(coords={"time": pd.date_range("2020-01-01", periods=4, freq="D")}),
                "/z1": xr.Dataset({"tas": (("time", "cell"), data(4))}, coords={"cell": np.arange(4)}),
                "/z2": xr.Dataset({"tas": (("time", "cell"), data(8))}, coords={"cell": np.arange(8)}),
                "/z2/ocean": xr.Dataset({"sst": (("time", "cell"), data(8) + 1)}),
            }
        )
        key_encoding = {"name": "v2" if zarr_format == 2 else "default", "separator": separator}
        encoding = {
            "/z1": {"tas": {"chunks": (1, 4), "chunk_key_encoding": key_encoding}},
            "/z2": {"tas": {"chunks": (1, 4), "chunk_key_encoding": key_encoding}},
            "/z2/ocean": {"sst": {"chunks": (1, 4), "chunk_key_encoding": key_encoding}},
        }
        tree.to_zarr(store_dir, zarr_format=zarr_format, consolidated=consolidated, encoding=encoding)
        return tree

    @staticmethod
    def _store_files(store_dir):
        return {
            os.path.relpath(os.path.join(root, f), store_dir): os.path.getsize(os.path.join(root, f))
            for root, _, files in os.walk(store_dir)
            for f in files
        }

    def _for_each_layout(self, check):
        """Run check(zarr_format, separator, tmp_path, store_dir, tree) on a tree store of each layout."""
        for zarr_format, separator in TestChunkKeySeparators.LAYOUTS:
            with self.subTest(zarr_format=zarr_format, separator=separator), tempfile.TemporaryDirectory() as tmpdir:
                store_dir = Path(tmpdir) / "hp_P1D_z1.zarr"
                tree = self._make_tree(store_dir, zarr_format, separator)
                check(zarr_format, separator, Path(tmpdir), store_dir, tree)

    def test_store_tree_helpers(self):
        from zarrcurator.storetree import groupAncestors, isZarrGroupDir, listArrayPaths

        self.assertEqual(groupAncestors("tas"), [""])
        self.assertEqual(groupAncestors("z2/ocean/sst"), ["", "z2", "z2/ocean"])
        def check(zarr_format, _separator, _tmp_path, store_dir, _tree):
            for group in self.GROUPS:
                self.assertTrue(isZarrGroupDir(str(store_dir / group)), group)
            for array in self.ARRAYS:
                self.assertFalse(isZarrGroupDir(str(store_dir / array)), array)
            self.assertEqual(listArrayPaths(zarr.open_group(str(store_dir), mode="r")), self.ARRAYS)
            # A plain directory holding no zarr metadata is not a group either.
            (store_dir / "notes").mkdir()
            self.assertFalse(isZarrGroupDir(str(store_dir / "notes")))

        self._for_each_layout(check)

    def test_diagnoser_records_arrays_by_path(self):
        for flag in ("0", "1"):
            with mock.patch.dict(os.environ, {"ZARRCURATOR_MULTITHREAD": flag}):
                def check(zarr_format, _separator, _tmp_path, store_dir, _tree):
                    store = str(store_dir)
                    sizes = TestCoordinateVariablesInTarballs._diagnose(store).exp_size_dict[store]

                    meta = [".zattrs", ".zgroup"] if zarr_format == 2 else ["zarr.json"]
                    expected = set(self.ARRAYS) | {f"{g}/{m}".lstrip("/") for g in self.GROUPS for m in meta}
                    self.assertEqual(set(sizes) - {"size", "count"}, expected)

                    files = self._store_files(store_dir)
                    self.assertEqual(sizes["count"], len(files))
                    self.assertEqual(sizes["size"], sum(files.values()))
                    sst_files = {k: v for k, v in files.items() if k.startswith(os.path.join("z2", "ocean", "sst"))}
                    self.assertEqual(sizes["z2/ocean/sst"]["count"], len(sst_files))
                    self.assertEqual(sizes["z2/ocean/sst"]["size"], sum(sst_files.values()))

                self._for_each_layout(check)

    def test_find_missing_chunks_checks_nested_arrays(self):
        from zarrcurator import utils

        def check(zarr_format, separator, tmp_path, store_dir, _tree):
            key = TestChunkKeySeparators._chunk_key
            sst_dir = store_dir / "z2" / "ocean" / "sst"
            (sst_dir / key(zarr_format, separator, 0, 0)).unlink()
            (sst_dir / key(zarr_format, separator, 0, 1)).write_bytes(b"")

            old_cwd = os.getcwd()
            try:
                os.chdir(tmp_path)
                with redirect_stdout(io.StringIO()):
                    utils.findMissingChunksInStore(str(store_dir))
            finally:
                os.chdir(old_cwd)

            nested = json.loads((tmp_path / "hp_P1D_z1.check").read_text(encoding="utf-8"))
            # The report is nested by group.
            self.assertEqual(sorted(nested), ["time", "z1", "z2"])
            self.assertEqual(sorted(nested["z2"]), ["cell", "ocean", "tas"])
            self.assertEqual(nested["z2"]["ocean"]["sst"]["type"], "array")
            self.assertEqual(nested["z2"]["ocean"]["sst"]["path"], "/z2/ocean/sst")
            self.assertEqual(utils.nestCheckReport(utils.flattenCheckReport(nested)), nested)

            report = utils.flattenCheckReport(nested)
            self.assertEqual(sorted(report), sorted(f"/{a}" for a in self.ARRAYS))
            sst = report["/z2/ocean/sst"]
            self.assertEqual(sst["expected_chunks"], 8)
            self.assertEqual(sst["missing"], ["0.0"])
            self.assertEqual(sst["zero_size"], [key(zarr_format, separator, 0, 1)])
            for array in self.ARRAYS:
                if array != "z2/ocean/sst":
                    self.assertEqual(report[f"/{array}"]["missing"], [], array)

        self._for_each_layout(check)

    def test_find_missing_chunks_logs_time_and_size_per_array(self):
        from zarrcurator import utils

        def check(zarr_format, separator, tmp_path, store_dir, _tree):
            sst_dir = store_dir / "z2" / "ocean" / "sst"
            sst_bytes = sum(
                f.stat().st_size for f in sst_dir.rglob("*")
                if f.is_file() and f.name not in {".zarray", ".zattrs", "zarr.json"}
            )
            old_cwd = os.getcwd()
            try:
                os.chdir(tmp_path)
                with redirect_stdout(io.StringIO()) as out, \
                        self.assertLogs("zarrcurator.utils", level="INFO") as logs:
                    utils.findMissingChunksInStore(str(store_dir))
            finally:
                os.chdir(old_cwd)

            for array in self.ARRAYS:
                self.assertTrue(any(f"check_array start /{array}" in line for line in logs.output), array)
                self.assertTrue(any(f"check_array end /{array} " in line for line in logs.output), array)
            sst_end = [line for line in logs.output if "check_array end /z2/ocean/sst " in line]
            self.assertIn(f"bytes={sst_bytes} chunks=8 ", sst_end[0])
            self.assertIn("checked in", out.getvalue())
            self.assertIn(f"{sst_bytes} bytes", out.getvalue())

        self._for_each_layout(check)

    @staticmethod
    def _chunk_files(array_dir):
        return sorted(
            str(f.relative_to(array_dir)) for f in array_dir.rglob("*")
            if f.is_file() and f.name not in {".zarray", ".zattrs", "zarr.json"}
        )

    def test_find_missing_chunks_resumes_partly_checked_array(self):
        from zarrcurator import utils

        def check(zarr_format, _separator, tmp_path, store_dir, _tree):
            sst = zarr.open_group(str(store_dir), mode="r")["z2/ocean/sst"]
            keys = self._chunk_files(store_dir / "z2" / "ocean" / "sst")
            self.assertEqual(len(keys), 8)
            # An earlier session checked two chunks of sst (one marked corrupt, so it is seen
            # not to be read again); the entry of tas has another shape and is ignored.
            partial = {
                "/z2/ocean/sst": {
                    "shape": list(sst.shape), "chunks": list(sst.chunks),
                    "shards": None if sst.shards is None else list(sst.shards),
                    "checked": keys[:2], "corrupt": [keys[1]],
                },
                "/z1/tas": {"shape": [999], "chunks": [1], "shards": None,
                            "checked": [], "corrupt": ["0"]},
            }
            partial_path = tmp_path / "hp_P1D_z1.check.partial"
            partial_path.write_text(json.dumps(partial), encoding="utf-8")

            old_cwd = os.getcwd()
            try:
                os.chdir(tmp_path)
                with redirect_stdout(io.StringIO()) as out:
                    utils.findMissingChunksInStore(str(store_dir))
            finally:
                os.chdir(old_cwd)

            report = utils.flattenCheckReport(
                json.loads((tmp_path / "hp_P1D_z1.check").read_text(encoding="utf-8")))
            self.assertEqual(report["/z2/ocean/sst"]["corrupt"], [keys[1]])
            self.assertEqual(report["/z1/tas"]["corrupt"], [])
            self.assertIn("resuming: 2 of 8 chunks", out.getvalue())
            self.assertFalse(partial_path.exists())

        with mock.patch.dict(os.environ, {"ZARRCURATOR_MULTITHREAD": "0"}):
            self._for_each_layout(check)

    @unittest.skipUnless(hasattr(signal, "SIGUSR1"), "needs SIGUSR1")
    def test_find_missing_chunks_saves_progress_on_signal(self):
        from zarrcurator import utils

        parse = utils.parseChunkKey

        def check(zarr_format, _separator, tmp_path, store_dir, _tree):
            partial_path = tmp_path / "hp_P1D_z1.check.partial"
            calls = []

            def interrupt_sst(key):
                # On the third chunk of sst: send the signal, wait for the partial file,
                # then stop the check as the end of a job would
                frame = sys._getframe(1)
                if frame.f_code.co_name == "check_chunk" and frame.f_locals.get("varName") == "z2/ocean/sst":
                    calls.append(key)
                    if len(calls) == 3:
                        os.kill(os.getpid(), signal.SIGUSR1)
                        deadline = time.monotonic() + 10
                        while not partial_path.exists() and time.monotonic() < deadline:
                            time.sleep(0.01)
                        raise KeyboardInterrupt
                return parse(key)

            handler = signal.getsignal(signal.SIGUSR1)
            old_cwd = os.getcwd()
            try:
                os.chdir(tmp_path)
                with redirect_stdout(io.StringIO()), mock.patch.object(utils, "parseChunkKey", interrupt_sst):
                    with self.assertRaises(KeyboardInterrupt):
                        utils.findMissingChunksInStore(str(store_dir), checkpointSignal=signal.SIGUSR1)
                self.assertEqual(signal.getsignal(signal.SIGUSR1), handler)
                saved = json.loads(partial_path.read_text(encoding="utf-8"))
                # Single-threaded only sst is in progress; multi-threaded other arrays may be too
                if os.environ["ZARRCURATOR_MULTITHREAD"] == "0":
                    self.assertEqual(list(saved), ["/z2/ocean/sst"])
                self.assertIn("/z2/ocean/sst", saved)
                # Chunks of other threads may finish too, the interrupted one is not saved
                checked = saved["/z2/ocean/sst"]["checked"]
                self.assertTrue(set(calls[:2]) <= set(checked), checked)
                self.assertNotIn(calls[2], checked)
                self.assertEqual(saved["/z2/ocean/sst"]["corrupt"], [])

                with redirect_stdout(io.StringIO()) as out:
                    utils.findMissingChunksInStore(str(store_dir))
            finally:
                os.chdir(old_cwd)

            self.assertIn(f"resuming: {len(checked)} of 8 chunks", out.getvalue())
            self.assertFalse(partial_path.exists())
            report = utils.flattenCheckReport(
                json.loads((tmp_path / "hp_P1D_z1.check").read_text(encoding="utf-8")))
            self.assertEqual(sorted(report), sorted(f"/{a}" for a in self.ARRAYS))
            self.assertEqual(report["/z2/ocean/sst"]["corrupt"], [])
            self.assertEqual(report["/z2/ocean/sst"]["found_chunks"], 8)

        for flag in ("0", "1"):
            with self.subTest(multithread=flag), mock.patch.dict(os.environ, {"ZARRCURATOR_MULTITHREAD": flag}):
                self._for_each_layout(check)

    def test_find_missing_chunks_resumes_from_report(self):
        from zarrcurator import utils

        def run(tmp_path, store_dir):
            old_cwd = os.getcwd()
            try:
                os.chdir(tmp_path)
                with redirect_stdout(io.StringIO()):
                    utils.findMissingChunksInStore(str(store_dir))
            finally:
                os.chdir(old_cwd)
            return utils.flattenCheckReport(
                json.loads((tmp_path / "hp_P1D_z1.check").read_text(encoding="utf-8"))
            )

        def check(zarr_format, separator, tmp_path, store_dir, _tree):
            report_path = tmp_path / "hp_P1D_z1.check"
            first = run(tmp_path, store_dir)
            self.assertEqual(sorted(first), sorted(f"/{a}" for a in self.ARRAYS))

            # Simulate an interrupted session: '/z1/tas' is done (marked so it is
            # seen to be kept), '/z2/ocean/sst' was not reached yet.
            partial = {"/z1/tas": dict(first["/z1/tas"], missing=["kept"])}
            report_path.write_text(json.dumps(utils.nestCheckReport(partial)), encoding="utf-8")
            sst_dir = store_dir / "z2" / "ocean" / "sst"
            (sst_dir / TestChunkKeySeparators._chunk_key(zarr_format, separator, 0, 0)).unlink()

            resumed = run(tmp_path, store_dir)
            self.assertEqual(sorted(resumed), sorted(first))
            self.assertEqual(resumed["/z1/tas"]["missing"], ["kept"])
            self.assertEqual(resumed["/z2/ocean/sst"]["missing"], ["0.0"])

            # Reports in the older flat format, appended once per array, are read too.
            report_path.write_text(
                json.dumps(partial, indent=2) + json.dumps(dict(partial, **{"/z2/tas": first["/z2/tas"]}), indent=2),
                encoding="utf-8",
            )
            resumed = run(tmp_path, store_dir)
            self.assertEqual(sorted(resumed), sorted(first))
            self.assertEqual(resumed["/z1/tas"]["missing"], ["kept"])

        self._for_each_layout(check)

    def test_tarballs_of_nested_arrays_open_as_datatree(self):

        from types import SimpleNamespace

        import xarray as xr

        from zarrcurator.config import configObj
        from zarrcurator.dispatcher import Dispatcher
        from zarrcurator.subgroup import SubGroup


        def restore(tar_name, target):
            with tarfile.open(tar_name) as tf:
                names = [m.name for m in tf.getmembers() if m.isfile()]
                tf.extractall(target, filter="data")
            return names, xr.open_datatree(target, engine="zarr", consolidated=False)

        def check(zarr_format, separator, tmp_path, store_dir, tree):
            configObj.setZarrStorePath(str(store_dir))
            configObj.setWorkingDir(str(tmp_path))
            dispatcher = Dispatcher(None, SimpleNamespace(targetSize=self.GIB, frequencySubGroupDict={}))

            var_group = SubGroup([("z2/ocean/sst", 1)], "var", [], [])
            dispatcher.createTarForVar(var_group, "hp_P1D_z1_1")
            _, restored = restore(var_group.groupTarMembers[0], tmp_path / "var")
            self.assertEqual([node.path for node in restored.subtree], ["/", "/z2", "/z2/ocean"])
            np.testing.assert_array_equal(restored["z2/ocean/sst"].values, tree["z2/ocean/sst"].values)

            # Twice the target size forces the chunks of the nested array into two tarballs.
            chunk_group = SubGroup([("z2/tas", 2 * self.GIB)], "chunk", [], [])
            dispatcher.createTarForChunk(chunk_group, "hp_P1D_z1_2")
            self.assertEqual(len(chunk_group.groupTarMembers), 2)
            tarred_chunks = []
            for index, tar_name in enumerate(chunk_group.groupTarMembers):
                names, restored = restore(tar_name, tmp_path / f"chunk_{index}")
                self.assertEqual([node.path for node in restored.subtree], ["/", "/z2"])
                tarred_chunks.extend(n[len("z2/tas/"):] for n in names if n.startswith("z2/tas/"))
            expected = [
                TestChunkKeySeparators._chunk_key(zarr_format, separator, i, j) for i in range(4) for j in range(2)
            ]
            chunks = [k for k in tarred_chunks if not k.startswith(".z") and k != "zarr.json"]
            # Every chunk of the nested array is archived exactly once.
            self.assertEqual(sorted(chunks), sorted(expected))

        self._for_each_layout(check)

    def test_kerchunk_parquet_roundtrip_of_tree_store(self):
        """Kerchunk combines references in the zarr v2 layout; zarr v3 metadata is translated to it."""

        import xarray as xr

        from zarrcurator import utils
        from zarrcurator.config import configObj

        for zarr_format, separator in TestChunkKeySeparators.LAYOUTS:
            with self.subTest(zarr_format=zarr_format, separator=separator), tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                configObj.setWorkingDir(str(tmp_path))
                store_dir = tmp_path / "hp.zarr"
                tree = self._make_tree(store_dir, zarr_format, separator, consolidated=True)

                tar_path = tmp_path / "hp_001.tar"
                with tarfile.open(tar_path, "w") as tf:
                    tf.add(store_dir, arcname=store_dir.name)
                with redirect_stdout(io.StringIO()):
                    utils.createKerchunkReferenceFileForTar(str(tar_path))
                    utils.convertKerchunkReferenceFilesOfZarrStoreToParquet(str(store_dir))

                # Chunk keys are rewritten to the dot-separated zarr v2 form relative to their array,
                # and zarr v3 metadata (zarr.json) is replaced by zarr v2 metadata.
                refs = json.loads((tmp_path / "hp_001_Offset_kerchunk.json.copy").read_text(encoding="utf-8"))["refs"]
                self.assertIn("z2/ocean/sst/0.1", refs)
                self.assertIn("z2/ocean/sst/.zarray", refs)
                self.assertIn("z2/ocean/.zgroup", refs)
                original_key = TestChunkKeySeparators._chunk_key(zarr_format, separator, 0, 1)
                if original_key != "0.1":
                    self.assertNotIn(f"z2/ocean/sst/{original_key}", refs)
                self.assertEqual([k for k in refs if k.endswith("zarr.json")], [])

                # The nested groups are only found through the consolidated metadata of the references.
                reopened = xr.open_datatree(
                    "reference://",
                    engine="zarr",
                    consolidated=True,
                    zarr_format=2,
                    storage_options={"fo": str(tmp_path / "hp.parq"), "remote_protocol": "file"},
                )
                self.assertTrue(reopened.identical(tree))

    def test_kerchunk_parquet_merges_references_of_all_tarballs(self):
        """The references of the tarballs a store is split into are merged into those of the whole store."""
        import xarray as xr

        from zarrcurator import utils
        from zarrcurator.dispatcher import Dispatcher

        def check(_zarr_format, _separator, tmp_path, store_dir, tree):
            distributor = self._distribute(str(store_dir), tmp_path)
            dispatcher = Dispatcher(None, distributor)
            tar_names = []
            with redirect_stdout(io.StringIO()):
                for group_id, sub_group in distributor.frequencySubGroupDict["P1D"].items():
                    dispatcher.createTarForSubGroup(sub_group, group_id)
                    tar_names.extend(sub_group.groupTarMembers)
                # Several var tarballs and two chunk tarballs each for 'z2/tas' and 'z2/ocean/sst'.
                self.assertGreaterEqual(len(tar_names), 5)
                for tar_name in tar_names:
                    utils.createKerchunkReferenceFileForTar(tar_name)
                utils.convertKerchunkReferenceFilesOfZarrStoreToParquet(str(store_dir))

            reopened = xr.open_datatree(
                "reference://",
                engine="zarr",
                consolidated=True,
                zarr_format=2,
                storage_options={"fo": str(tmp_path / "hp_P1D_z1.parq"), "remote_protocol": "file"},
            )
            self.assertTrue(reopened.identical(tree))

        self._for_each_layout(check)

    def test_merge_kerchunk_references(self):
        from zarrcurator import utils

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            def refs_file(name, refs):
                path = tmp_path / name
                path.write_text(json.dumps({"version": 1, "refs": refs}), encoding="utf-8")
                return str(path)

            meta = json.dumps({"zarr_format": 2})
            first = refs_file("a.json", {".zgroup": meta, ".zmetadata": "{}", "tas/0.0": ["file://a.tar", 0, 10]})
            second = refs_file("b.json", {".zgroup": meta, ".zmetadata": "{}", "tas/1.0": ["file://b.tar", 5, 10]})
            # Metadata found in several tarballs is kept once, the consolidated metadata is left out.
            self.assertEqual(
                utils.mergeKerchunkReferences([first, second]),
                {".zgroup": meta, "tas/0.0": ["file://a.tar", 0, 10], "tas/1.0": ["file://b.tar", 5, 10]},
            )
            # A chunk in two tarballs (e.g. of a coordinate variable) is kept once if the bytes are the same.
            (tmp_path / "a.tar").write_bytes(b"0123456789")
            (tmp_path / "b.tar").write_bytes(b"xx0123456789")
            (tmp_path / "c.tar").write_bytes(b"abcdefghij")
            same = refs_file("same.json", {"x/0": [f"file://{tmp_path}/a.tar", 0, 10]})
            copy = refs_file("copy.json", {"x/0": [f"file://{tmp_path}/b.tar", 2, 10]})
            self.assertEqual(utils.mergeKerchunkReferences([same, copy]), {"x/0": [f"file://{tmp_path}/a.tar", 0, 10]})
            conflicting = refs_file("c.json", {"x/0": [f"file://{tmp_path}/c.tar", 0, 10]})
            with self.assertRaisesRegex(ValueError, "x/0"):
                utils.mergeKerchunkReferences([same, conflicting])

    @staticmethod
    def _make_plain_zarr_store(store_dir, zarr_format):
        """A store written with plain zarr, without the dimension names xarray needs."""
        group = zarr.open_group(str(store_dir), mode="w", zarr_format=zarr_format)
        group.create_array("tas", shape=(4, 6), chunks=(2, 3), dtype="f4")[:] = 1

    def test_check_store_opens_with_xarray(self):
        import xarray as xr

        from zarrcurator import utils

        def check(zarr_format, _separator, tmp_path, store_dir, _tree):
            # A tree store written with xarray passes, as does a flat one.
            utils.checkStoreOpensWithXarray(str(store_dir), "tree")
            flat = tmp_path / "flat.zarr"
            xr.Dataset({"tas": (("time", "cell"), np.ones((4, 6), "f4"))}).to_zarr(flat, zarr_format=zarr_format)
            utils.checkStoreOpensWithXarray(str(flat), "flat")
            plain = tmp_path / "plain.zarr"
            self._make_plain_zarr_store(plain, zarr_format)
            with self.assertRaisesRegex(ValueError, "cannot be opened with xarray"):
                utils.checkStoreOpensWithXarray(str(plain), "plain")

        self._for_each_layout(check)

    def test_dispatch_fails_early_for_store_xarray_cannot_open(self):
        from zarrcurator import utils
        from zarrcurator.config import configObj

        for zarr_format in (2, 3):
            with self.subTest(zarr_format=zarr_format), tempfile.TemporaryDirectory() as tmpdir:
                store_dir = Path(tmpdir) / "plain_P1D_1.zarr"
                self._make_plain_zarr_store(store_dir, zarr_format)
                old_cwd = os.getcwd()
                try:
                    os.chdir(tmpdir)
                    with mock.patch.object(configObj, "getDistributorObj", return_value=None), \
                         mock.patch.object(utils, "Diagnoser") as mock_diagnoser, \
                         mock.patch.object(utils, "Distributor") as mock_distributor, \
                         mock.patch.object(utils, "Dispatcher") as mock_dispatcher, \
                         self.assertRaisesRegex(ValueError, "cannot be opened with xarray"):
                        utils.dispatchStoreToTarStores(str(store_dir))
                finally:
                    os.chdir(old_cwd)
                # Nothing is diagnosed, distributed or archived.
                mock_diagnoser.assert_not_called()
                mock_distributor.assert_not_called()
                mock_dispatcher.assert_not_called()
                self.assertEqual(list(Path(tmpdir).glob("*.tar")), [])

    def test_entries_are_distributed_per_group(self):
        """Each subgroup holds the entries of one group only, e.g. of one zoom level of a DataTree."""
        from zarrcurator.distributor import Distributor

        distributor = Distributor.__new__(Distributor)
        distributor.targetSize = 10

        def store(entries):
            return {name: {"size": size, "count": 1} for name, size in entries.items()}

        # Without nested groups all entries belong to the root group.
        self.assertEqual(distributor.groupEntriesByGroup(store({"tas": 20, "time": 1})),
                         {"": [("tas", 20), ("time", 1)]})
        # Groups with metadata files only (the root, 'ms') go to the first group with arrays.
        entries = {"zarr.json": 1, "ms/zarr.json": 1,
                   "ms/zoom_0/zarr.json": 1, "ms/zoom_0/tas": 2, "ms/zoom_0/pr": 2,
                   "ms/zoom_1/zarr.json": 1, "ms/zoom_1/tas": 4, "ms/zoom_1/pr": 4, "ms/zoom_1/wa": 30,
                   "ms/zoom_2/zarr.json": 1, "ms/zoom_2/wa": 40}
        groups = distributor.groupEntriesByGroup(store(entries))
        self.assertEqual(list(groups), ["ms/zoom_0", "ms/zoom_1", "ms/zoom_2"])
        self.assertEqual(sorted(name for name, _ in groups["ms/zoom_0"]),
                         ["ms/zarr.json", "ms/zoom_0/pr", "ms/zoom_0/tas", "ms/zoom_0/zarr.json", "zarr.json"])

        sizes = store(entries)
        sizes.update({"size": sum(entries.values()), "count": len(entries)})
        sub_groups = distributor.split_zarr_into_equalSized_bins(sizes)
        members = sorted((g.groupType, sorted(m[0] for m in g.groupMembers)) for g in sub_groups)
        self.assertEqual(members, [
            ("chunk", ["ms/zoom_1/wa"]),
            ("chunk", ["ms/zoom_2/wa"]),
            ("var", ["ms/zarr.json", "ms/zoom_0/pr", "ms/zoom_0/tas", "ms/zoom_0/zarr.json", "zarr.json"]),
            ("var", ["ms/zoom_1/pr", "ms/zoom_1/tas", "ms/zoom_1/zarr.json"]),
        ])
        # No subgroup mixes zoom levels; 'ms/zoom_2' has a chunk subgroup only, whose tarballs carry its metadata.
        for sub_group in sub_groups:
            zooms = {m[0].split("/")[1] for m in sub_group.groupMembers if m[0].count("/") == 2}
            self.assertLessEqual(len(zooms), 1)

    def test_subgroups_are_named_by_zoom_level(self):
        """Subgroups (and so tarballs) of a split tree store are named by their group, e.g. the zoom level."""
        from zarrcurator.distributor import Distributor
        from zarrcurator.subgroup import SubGroup

        def redistribute(entries, store_id):
            sizes = {name: {"size": size, "count": 1} for name, size in entries.items()}
            sizes.update({"size": sum(entries.values()), "count": len(entries)})
            distributor = Distributor.__new__(Distributor)
            distributor.targetSize = 10
            distributor.frequencyGroupDict = {"ALL": {"/tmp/s.zarr": sizes}}
            distributor.frequencySubGroupDict = {"ALL": {store_id: SubGroup([("/tmp/s.zarr", sizes["size"])], "zarr", [], [])}}
            distributor.redistributeSubGroups()
            return {name: (g.groupType, sorted(m[0] for m in g.groupMembers))
                    for name, g in distributor.frequencySubGroupDict["ALL"].items()}

        tree = {"zarr.json": 1, "ms/zarr.json": 1,
                "ms/zoom_2/tas": 6, "ms/zoom_2/pr": 6,
                "ms/zoom_10/tas": 4, "ms/zoom_10/wa": 30}
        self.assertEqual(redistribute(tree, "P1D_mean_atm"), {
            # numbered per zoom level, zoom levels in numeric order
            "P1D_mean_atm_zoom_2_1": ("var", ["ms/zarr.json", "ms/zoom_2/pr", "ms/zoom_2/tas", "zarr.json"]),
            "P1D_mean_atm_zoom_10_1": ("var", ["ms/zoom_10/tas"]),
            "P1D_mean_atm_zoom_10_2": ("chunk", ["ms/zoom_10/wa"]),
        })
        # Groups with the same name are labelled by their path.
        self.assertEqual(Distributor.subGroupLabels(["atmos/zoom_0", "ocean/zoom_0", "ocean/zoom_1", ""]),
                         {"atmos/zoom_0": "atmos_zoom_0", "ocean/zoom_0": "ocean_zoom_0", "ocean/zoom_1": "zoom_1", "": ""})
        # A store without nested groups keeps its names.
        self.assertEqual(sorted(redistribute({"tas": 6, "pr": 6, "wa": 30}, "ngc4008_P1D_7")),
                         ["ngc4008_P1D_7_1", "ngc4008_P1D_7_2"])

    def test_get_zarrstore_dimensions_resolves_inherited_coordinates(self):
        from zarrcurator.config import configObj
        from zarrcurator.distributor import Distributor

        def check(_zarr_format, _separator, _tmp_path, store_dir, _tree):
            store = str(store_dir)
            distributor = Distributor.__new__(Distributor)
            distributor.diagnoserObj = TestCoordinateVariablesInTarballs._diagnose(store)
            with mock.patch.object(configObj, "getFileSystemObj", return_value=None):
                def coords(groups):
                    return [os.path.relpath(p, store) for p, _ in distributor.getZarrstoreDimensions("P1D", store, groups)]

                self.assertEqual(coords(None), ["time"])
                self.assertEqual(coords(["z1"]), ["time", "z1/cell"])
                # '/z2/ocean' has no coordinate arrays of its own: 'cell' comes from '/z2', 'time' from the root.
                self.assertEqual(coords(["z2/ocean"]), ["time", "z2/cell"])

        self._for_each_layout(check)

    def _distribute(self, store, tmp_path):
        """Distribute a tree store into sub groups, with 'z1' kept whole and 'z2/tas', 'z2/ocean/sst' split."""
        from zarrcurator.config import configObj
        from zarrcurator.distributor import Distributor
        from zarrcurator.subgroup import SubGroup

        diagnoser = TestCoordinateVariablesInTarballs._diagnose(store)
        sizes = diagnoser.exp_size_dict[store]
        # Sizes such that 'z2/tas' and 'z2/ocean/sst' exceed the 2 GiB target and are split into
        # chunk tarballs, while the group 'z1' fits and is archived as a whole.
        large = {"z2/tas": 3 * self.GIB, "z2/ocean/sst": 3 * self.GIB, "z1/tas": self.GIB}
        for name, entry in sizes.items():
            if isinstance(entry, dict):
                entry["size"] = large.get(name, 1024 * 1024)
        sizes["size"] = sum(entry["size"] for entry in sizes.values() if isinstance(entry, dict))

        distributor = Distributor.__new__(Distributor)
        distributor.diagnoserObj = diagnoser
        distributor.targetSize = 2 * self.GIB
        distributor.frequencyGroupDict = {"P1D": {store: sizes}}
        distributor.frequencySubGroupDict = {"P1D": {"hp_P1D_z1": SubGroup([(store, sizes["size"])], "zarr", [], [])}}
        configObj.setZarrStorePath(store)
        configObj.setWorkingDir(str(tmp_path))
        with mock.patch.object(configObj, "getFileSystemObj", return_value=None), redirect_stdout(io.StringIO()):
            distributor.redistributeSubGroups()
            distributor.updateDimensionsToSubGroups()
        return distributor

    def test_distribute_and_dispatch_tree_store(self):
        import xarray as xr

        from zarrcurator.dispatcher import Dispatcher

        def check(_zarr_format, _separator, tmp_path, store_dir, tree):
            store = str(store_dir)
            distributor = self._distribute(store, tmp_path)
            sub_groups = distributor.frequencySubGroupDict["P1D"]
            by_type = {}
            for sub_group in sub_groups.values():
                members = [os.path.relpath(m[0], store) if os.path.isabs(m[0]) else m[0] for m in sub_group.groupMembers]
                by_type.setdefault(sub_group.groupType, []).append(members)
            self.assertEqual(sorted(m[0] for m in by_type["chunk"]), ["z2/ocean/sst", "z2/tas"])
            z1_groups = [members for members in by_type["var"] if "z1/tas" in members]
            self.assertEqual(len(z1_groups), 1)
            self.assertTrue({"z1/tas", "z1/cell", "time"} <= set(z1_groups[0]))

            dispatcher = Dispatcher(None, distributor)
            archived = {}
            for group_id, sub_group in sub_groups.items():
                with redirect_stdout(io.StringIO()):
                    dispatcher.createTarForSubGroup(sub_group, group_id)
                for tar_name in sub_group.groupTarMembers:
                    target = tmp_path / f"restored_{os.path.basename(tar_name)}"
                    with tarfile.open(tar_name) as tf:
                        tf.extractall(target, filter="data")
                    restored = xr.open_datatree(target, engine="zarr", consolidated=False)
                    for node in restored.subtree:
                        for name in node.data_vars:
                            # Each data variable comes with its coordinates, inherited ones included.
                            self.assertEqual(sorted(node.coords), ["cell", "time"], node.path)
                            archived.setdefault(f"{node.path}/{name}".lstrip("/"), []).append(tar_name)
            self.assertEqual(sorted(archived), ["z1/tas", "z2/ocean/sst", "z2/tas"])
            self.assertEqual(len(archived["z2/tas"]), 2)
            np.testing.assert_array_equal(
                xr.open_datatree(tmp_path / f"restored_{os.path.basename(archived['z1/tas'][0])}", engine="zarr", consolidated=False)["z1/tas"].values,
                tree["z1/tas"].values,
            )

        self._for_each_layout(check)

    def test_find_missing_chunks_checks_several_arrays_at_once(self):
        """Arrays checked at once give the report of a sequential check, and the check can be resumed."""
        from zarrcurator import chunkkeys, utils

        def run(tmp_path, store_dir, env, interrupt_after=None):
            calls = []
            original = utils.numThreadsForChunks
            lock = threading.Lock()

            def counting(num_chunks, ioBound=True):
                # called once per array and kind of work; stop the session after some arrays
                with lock:
                    calls.append(ioBound)
                    if interrupt_after is not None and calls.count(True) > interrupt_after:
                        raise KeyboardInterrupt("session ended")
                return original(num_chunks, ioBound=ioBound)

            old_cwd = os.getcwd()
            out = io.StringIO()
            try:
                os.chdir(tmp_path)
                with mock.patch.dict(os.environ, env), mock.patch.object(utils, "numThreadsForChunks", counting), \
                     redirect_stdout(out):
                    utils.findMissingChunksInStore(str(store_dir))
            finally:
                os.chdir(old_cwd)
            return (tmp_path / "hp_P1D_z1.check").read_text(encoding="utf-8"), out.getvalue()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            store_dir = tmp_path / "hp_P1D_z1.zarr"
            self._make_tree(store_dir, 3, "/")
            # anomalies in two arrays of different groups
            sst_chunk = next(p for p in (store_dir / "z2" / "ocean" / "sst").rglob("*") if p.is_file() and p.name.isdigit())
            sst_chunk.write_bytes(b"")
            tas_chunk = next(p for p in (store_dir / "z1" / "tas").rglob("*") if p.is_file() and p.name.isdigit())
            tas_chunk.unlink()

            sequential, _ = run(tmp_path, store_dir, {"ZARRCURATOR_MULTITHREAD": "0"})
            (tmp_path / "hp_P1D_z1.check").unlink()
            parallel_env = {"ZARRCURATOR_MULTITHREAD": "1", chunkkeys.ENV_ARRAY_WORKERS: "4",
                            chunkkeys.ENV_MAX_THREADS: "3"}
            parallel, output = run(tmp_path, store_dir, parallel_env)
            # Same report, arrays in the order of the store
            self.assertEqual(json.loads(parallel), json.loads(sequential))
            self.assertEqual(parallel, sequential)
            # Lines are labelled with their array when arrays are checked at once
            self.assertIn("[z2/ocean/sst] zero-size chunks: 1", output)
            self.assertIn("[z1/tas] missing chunks: 1", output)

            # An interrupted session keeps the arrays it finished; the next one checks the others.
            (tmp_path / "hp_P1D_z1.check").unlink()
            with self.assertRaises(KeyboardInterrupt):
                run(tmp_path, store_dir, parallel_env, interrupt_after=3)
            partial = utils.flattenCheckReport(json.loads((tmp_path / "hp_P1D_z1.check").read_text(encoding="utf-8")))
            self.assertTrue(0 < len(partial) < len(self.ARRAYS))
            resumed, output = run(tmp_path, store_dir, parallel_env)
            self.assertIn("already checked", output)
            self.assertEqual(json.loads(resumed), json.loads(sequential))

    def test_diagnosis_resumes_from_checkpoint(self):
        """An interrupted diagnosis continues from its checkpoint, with the result of a single session."""
        from zarrcurator.diagnoser import Diagnoser

        def new_diagnoser():
            diagnoser = Diagnoser.__new__(Diagnoser)
            diagnoser.fileSystemObj = None
            diagnoser.exp_size_dict = {}
            diagnoser.zeroSizeFilesDict = collections.defaultdict(list)
            diagnoser.zeroSizeFilesFlag = False
            diagnoser.checkpointInterval = 0  # write the checkpoint after every entry
            return diagnoser

        def check(_zarr_format, separator, tmp_path, store_dir, _tree):
            store = str(store_dir)
            chunk_dir = next(p for p in (store_dir / "z1" / "tas").rglob("*") if p.is_file() and p.name[0].isdigit())
            chunk_dir.write_bytes(b"")  # a zero-size chunk, to be kept across sessions
            with redirect_stdout(io.StringIO()):
                reference = new_diagnoser()
                reference.diagnose_zarr(store)
            names = [n for n in reference.exp_size_dict[store] if n not in ("size", "count")]

            for flag in ("0", "1"):
                with self.subTest(multithread=flag), mock.patch.dict(os.environ, {"ZARRCURATOR_MULTITHREAD": flag}):
                    checkpoint = tmp_path / f"hp_P1D_z1_{flag}.diag.checkpoint"
                    original = Diagnoser.diagnose_zarr_var
                    calls = []
                    lock = threading.Lock()

                    def interrupted(self, var, zarr_path, var_name=None):
                        with lock:
                            if len(calls) >= 4:
                                raise KeyboardInterrupt("session ended")
                            calls.append(var_name)
                        return original(self, var, zarr_path, var_name)

                    first = new_diagnoser()
                    with mock.patch.object(Diagnoser, "diagnose_zarr_var", interrupted), \
                         redirect_stdout(io.StringIO()), self.assertRaises(KeyboardInterrupt):
                        first.diagnose_zarr(store, checkpointFile=str(checkpoint))
                    saved = json.loads(checkpoint.read_text())
                    self.assertEqual(saved["store"], store)
                    self.assertTrue(0 < len(saved["entries"]) < len(names))
                    self.assertFalse(any(p.suffix == ".tmp" for p in tmp_path.iterdir()))

                    # The next session diagnoses only the remaining entries.
                    second_calls = []
                    def counted(self, var, zarr_path, var_name=None):
                        second_calls.append(var_name)
                        return original(self, var, zarr_path, var_name)
                    second = new_diagnoser()
                    with mock.patch.object(Diagnoser, "diagnose_zarr_var", counted), redirect_stdout(io.StringIO()):
                        second.diagnose_zarr(store, checkpointFile=str(checkpoint))
                    self.assertEqual(sorted(second_calls), sorted(set(names) - set(saved["entries"])))

                    def sizes(d):
                        return [(n, e["size"], e["count"]) if isinstance(e, dict) else (n, e) for n, e in d.items()]
                    self.assertEqual(sizes(second.exp_size_dict[store]), sizes(reference.exp_size_dict[store]))
                    self.assertTrue(second.zeroSizeFilesFlag)
                    self.assertIn(str(chunk_dir), second.zeroSizeFilesDict[store.split(".")[0]])

            # A checkpoint of another store is ignored.
            other = tmp_path / "other.diag.checkpoint"
            other.write_text(json.dumps({"store": "/elsewhere.zarr", "entries": {"time": {"size": 1, "count": 1}}}))
            diagnoser = new_diagnoser()
            with redirect_stdout(io.StringIO()):
                diagnoser.diagnose_zarr(store, checkpointFile=str(other))
            self.assertEqual(sizes(diagnoser.exp_size_dict[store]), sizes(reference.exp_size_dict[store]))

        for layout in [(3, "/"), (2, ".")]:
            with self.subTest(layout=layout), tempfile.TemporaryDirectory() as tmpdir:
                store_dir = Path(tmpdir) / "hp_P1D_z1.zarr"
                self._make_tree(store_dir, *layout)
                check(*layout, Path(tmpdir), store_dir, None)

    def test_diagnose_store_resumes_and_removes_checkpoint(self):
        from zarrcurator import utils
        from zarrcurator.diagnoser import Diagnoser
        from zarrcurator.storetree import flattenDiagReport

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            store_dir = tmp_path / "hp_P1D_z1.zarr"
            self._make_tree(store_dir, 3, "/")
            work = tmp_path / "work"
            work.mkdir()
            old_cwd = os.getcwd()
            try:
                os.chdir(work)
                with redirect_stdout(io.StringIO()):
                    utils.diagnoseStore(str(store_dir))
                reference = flattenDiagReport(json.loads((work / "hp_P1D_z1.diag").read_text()))
                self.assertEqual(sorted(p.name for p in work.iterdir()), ["hp_P1D_z1.diag"])

                # A checkpoint left by an interrupted session: 'time' was already diagnosed.
                (work / "hp_P1D_z1.diag").unlink()
                store = next(iter(reference))
                (work / "hp_P1D_z1.diag.checkpoint").write_text(json.dumps(
                    {"store": store, "entries": {"time": reference[store]["time"]}, "zeroSizeFiles": []}))
                diagnosed = []
                original = Diagnoser.diagnose_zarr_var
                def counted(self, var, zarr_path, var_name=None):
                    diagnosed.append(var_name)
                    return original(self, var, zarr_path, var_name)
                out = io.StringIO()
                with mock.patch.object(Diagnoser, "diagnose_zarr_var", counted), redirect_stdout(out):
                    utils.diagnoseStore(str(store_dir))
            finally:
                os.chdir(old_cwd)
            self.assertIn("resuming the diagnosis", out.getvalue())
            self.assertNotIn("time", diagnosed)
            def sizes(report):
                return {name: {k: (v["size"], v["count"]) if isinstance(v, dict) else v for k, v in entries.items()}
                        for name, entries in report.items()}
            self.assertEqual(sizes(flattenDiagReport(json.loads((work / "hp_P1D_z1.diag").read_text()))), sizes(reference))
            self.assertEqual(sorted(p.name for p in work.iterdir()), ["hp_P1D_z1.diag"])

    def test_dispatch_skips_existing_tarballs(self):
        """Tarballs that exist completely are skipped, so the dispatch can be resumed in a later session."""
        from zarrcurator.dispatcher import Dispatcher

        def check(zarr_format, separator, tmp_path, store_dir, _tree):
            if (zarr_format, separator) != (3, "/"):
                return
            distributor = self._distribute(str(store_dir), tmp_path)
            sub_groups = distributor.frequencySubGroupDict["P1D"]

            def dispatch():
                dispatcher = Dispatcher(None, distributor)
                with redirect_stdout(io.StringIO()), self.assertLogs("zarrcurator.dispatcher", "INFO") as logs:
                    for group_id, sub_group in sub_groups.items():
                        dispatcher.createTarForSubGroup(sub_group, group_id)
                tars = sorted(t for g in sub_groups.values() for t in g.groupTarMembers)
                skipped = sorted(line.split(": ", 1)[1] for line in logs.output if "Skipping existing tar file" in line)
                return tars, skipped

            tars, skipped = dispatch()
            self.assertEqual(skipped, [])
            self.assertGreater(len(tars), 3)
            self.assertEqual(list(tmp_path.glob("*.part")), [])
            mtimes = {t: os.path.getmtime(t) for t in tars}

            # A second session skips all tarballs and still records them in the subgroups.
            self.assertEqual(dispatch(), (tars, tars))
            self.assertEqual({t: os.path.getmtime(t) for t in tars}, mtimes)

            # A missing and an incomplete tarball (e.g. from an older, interrupted session) are created again.
            missing, cut = tars[0], tars[-1]
            os.remove(missing)
            with open(cut, "r+b") as f:
                f.truncate(os.path.getsize(cut) // 2)
            self.assertEqual(dispatch(), (tars, sorted(set(tars) - {missing, cut})))
            for t in (missing, cut):
                with tarfile.open(t) as tf:
                    self.assertTrue(tf.getmembers())

        self._for_each_layout(check)

    def test_tar_completeness_and_interrupted_writes(self):
        from zarrcurator import dispatcher

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            (tmp_path / "data.bin").write_bytes(os.urandom(5000))
            complete = tmp_path / "complete.tar"
            with dispatcher._openTarForWriting(str(complete)) as tar:
                tar.add(tmp_path / "data.bin", arcname="data.bin")
            self.assertTrue(dispatcher._isCompleteTar(str(complete)))
            self.assertFalse((tmp_path / "complete.tar.part").exists())

            data = complete.read_bytes()
            cases = {
                "cut in the data": data[:3000],
                "without the end blocks": data[:512 + 5120],
                "not a tar file": b"not a tar file" * 100,
            }
            for name, content in cases.items():
                with self.subTest(name):
                    path = tmp_path / "broken.tar"
                    path.write_bytes(content)
                    self.assertFalse(dispatcher._isCompleteTar(str(path)))

            # An interrupted write leaves neither the tarball nor its temporary file.
            interrupted = tmp_path / "interrupted.tar"
            with self.assertRaises(RuntimeError):
                with dispatcher._openTarForWriting(str(interrupted)) as tar:
                    tar.add(tmp_path / "data.bin", arcname="data.bin")
                    raise RuntimeError("session interrupted")
            self.assertFalse(interrupted.exists())
            self.assertFalse((tmp_path / "interrupted.tar.part").exists())


@unittest.skipUnless(np is not None and zarr is not None, "requires numpy, zarr")
class TestZarrV3Metadata(unittest.TestCase):
    """Translation of zarr v3 metadata to zarr v2 for the Kerchunk references of zarr v3 stores."""

    @staticmethod
    def _array_meta(**overrides):
        meta = {
            "zarr_format": 3,
            "node_type": "array",
            "shape": [4, 6],
            "data_type": "float32",
            "chunk_grid": {"name": "regular", "configuration": {"chunk_shape": [2, 3]}},
            "chunk_key_encoding": {"name": "default", "configuration": {"separator": "/"}},
            "fill_value": "NaN",
            "codecs": [{"name": "bytes", "configuration": {"endian": "little"}}, {"name": "zstd", "configuration": {"level": 3, "checksum": False}}],
            "attributes": {"_FillValue": "AAAAAAAA+H8=", "units": "K"},
            "dimension_names": ["time", "cell"],
        }
        meta.update(overrides)
        return meta

    def test_array_and_group_metadata(self):
        from zarrcurator.zarrmetadata import v3MetadataToV2

        v2 = v3MetadataToV2(self._array_meta())
        self.assertEqual(v2[".zarray"], {
            "zarr_format": 2, "shape": [4, 6], "chunks": [2, 3], "dtype": "<f4",
            "compressor": {"id": "zstd", "level": 3, "checksum": False}, "fill_value": "NaN",
            "order": "C", "filters": None, "dimension_separator": ".",
        })
        # xarray's '_FillValue' attribute of zarr v3 is the zarr v2 fill value instead.
        self.assertEqual(v2[".zattrs"], {"units": "K", "_ARRAY_DIMENSIONS": ["time", "cell"]})

        group = v3MetadataToV2({"zarr_format": 3, "node_type": "group", "attributes": {"title": "t"}})
        self.assertEqual(group, {".zgroup": {"zarr_format": 2}, ".zattrs": {"title": "t"}})

    def test_fill_value_and_dimension_names(self):
        from zarrcurator.zarrmetadata import v3MetadataToV2

        # Without '_FillValue' a zero fill value is left out, so xarray does not mask zeros.
        v2 = v3MetadataToV2(self._array_meta(data_type="int64", fill_value=0, attributes={}))
        self.assertIsNone(v2[".zarray"]["fill_value"])
        self.assertEqual(v2[".zarray"]["dtype"], "<i8")
        # A non-zero fill value is kept, so that missing chunks read correctly.
        v2 = v3MetadataToV2(self._array_meta(data_type="int16", fill_value=-999, attributes={}))
        self.assertEqual(v2[".zarray"]["fill_value"], -999)
        # zarr leaves out the dimension names of 0-d arrays.
        meta = self._array_meta(shape=[], chunk_grid={"name": "regular", "configuration": {"chunk_shape": []}}, attributes={})
        del meta["dimension_names"]
        self.assertEqual(v3MetadataToV2(meta)[".zattrs"], {"_ARRAY_DIMENSIONS": []})
        big_endian = self._array_meta(codecs=[{"name": "bytes", "configuration": {"endian": "big"}}])
        self.assertEqual(v3MetadataToV2(big_endian)[".zarray"]["dtype"], ">f4")

    def test_codecs(self):
        from zarrcurator.zarrmetadata import v3CodecsToV2

        def codecs(*compressors):
            return [{"name": "bytes", "configuration": {"endian": "little"}}, *compressors]

        self.assertEqual(v3CodecsToV2(codecs()), ("little", None))
        self.assertEqual(v3CodecsToV2(codecs({"name": "gzip", "configuration": {"level": 5}}))[1], {"id": "gzip", "level": 5})
        blosc = {"name": "blosc", "configuration": {"cname": "lz4", "clevel": 5, "shuffle": "bitshuffle", "typesize": 4, "blocksize": 0}}
        self.assertEqual(v3CodecsToV2(codecs(blosc))[1], {"id": "blosc", "cname": "lz4", "clevel": 5, "shuffle": 2, "blocksize": 0})
        self.assertEqual(v3CodecsToV2(codecs({"name": "numcodecs.lz4", "configuration": {"acceleration": 1}}))[1], {"id": "lz4", "acceleration": 1})
        # Codecs without a zarr v2 equivalent, as the chunks are referenced unchanged.
        for unsupported in (
            [{"name": "sharding_indexed", "configuration": {}}],
            [{"name": "transpose", "configuration": {"order": [1, 0]}}] + codecs(),
            codecs({"name": "zstd"}, {"name": "crc32c"}),
        ):
            with self.subTest(codecs=[c["name"] for c in unsupported]), self.assertRaises(ValueError):
                v3CodecsToV2(unsupported)

    def test_chunk_keys(self):
        from zarrcurator.zarrmetadata import v3ChunkKeyToV2

        default = {"name": "default", "configuration": {"separator": "/"}}
        self.assertEqual(v3ChunkKeyToV2("c/0/1", default), "0.1")
        self.assertEqual(v3ChunkKeyToV2("c.0.1", {"name": "default", "configuration": {"separator": "."}}), "0.1")
        self.assertEqual(v3ChunkKeyToV2("c", default), "0")
        self.assertEqual(v3ChunkKeyToV2("0/1", {"name": "v2", "configuration": {"separator": "/"}}), "0.1")

    def test_kerchunk_parquet_roundtrip_of_flat_v3_store(self):
        import fsspec
        import pandas as pd
        import xarray as xr

        from zarrcurator import utils
        from zarrcurator.config import configObj

        values = np.arange(24, dtype="f4").reshape(4, 6)
        values[1, 2] = np.nan
        # 'orog' has no 'time' dimension: the merged references keep it as it is.
        ds = xr.Dataset(
            {"tas": (("time", "cell"), values), "orog": (("cell",), np.arange(6, dtype="i2"))},
            coords={
                "time": pd.date_range("2020-01-01", periods=4, freq="D"),
                "crs": ((), 0, {"grid_mapping_name": "healpix"}),
            },
        )
        encodings = {
            "zstd": {"tas": {"chunks": (2, 3)}},
            "blosc, v2 key encoding": {"tas": {
                "chunks": (2, 3),
                "compressors": [zarr.codecs.BloscCodec(cname="lz4", clevel=5, shuffle="shuffle")],
                "chunk_key_encoding": {"name": "v2", "separator": "/"},
            }},
            "no compressor": {"tas": {"chunks": (2, 3), "compressors": None}},
        }
        for label, encoding in encodings.items():
            with self.subTest(encoding=label), tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                configObj.setWorkingDir(str(tmp_path))
                store_dir = tmp_path / "hp.zarr"
                ds.to_zarr(store_dir, zarr_format=3, consolidated=True, encoding=encoding)
                tar_path = tmp_path / "hp_001.tar"
                with tarfile.open(tar_path, "w") as tf:
                    tf.add(store_dir, arcname=store_dir.name)
                with redirect_stdout(io.StringIO()):
                    utils.createKerchunkReferenceFileForTar(str(tar_path))
                    utils.convertKerchunkReferenceFilesOfZarrStoreToParquet(str(store_dir))

                mapper = fsspec.get_mapper("reference://", fo=str(tmp_path / "hp.parq"), remote_protocol="file")
                reopened = xr.open_dataset(mapper, engine="zarr", consolidated=False, zarr_format=2)
                self.assertTrue(reopened.identical(ds))

    @staticmethod
    def _sharded_meta(**sharding):
        conf = {
            "chunk_shape": [2, 3],
            "codecs": [{"name": "bytes", "configuration": {"endian": "little"}}, {"name": "zstd", "configuration": {"level": 0, "checksum": False}}],
            "index_codecs": [{"name": "bytes", "configuration": {"endian": "little"}}, {"name": "crc32c"}],
            "index_location": "end",
        }
        conf.update(sharding)
        return TestZarrV3Metadata._array_meta(
            shape=[6, 7],
            chunk_grid={"name": "regular", "configuration": {"chunk_shape": [4, 6]}},
            codecs=[{"name": "sharding_indexed", "configuration": conf}],
        )

    def test_sharding_layout(self):
        from zarrcurator.zarrmetadata import v3MetadataToV2, v3ShardingLayout

        meta = self._sharded_meta()
        self.assertIsNone(v3ShardingLayout(self._array_meta()))
        layout = v3ShardingLayout(meta)
        self.assertEqual(layout["shard_shape"], [4, 6])
        self.assertEqual(layout["chunk_shape"], [2, 3])
        # 2 x 2 inner chunks of 16 bytes (offset, size) each, and the 4 byte checksum.
        self.assertEqual(layout["index_size"], 4 * 16 + 4)
        self.assertTrue(layout["index_checksum"])
        # The zarr v2 chunks are the inner chunks, with the inner codecs.
        zarray = v3MetadataToV2(meta)[".zarray"]
        self.assertEqual(zarray["chunks"], [2, 3])
        self.assertEqual(zarray["compressor"], {"id": "zstd", "level": 0, "checksum": False})
        self.assertEqual(v3ShardingLayout(self._sharded_meta(index_codecs=[{"name": "bytes"}]))["index_size"], 4 * 16)

        nested = self._sharded_meta(codecs=[{"name": "sharding_indexed", "configuration": {"chunk_shape": [1, 3]}}])
        unsupported = {
            "compressor after sharding": dict(meta, codecs=meta["codecs"] + [{"name": "zstd"}]),
            "shard not a multiple of the chunks": self._sharded_meta(chunk_shape=[3, 3]),
            "index codec": self._sharded_meta(index_codecs=[{"name": "bytes"}, {"name": "zstd"}]),
        }
        for label, bad in unsupported.items():
            with self.subTest(unsupported=label), self.assertRaises(ValueError):
                v3ShardingLayout(bad)
        with self.assertRaises(ValueError):
            v3MetadataToV2(nested)

    def test_shard_chunk_references(self):
        from numcodecs import CRC32C

        from zarrcurator.zarrmetadata import (
            SHARD_EMPTY_CHUNK,
            shardChunkReferences,
            v3ShardingLayout,
        )

        empty = SHARD_EMPTY_CHUNK
        index_size = 4 * 16 + 4
        for location in ("end", "start"):
            with self.subTest(index_location=location):
                layout = v3ShardingLayout(self._sharded_meta(index_location=location))
                # Offsets are relative to the start of the shard, which holds the index first or last.
                data_start = 0 if location == "end" else index_size
                # Inner chunks (0, 0), (0, 1) (not written), (1, 0) and (1, 1) of a shard of 2 x 2 inner chunks.
                entries = np.array([[data_start, 10], [empty, empty], [data_start + 10, 5], [data_start + 15, 5]], dtype="<u8")
                index = bytes(CRC32C().encode(entries.tobytes()))
                shard = b"x" * 20 + index if location == "end" else index + b"x" * 20
                # The shard starts at offset 100 in the tarball.
                tarball = b"." * 100 + shard
                refs = shardChunkReferences(["file:///t.tar", 100, len(shard)], "0.0", layout, lambda url, start, end: tarball[start:end])
                base = 100 + data_start
                self.assertEqual(refs, [
                    ("0.0", ["file:///t.tar", base, 10]),
                    ("1.0", ["file:///t.tar", base + 10, 5]),
                    ("1.1", ["file:///t.tar", base + 15, 5]),
                ])

        entries = np.array([[0, 10], [empty, empty], [10, 5], [15, 5]], dtype="<u8").tobytes()
        layout = v3ShardingLayout(self._sharded_meta())
        shard = b"x" * 20 + bytes(CRC32C().encode(entries))
        # Shard (1, 1) of an array of 6 x 7: inner chunk rows 2-3 and columns 2-3, of which only (2, 2)
        # lies within the array's grid of 3 x 3 inner chunks.
        refs = shardChunkReferences(["file:///t.tar", 0, len(shard)], "1.1", layout, lambda url, start, end: shard[start:end])
        self.assertEqual(refs, [("2.2", ["file:///t.tar", 0, 10])])
        corrupted = shard[:-1] + bytes([shard[-1] ^ 1])
        with self.assertRaisesRegex(ValueError, "checksum"):
            shardChunkReferences(["file:///t.tar", 0, len(corrupted)], "0.0", layout, lambda url, start, end: corrupted[start:end])

    def _kerchunk_roundtrip(self, tmp_path, store_dir):
        import fsspec
        import xarray as xr

        from zarrcurator import utils
        from zarrcurator.config import configObj

        configObj.setWorkingDir(str(tmp_path))
        tar_path = tmp_path / "hp_001.tar"
        with tarfile.open(tar_path, "w") as tf:
            tf.add(store_dir, arcname=store_dir.name)
        with redirect_stdout(io.StringIO()):
            utils.createKerchunkReferenceFileForTar(str(tar_path))
            utils.convertKerchunkReferenceFilesOfZarrStoreToParquet(str(store_dir))
        mapper = fsspec.get_mapper("reference://", fo=str(tmp_path / "hp.parq"), remote_protocol="file")
        return xr.open_dataset(mapper, engine="zarr", consolidated=False, zarr_format=2)

    def test_kerchunk_parquet_roundtrip_of_sharded_v3_store(self):
        import pandas as pd
        import xarray as xr

        values = np.arange(10 * 7, dtype="f4").reshape(10, 7)
        # An inner chunk holding only the fill value is not written; edge shards and chunks.
        values[2:4, 0:3] = np.nan
        ds = xr.Dataset(
            {"tas": (("time", "cell"), values), "orog": (("cell",), np.arange(7, dtype="i2"))},
            coords={"time": pd.date_range("2020-01-01", periods=10, freq="D"), "crs": ((), 0, {"grid_mapping_name": "healpix"})},
        )
        encodings = {
            "default": {"tas": {"chunks": (2, 3), "shards": (4, 6)}},
            "v2 key encoding": {"tas": {"chunks": (2, 3), "shards": (4, 6), "chunk_key_encoding": {"name": "v2", "separator": "."}}},
            "blosc": {"tas": {"chunks": (2, 3), "shards": (4, 6),
                              "compressors": [zarr.codecs.BloscCodec(cname="zstd", clevel=3, shuffle="bitshuffle")]}},
            "1-d sharded too": {"tas": {"chunks": (2, 3), "shards": (4, 6)}, "orog": {"chunks": (2,), "shards": (4,)}},
        }
        for label, encoding in encodings.items():
            with self.subTest(encoding=label), tempfile.TemporaryDirectory() as tmpdir:
                store_dir = Path(tmpdir) / "hp.zarr"
                ds.to_zarr(store_dir, zarr_format=3, consolidated=True, encoding=encoding)
                self.assertTrue(self._kerchunk_roundtrip(Path(tmpdir), store_dir).identical(ds))

    def test_kerchunk_parquet_roundtrip_of_shard_index_layouts(self):
        from zarr.codecs import BytesCodec, ShardingCodec, ZstdCodec

        values = np.arange(10 * 7, dtype="f4").reshape(10, 7)
        for location, index_codecs in (("start", None), ("end", [BytesCodec()])):
            with self.subTest(index_location=location, checksum=index_codecs is None), tempfile.TemporaryDirectory() as tmpdir:
                store_dir = Path(tmpdir) / "hp.zarr"
                group = zarr.open_group(str(store_dir), mode="w", zarr_format=3)
                kwargs = {} if index_codecs is None else {"index_codecs": index_codecs}
                sharding = ShardingCodec(chunk_shape=(2, 3), codecs=[BytesCodec(), ZstdCodec()], index_location=location, **kwargs)
                array = group.create_array("tas", shape=values.shape, dtype="f4", chunks=(4, 6), serializer=sharding,
                                           compressors=None, dimension_names=["time", "cell"])
                array[:] = values
                reopened = self._kerchunk_roundtrip(Path(tmpdir), store_dir)
                np.testing.assert_array_equal(reopened["tas"].values, values)

    def test_kerchunk_parquet_keeps_unwritten_chunks_missing(self):
        """Chunks holding only the fill value are not written; they must read as fill value, not garbage."""
        import xarray as xr

        values = np.arange(60, dtype="f4").reshape(10, 6)
        values[2:4, 0:2] = np.nan
        ds = xr.Dataset({"tas": (("time", "cell"), values)})
        for zarr_format in (2, 3):
            # 15 chunks with one URL: fsspec would store the URLs as categoricals by default.
            with self.subTest(zarr_format=zarr_format), tempfile.TemporaryDirectory() as tmpdir:
                store_dir = Path(tmpdir) / "hp.zarr"
                ds.to_zarr(store_dir, zarr_format=zarr_format, consolidated=True, encoding={"tas": {"chunks": (2, 2)}})
                self.assertTrue(self._kerchunk_roundtrip(Path(tmpdir), store_dir).identical(ds))

    def test_kerchunk_reports_corrupted_shard_index(self):
        import xarray as xr

        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "hp.zarr"
            ds = xr.Dataset({"tas": (("time", "cell"), np.ones((4, 6), "f4"))})
            ds.to_zarr(store_dir, zarr_format=3, encoding={"tas": {"chunks": (1, 3), "shards": (2, 6)}})
            shard = store_dir / "tas" / "c" / "1" / "0"
            content = shard.read_bytes()
            shard.write_bytes(content[:-1] + bytes([content[-1] ^ 1]))
            with self.assertRaisesRegex(ValueError, "checksum"):
                self._kerchunk_roundtrip(Path(tmpdir), store_dir)


@unittest.skipUnless(np is not None and zarr is not None, "requires numpy, zarr")
class TestSyntheticStoreVariants(unittest.TestCase):
    """Every store variant of the synthetic generator runs through the xarray check and the kerchunk step."""

    def test_variants_open_with_xarray_and_roundtrip_through_kerchunk(self):
        import warnings

        import xarray as xr

        from zarrcurator import synthetic_store, utils
        from zarrcurator.config import configObj

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            manifest = synthetic_store.create_synthetic_experiment(
                output_dir=tmp_path / "exp",
                experiment_name="syntheticexp",
                frequencies=["P1D"],
                stores_per_frequency=1,
                start_zoom=1,
                zarr_formats=[2, 3],
                inject_anomalies=False,
                clean=False,
                separators=[".", "/"],
                shards=(4, 4, 8),
                layouts=["flat", "tree"],
            )
            self.assertEqual(len(manifest["stores"]), 12)
            for entry in manifest["stores"]:
                with self.subTest(store=entry["store"]):
                    store_dir = tmp_path / "exp" / entry["store"]
                    name = store_dir.name[: -len(".zarr")]
                    work_dir = tmp_path / name
                    work_dir.mkdir()
                    utils.checkStoreOpensWithXarray(str(store_dir), entry["store"])

                    tar_path = work_dir / f"{name}_001.tar"
                    with tarfile.open(tar_path, "w") as tf:
                        tf.add(store_dir, arcname=store_dir.name)
                    configObj.setWorkingDir(str(work_dir))
                    with redirect_stdout(io.StringIO()):
                        utils.createKerchunkReferenceFileForTar(str(tar_path))
                        utils.convertKerchunkReferenceFilesOfZarrStoreToParquet(str(store_dir))

                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", RuntimeWarning)
                        original = xr.open_datatree(store_dir, engine="zarr")
                    reopened = xr.open_datatree(
                        "reference://",
                        engine="zarr",
                        consolidated=True,
                        zarr_format=2,
                        storage_options={"fo": str(work_dir / f"{name}.parq"), "remote_protocol": "file"},
                    )
                    expected_groups = ["/", "/atmos", "/atmos/ocean"] if entry["layout"] == "tree" else ["/"]
                    self.assertEqual([node.path for node in reopened.subtree], expected_groups)
                    self.assertTrue(reopened.identical(original))


class TestPackageInitAndExistingTestsModule(unittest.TestCase):
    """Package exports and importing the regression tests."""

    def test_import_init(self):
        mod = importlib.import_module("zarrcurator")
        #self.assertTrue(hasattr(mod, "hello"))
        self.assertTrue(hasattr(mod, "utils"))

    def test_set_object_store_credentials_is_exported(self):
        mod = importlib.import_module("zarrcurator")
        self.assertTrue(hasattr(mod, "setObjectStoreCredentials"))

    def test_import_existing_regression_module(self):
        mod = importlib.import_module("tests.regression_test")
        self.assertTrue(hasattr(mod, "RegressionFixesTest"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
