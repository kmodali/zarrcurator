"""
This module contains certain utility functions that will be exposed to the user to perform various tasks.
"""
#Standard modules
import logging
import os
import sys
import json
import time
import glob
import shutil
import tarfile
import concurrent.futures
from copy import deepcopy as copy
from rich import print as richprint


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

#Non-Standard modules
try:
    import pyslk
except:
    logger.exception("Module 'pyslk' import error in %s", __file__)

try:
    from tqdm import tqdm
except:
    logger.exception("Module 'tqdm' import error in %s", __file__)
    
try:
    from kerchunk.df import refs_to_dataframe
except:
    logger.exception("Module 'kerchunk' import error in %s", __file__)
    
try:
    import pandas as pd
except:
    logger.exception("Module 'pandas' import error in %s", __file__)
    
try:
    import ujson
except:
    logger.exception("Module 'ujson' import error in %s", __file__)
    
try:
    import fsspec
except:
    logger.exception("Module 'fsspec' import error in %s", __file__)

try:
    import s3fs
except:
    logger.exception("Module 's3fs' import error in %s", __file__)

try:
    import xarray as xr
except:
    logger.exception("Module 'xarray' import error in %s", __file__)

#Local modules
try:
    from .config import configObj
except:
    logger.exception("Module 'config' import error in %s", __file__)

try:    
    from .diagnoser import Diagnoser
except:
    logger.exception("Module 'diagnoser' import error in %s", __file__)

try:    
    from .displayer import Displayer
except:
    logger.exception("Module 'displayer' import error in %s", __file__)

try:    
    from .distributor import Distributor
except:
    logger.exception("Module 'distributor' import error in %s", __file__)

try:
    from .dispatcher import Dispatcher
except:
    logger.exception("Module 'dispatcher' import error in %s", __file__)

try:
    from .chunkkeys import parseChunkKey, numThreadsForChunks, maxThreads, arrayWorkers
except:
    logger.exception("Module 'chunkkeys' import error in %s", __file__)

try:
    from .storetree import listArrayPaths, nestDiagReport, flattenDiagReport, nestDistReport
except:
    logger.exception("Module 'storetree' import error in %s", __file__)

try:
    from .zarrmetadata import v3MetadataToV2, v3ChunkKeyToV2, v3ShardingLayout, shardChunkReferences
except:
    logger.exception("Module 'zarrmetadata' import error in %s", __file__)

try:
    from .subgroup import subGroup_to_dict
except:
    logger.exception("Module 'subgroup' import error in %s", __file__)


def usage():
    """Help about the usage of zarrcurator.
    Returns: 
            None.
    """
    print("Zarrcurator has the following APIs:")
    print("usage() - Show this API help.")
    print("saveConfigToFile(configFileName) - Save zarrcurator configuration to JSON.")
    print("loadConfigFromFile(configFileName) - Load zarrcurator configuration from JSON.")
    print("setObjectStoreCredentials(accessKey=None, secretKey=None) - Set object-store credentials using values or env-var names.")
    print("initialize(expPath, workDir, jsonFile, targetSize, batchMode, debugMode, packDiscontinuousData, accessKey=None, secretKey=None) - Initialize runtime configuration.")
    print("findMissingChunksInStore(storeLocation, accessKey=None, secretKey=None, checkpointSignal=None) - Detect missing/zero-size/unexpected/corrupt chunks.")
    print("diagnose() - Diagnose configured experiment path and update diagnoser state.")
    print("diagnoseStore(storeLocation, accessKey=None, secretKey=None) - Diagnose a single zarr store and write '.diag' output.")
    print("display() - Display experiment-level plots from diagnoser output.")
    print("displayStoreSunburst(storeLocation, accessKey=None, secretKey=None) - Display sunburst for a single store.")
    print("displayZarrStoreVariables(zarrStore, fileCount, byteBins) - Plot variable-level counts/sizes for a store.")
    print("distribute() - Build subgroups for configured experiment diagnoser output.")
    print("distributeStoreToSubStores(storeLocation) - Build subgroups for a single store and write '.dist' output.")
    print("dispatchStoreToTarStores(storeLocation, accessKey=None, secretKey=None) - Create tarballs for the subgroups of a single store, running diagnosis and distribution first if '.diag'/'.dist' are missing.")
    print("createKerchunkReferenceFileForTar(tarFileName) - Create a kerchunk reference file for a tarball.")
    print("updateArchBasePath(archBasePath) - Set HSM archive base path for tape mapping.")
    print("mapTapeIDsToFrequencySubGroupDict() - Map tar files to tape IDs and write 'subGroupTarTape.json'.")
    print("displayZarrStoresTarTapes() - Plot tarball and tape counts for all zarr stores.")
    print("displayZarrStoreVarTarTapes(zarrStoreInput, varInput) - Plot tarball and tape counts for selected variables.")


def saveConfigToFile( configFileName ):
    """Saving the zarrcurator config to file.

    Saving the zarrcurator library configuration as a JSON file.

    Args:
            configFileName    : File name in which to store the configuration.
    Returns:
            None.
    """

    configObj.toFile( configFileName )
    print(f"Configuration saved to file {configFileName}")


def loadConfigFromFile( configFileName ):
    """Loading the zarrcurator config from file.

    Reading the zarrcurator library configuration from a JSON file.

    Args:
            configFileName    : File name in which to store the configuration.
    Returns:
            None.
    """

    if not os.path.isfile( configFileName ):
        print( f"Error:{configFileName} doesn't exist!!!" )
        sys.exit()

    print(f"Configuration loading from file {configFileName}")
    configObj.fromFile( configFileName )


def setObjectStoreCredentials(accessKey=None, secretKey=None):
    """Set object-store credentials for the current process.

    Accepts either raw key values or environment variable names that contain
    those values. Resolved values are exported to AWS/S3 standard environment
    variables and wired into configObj for downstream filesystem creation.

    Args:
            accessKey[str]: Access key value or env-var name containing it.
            secretKey[str]: Secret key value or env-var name containing it.
    Returns:
            None.
    """

    if accessKey is None and secretKey is None:
        return

    if not accessKey or not secretKey:
        raise ValueError("Both accessKey and secretKey must be provided together")

    # Treat user input as env-var names when available, otherwise as literal values.
    resolved_access_key = os.getenv(accessKey, accessKey)
    resolved_secret_key = os.getenv(secretKey, secretKey)

    os.environ["AWS_ACCESS_KEY_ID"] = resolved_access_key
    os.environ["AWS_SECRET_ACCESS_KEY"] = resolved_secret_key
    os.environ["S3_ACCESS_KEY_ID"] = resolved_access_key
    os.environ["S3_SECRET_ACCESS_KEY"] = resolved_secret_key

    # Keep config in sync by pointing to standard env vars.
    configObj.setaccessKey("AWS_ACCESS_KEY_ID")
    configObj.setsecretKey("AWS_SECRET_ACCESS_KEY")


def updateStoretoConfig( storeLocation, accessKey=None, secretKey=None ):
    """Update the store location to the config object.

    To update the store location to the config object, to be used by other functions in the zarrcurator library.

    Args:
            storeLocation[str]: Location of the zarr store.
            accessKey[str]: Optional access key value/env-var name.
            secretKey[str]: Optional secret key value/env-var name.
    Returns:
            None.
    """
    #import s3fs
    import zarr
    import fsspec

    setObjectStoreCredentials(accessKey=accessKey, secretKey=secretKey)

    configObj.setWorkingDir( os.getcwd() )
    configObj.setZarrStorePath( storeLocation )
    
    # getZarrStorePath returns without URL scheme if the store is on object storage, 
    # else returns the path as it is for local store
    zarrPath = configObj.getZarrStorePath()    
    fs = configObj.getFileSystemObj()

    if fs is not None:
        #store = s3fs.S3Map( root = zarrPath, s3=fs, check=False )
        logger.info("Object store path resolved: %s", zarrPath)
        if logger.isEnabledFor(logging.DEBUG):
            try:
                listing = fs.ls(zarrPath)
            except Exception as exp:
                logger.debug("Object store listing unavailable for %s: %s", zarrPath, exp)
            else:
                logger.debug("Object store listing for %s: %s", zarrPath, listing)
        mapper = fs.get_mapper(zarrPath)
        try:
            store = zarr.open(mapper, mode="r")
        except PermissionError as exp:
            err_text = str(exp)
            # If credentials are present but invalid, retry anonymously.
            if "InvalidAccessKeyId" in err_text or "Access Key Id" in err_text:
                logger.warning("Credentialed S3 access failed for %s; retrying anonymously", zarrPath)
                client_kwargs = getattr(fs, "client_kwargs", None) or {}
                anon_fs = fsspec.filesystem("s3", client_kwargs=client_kwargs, anon=True)
                mapper = anon_fs.get_mapper(zarrPath)
                try:
                    store = zarr.open(mapper, mode="r")
                    fs = anon_fs
                    configObj.fileSystemObj = anon_fs
                except PermissionError as exp2:
                    raise PermissionError(
                        f"Access denied for object store path '{zarrPath}'. "
                        "Both credentialed and anonymous access failed. "
                        "Provide valid S3 credentials via configObj.setaccessKey('<ACCESS_KEY_ENV>')/"
                        "setsecretKey('<SECRET_KEY_ENV>') "
                        "or AWS/S3 environment variables, or verify public-read permissions."
                    ) from exp2
            else:
                raise PermissionError(
                    f"Access denied for object store path '{zarrPath}'. "
                    "Provide valid credentials or verify object permissions."
                ) from exp
        logger.info("Store opened path=%s", zarrPath)
        if logger.isEnabledFor(logging.DEBUG):
            try:
                listing = fs.ls(zarrPath)
            except Exception as exp:
                logger.debug("Store file listing unavailable for %s: %s", zarrPath, exp)
            else:
                logger.debug("Store files for %s: %s", zarrPath, listing)
    else:
        store = zarrPath
        
    storeName = zarrPath.split(os.path.sep)[-1]

    return fs, store, storeName


def nestCheckReport( flatReport ):
    """Nest a check report keyed by array path by its groups.

    ``{"/z2/ocean/sst": {...}}`` becomes ``{"z2": {"ocean": {"sst": {...}}}}``.
    Array entries are marked with ``"type": "array"`` and carry their ``path``;
    all other dicts are groups.

    Args:
            flatReport[dict]: Report keyed by array path.
    Returns:
            dict: Report nested by group.
    """

    nested = {}
    for path, entry in flatReport.items():
        parts = [p for p in path.split("/") if p]
        node = nested
        for group in parts[:-1]:
            node = node.setdefault(group, {})
        node[parts[-1]] = {"type": "array", "path": "/" + "/".join(parts), **entry}
    return nested


def flattenCheckReport( nestedReport ):
    """Flatten a check report nested by group to one keyed by array path.

    The inverse of nestCheckReport; a report that is already keyed by array
    path (written by older versions) is returned as it is.

    Args:
            nestedReport[dict]: Report nested by group.
    Returns:
            dict: Report keyed by array path, e.g. ``/z2/ocean/sst``.
    """

    if any(key.startswith("/") for key in nestedReport):
        return dict(nestedReport)

    flat = {}

    def walk(node, prefix):
        for name, child in node.items():
            if not isinstance(child, dict):
                continue
            if child.get("type") == "array":
                entry = {k: v for k, v in child.items() if k not in ("type", "path")}
                flat[f"{prefix}/{name}"] = entry
            else:
                walk(child, f"{prefix}/{name}")

    walk(nestedReport, "")
    return flat


def findMissingChunksInStore( storeLocation, accessKey=None, secretKey=None, checkpointSignal=None ):
    """Finding missing chunks in a zarr store.

    To find chunks in store that are missing, artifacts, corrupt or zero sized.
    All arrays are checked, including those in nested groups (e.g. a store
    written from an xarray DataTree).
    When ZARRCURATOR_MULTITHREAD=1, several arrays are checked at once (see
    arrayWorkers, ZARRCURATOR_ARRAY_WORKERS), and their chunk size queries and
    chunk readability (corruption) checks run in two thread pools shared by all
    arrays, sized by the available CPUs (see maxThreads); each array keeps at most
    as many chunks in progress as numThreadsForChunks gives for its number of chunks.
    The ``<store>.check`` report is nested by group (see nestCheckReport;
    flattenCheckReport gives it keyed by array path) and is rewritten after
    each array. If it already
    exists, it is loaded and the arrays it lists (with unchanged shape, chunks
    and shards) are skipped, so the check of a large store can be resumed in
    a later session. Delete the report to check all arrays again.

    Arrays are written to the report only when finished. With checkpointSignal
    (e.g. signal.SIGUSR1, sent by SLURM shortly before the time limit), the
    chunks checked so far in the unfinished arrays are saved to
    ``<store>.check.partial`` when that signal arrives, and a later session
    reads only the remaining chunks of those arrays. The partial file is
    removed when all arrays are checked. Without checkpointSignal, an
    interrupted array is checked again from its start.

    Args:
            storePath    : Path of the zarr store.
            accessKey[str]: Optional access key value/env-var name.
            secretKey[str]: Optional secret key value/env-var name.
            checkpointSignal: Optional signal (e.g. signal.SIGUSR1) that saves the
                              progress of the unfinished arrays; the handler is
                              installed only when called from the main thread.
    Returns:
            None.
    """

    import math
    import signal
    import threading
    import zarr
    import s3fs
    import itertools
    import numpy as np
    import concurrent.futures
    from concurrent.futures import ThreadPoolExecutor

    def get_chunk_size(var_path, chunk_rel_path):
        """Return chunk size in bytes for local and object stores."""

        if fs is not None:
            chunk_path = os.path.join(var_path, chunk_rel_path)
            try:
                return fs.info(chunk_path).get("size", 0)
            except Exception as exp:
                logger.debug("Unable to query chunk size for %s: %s", chunk_path, exp)
                return None

        chunk_path = os.path.join(var_path, chunk_rel_path)
        try:
            return os.path.getsize(chunk_path)
        except OSError as exp:
            logger.debug("Unable to query chunk size for %s: %s", chunk_path, exp)
            return None

    # build expected chunk keys
    def chunk_keys(grid):
        for idx in itertools.product(*[range(g) for g in grid]):
            yield ".".join(map(str, idx))

    def map_chunks(func, items, ioBound=True):
        """Apply func to items, in parallel when multithreading is enabled.

        The items run in the thread pool shared by all arrays, the I/O pool for I/O-bound work
        (e.g. size queries) or the CPU pool for CPU-bound work (e.g. reading and decompressing
        chunks). At most numThreadsForChunks(len(items)) items of one array are in progress at
        once, so that the arrays checked at once share the pool. The results keep the order of
        the items.
        """

        items = list(items)
        limit = numThreadsForChunks( len(items), ioBound=ioBound )
        if not multiThread or limit <= 1:
            return [ func(item) for item in items ]
        pool = ioPool if ioBound else cpuPool
        logger.debug("map_chunks chunks=%d in_progress=%d io_bound=%s", len(items), limit, ioBound)
        results = [None] * len(items)
        inProgress = {}
        for index, item in enumerate(items):
            if len(inProgress) >= limit:
                finished, _ = concurrent.futures.wait( inProgress, return_when=concurrent.futures.FIRST_COMPLETED )
                for future in finished:
                    results[ inProgress.pop(future) ] = future.result()
            inProgress[ pool.submit(func, item) ] = index
        for future in concurrent.futures.as_completed( inProgress ):
            results[ inProgress[future] ] = future.result()
        return results

    #STORE = "s3://my-bucket/my-array"
    CHECK_CORRUPTION = True

    threadFlag = os.getenv('ZARRCURATOR_MULTITHREAD')
    multiThread = threadFlag == '1'
    logger.info(
        "findMissingChunksInStore store=%s mode=%s flag=%s",
        storeLocation,
        "multi-thread" if multiThread else "single-thread",
        threadFlag,
    )

    def load_report(reportFile):
        """Load an existing report keyed by array path; also accepts the older
        flat and appended formats."""

        if not os.path.exists(reportFile):
            return {}
        with open(reportFile) as f:
            text = f.read()
        try:
            return flattenCheckReport(json.loads(text))
        except json.JSONDecodeError:
            pass
        # Older versions appended the full report after each array, so the
        # file holds several JSON objects; the last complete one has them all.
        decoder = json.JSONDecoder()
        loaded, pos = {}, 0
        while True:
            while pos < len(text) and text[pos].isspace():
                pos += 1
            if pos >= len(text):
                break
            try:
                loaded, pos = decoder.raw_decode(text, pos)
            except json.JSONDecodeError:
                logger.warning("Ignoring unreadable part of %s", reportFile)
                break
        return flattenCheckReport(loaded) if isinstance(loaded, dict) else {}

    def save_report(reportFile):
        """Write the report atomically so an interrupted run keeps a valid file.

        The arrays are written in the order of the store, whatever order they were checked in.
        """

        ordered = { path: report[path] for path in arrayPaths if path in report }
        ordered.update( { path: entry for path, entry in report.items() if path not in ordered } )
        tmpFile = f"{reportFile}.tmp"
        with open(tmpFile, "w") as f:
            json.dump(nestCheckReport(ordered), f, indent=2)
        os.replace(tmpFile, reportFile)

    def as_list(value):
        return None if value is None else list(value)

    # Progress of the arrays being checked, saved on checkpointSignal: array path ->
    # shape, chunks, shards, chunks checked and corrupt chunks found so far
    progress = {}
    progressLock = threading.Lock()

    def load_partial(partialFile):
        if not os.path.exists(partialFile):
            return {}
        try:
            with open(partialFile) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as exp:
            logger.warning("Ignoring unreadable %s: %s", partialFile, exp)
            return {}

    def save_partial(partialFile):
        """Write the progress of the unfinished arrays atomically."""

        with progressLock:
            saved = { path: entry for path, entry in resumeFrom.items() if path not in report }
            for path, entry in progress.items():
                saved[path] = dict( entry, checked=list(entry["checked"]), corrupt=list(entry["corrupt"]) )
        tmpFile = f"{partialFile}.tmp"
        with open(tmpFile, "w") as f:
            json.dump(saved, f)
        os.replace(tmpFile, partialFile)
        chunks = sum( len(entry["checked"]) for entry in saved.values() )
        print( f"progress of {len(saved)} unfinished array(s) ({chunks} chunks checked) written to {partialFile}", flush=True )
        logger.info("findMissingChunksInStore checkpoint arrays=%d chunks=%d file=%s", len(saved), chunks, partialFile)

    report = {}
    results = {
        "unexpected": [],
        "missing": [],
        "zero_size": [],
        "corrupt": []
    }    

    fs, store, storeName = updateStoretoConfig(
        storeLocation,
        accessKey=accessKey,
        secretKey=secretKey,
    )
    zarrPath = configObj.getZarrStorePath()    

    reportFile = f"{storeName.split('.')[0]}.check"
    report = load_report(reportFile)
    if report:
        print( f"resuming from {reportFile}: {len(report)} array(s) already checked" )
    partialFile = f"{reportFile}.partial"
    resumeFrom = load_partial(partialFile)
    if resumeFrom:
        print( f"resuming from {partialFile}: {len(resumeFrom)} array(s) partly checked" )

    print(type(store),flush=True)
    store_target = store.store if isinstance(store, zarr.core.group.Group) else store
    try:
        root = zarr.open_consolidated(store_target, mode="r")
    except Exception as exp:
        # zarr v3 stores may not provide consolidated metadata in the v2 layout.
        print(f"open_consolidated failed for {storeLocation}: {exp}; falling back to open_group()")
        root = zarr.open_group(store_target, mode="r")


    def is_checked(varName):
        """Whether the report lists the array already, with unchanged shape, chunks and shards."""
        array = root[varName]
        done = report.get("/" + array.name.strip("/"))
        return done is not None and \
            as_list(done.get("shape")) == as_list(array.shape) and \
            as_list(done.get("chunks")) == as_list(array.chunks) and \
            as_list(done.get("shards")) == as_list(array.shards)

    def check_array(varName):
        """Check one array; returns its path and its report entry."""

        def say(*message):
            # Several arrays are checked at once: label the lines with the array
            if parallelArrays:
                print( f"[{varName}]", *message, flush=True )
            else:
                print( *message, flush=True )

        array = root[varName]

        arrayPath = "/" + array.name.strip("/")

        # Time each array, so the rate of the check can be computed from the log
        started = time.perf_counter()
        logger.info("check_array start %s", arrayPath)

        # Handle shards
        var_path = os.path.join(zarrPath, varName)
        if fs is not None:
            raw_objects = fs.find(var_path)
            relative_objects = [
                obj[len(var_path.rstrip("/") + "/") :]
                if obj.startswith(var_path.rstrip("/") + "/")
                else obj.split("/")[-1]
                for obj in raw_objects
            ]
        else:
            var_root = var_path
            relative_objects = []
            for root_dir, _, files in os.walk(var_root):
                for file_name in files:
                    rel = os.path.relpath(os.path.join(root_dir, file_name), var_root)
                    relative_objects.append(rel)

        metadata_names = {".zarray", ".zattrs", "zarr.json"}
        actualList = [obj for obj in relative_objects if obj not in metadata_names and not obj.startswith(".")]
        actual = len(actualList)
        
        say( f"Scanning array: {varName} Shape: {array.shape}"  )
        say( f"Scanning array: {varName} Chunks: {array.chunks}"  )        
        if array.shards is not None:
            say( f"Scanning array: {varName} Shards: {array.shards}"  )
            grid = [math.ceil(s / c) for s, c in zip(array.shape, array.shards)]
        else:
            grid = [math.ceil(s / c) for s, c in zip(array.shape, array.chunks)]

        expected = math.prod(grid)
        say( f"Chunk count Expected : {expected} Actual : {actual}" )
        if actual > expected :
            results[ "unexpected" ].append( ( array.name, actual - expected ) )


        say( "expected chunks:", expected )

        # list actual objects
        say( "listing objects..." )
        objects = []

        objects.extend(actualList)

        actual = set(objects)
        numeric_chunks = set()

        say( "found objects:", len(actual) )

        # detect unexpected objects
        unexpected = []
        zero_size = []

        coord_to_name = {}
        for k in actual:
            coord = parseChunkKey(k)
            if coord is not None:
                numeric_chunks.add(k)
                # Preserve one representative path per coordinate for readability checks.
                coord_to_name[coord] = k
            else:
                unexpected.append(k)

        numeric_chunk_list = sorted(numeric_chunks)
        chunk_sizes = map_chunks(lambda k: get_chunk_size(var_path, k), numeric_chunk_list)
        zero_size = [k for k, chunk_size in zip(numeric_chunk_list, chunk_sizes) if chunk_size == 0]

        say( "unexpected objects:", len(unexpected) )

        # detect missing based on numeric chunk names only
        missing = []

        actual_coords = set(coord_to_name.keys())
        for k in chunk_keys(grid):
            coord = tuple(map(int, k.split(".")))
            if coord not in actual_coords:
                missing.append(k)

        say( "missing chunks:", len(missing) )
        say( "zero-size chunks:", len(zero_size) )

        # corruption test
        corrupt = []
        toCheck = numeric_chunk_list

        if CHECK_CORRUPTION:
            # Chunks checked in an earlier session that was interrupted (see checkpointSignal)
            prior = resumeFrom.get(arrayPath)
            if prior is not None and not (
                    as_list(prior.get("shape")) == as_list(array.shape) and
                    as_list(prior.get("chunks")) == as_list(array.chunks) and
                    as_list(prior.get("shards")) == as_list(array.shards)):
                prior = None
            done = set(prior["checked"]) & numeric_chunks if prior else set()
            entry = {
                "shape": as_list(array.shape),
                "chunks": as_list(array.chunks),
                "shards": as_list(array.shards),
                "checked": list(done),
                "corrupt": [k for k in prior["corrupt"] if k in done] if prior else [],
            }
            with progressLock:
                progress[arrayPath] = entry
            if done:
                say( f"resuming: {len(done)} of {len(numeric_chunk_list)} chunks checked in an earlier session" )
            toCheck = [k for k in numeric_chunk_list if k not in done]

            say( "checking chunk readability..." )

            def check_chunk(chunkname):
                #print(  f"processing: {varName}/{chunkname}" )
                idx = parseChunkKey(chunkname)
                if idx is None:
                    return None
                try:
                    _ = root[varName].blocks[idx][:]
                    result = None
                except Exception as exp:
                    say(  f"var: {varName} corrupt chunk: {chunkname} {idx} error: {exp}" )
                    result = chunkname
                with progressLock:
                    entry["checked"].append(chunkname)
                    if result:
                        entry["corrupt"].append(chunkname)
                return result

            # Reading and decompressing the chunks is CPU-bound
            map_chunks(check_chunk, toCheck, ioBound=False)
            # In the order of the chunks, also those found in an earlier session
            found = set(entry["corrupt"])
            corrupt = [k for k in numeric_chunk_list if k in found]

        say( "corrupt chunks:", len(corrupt) )

        # Bytes read in this session (chunks checked in an earlier session are not read again)
        elapsed = time.perf_counter() - started
        readNow = set(toCheck)
        nbytes = sum( size for k, size in zip(numeric_chunk_list, chunk_sizes) if size and k in readNow )
        rate = nbytes / elapsed / 1e9 if elapsed > 0 else 0.0
        say( f"checked in {elapsed:.1f} s: {nbytes} bytes ({nbytes / 2**30:.2f} GiB) "
             f"in {len(toCheck)} chunks, {rate:.3f} GB/s" )
        logger.info("check_array end %s seconds=%.1f bytes=%d chunks=%d rate_gbps=%.3f",
                    arrayPath, elapsed, nbytes, len(toCheck), rate)

        return arrayPath, {
            "shape": array.shape,
            "shards": array.shards,
            "chunks": array.chunks,
            "expected_chunks": expected,
            "found_chunks": len(actual),
            "missing": missing,
            "zero_size": zero_size,
            "corrupt": corrupt,
            "unexpected": unexpected,
        }

    arrayNames = listArrayPaths(root)
    arrayPaths = [ "/" + root[varName].name.strip("/") for varName in arrayNames ]
    todo = []
    for varName in arrayNames:
        if is_checked(varName):
            print( f"Skipping array: {varName} (already checked in {reportFile})" )
        else:
            todo.append(varName)

    def record(arrayPath, entry):
        """Add a finished array to the report; it is no longer partly checked."""
        with progressLock:
            report[arrayPath] = entry
            progress.pop(arrayPath, None)

    # On checkpointSignal the handler only sets an event; a helper thread writes the
    # partial file, so the handler never waits for a lock held by the interrupted code
    checkpointRequested = threading.Event()
    stopWatcher = threading.Event()

    def watch_checkpoint():
        while True:
            checkpointRequested.wait()
            if stopWatcher.is_set():
                return
            checkpointRequested.clear()
            try:
                save_partial(partialFile)
            except Exception:
                logger.exception("Unable to write %s", partialFile)

    previousHandler = None
    watcher = None
    if checkpointSignal is not None:
        if threading.current_thread() is threading.main_thread():
            previousHandler = signal.signal( checkpointSignal, lambda signum, frame: checkpointRequested.set() )
            watcher = threading.Thread( target=watch_checkpoint, name="zarrcurator-checkpoint", daemon=True )
            watcher.start()
            print( f"progress of unfinished arrays is saved to {partialFile} on signal {signal.Signals(checkpointSignal).name}", flush=True )
        else:
            logger.warning("checkpointSignal ignored: findMissingChunksInStore is not running in the main thread")

    numArrayWorkers = min( arrayWorkers(), len(todo) ) if multiThread else 1
    parallelArrays = numArrayWorkers > 1
    if multiThread:
        # Thread pools shared by all arrays checked at once, sized by the available CPUs
        ioPool = ThreadPoolExecutor( max_workers=maxThreads(ioBound=True) )
        cpuPool = ThreadPoolExecutor( max_workers=maxThreads(ioBound=False) )
        logger.info("findMissingChunksInStore arrays=%d arrays_at_once=%d io_threads=%d cpu_threads=%d",
                    len(todo), numArrayWorkers, maxThreads(ioBound=True), maxThreads(ioBound=False))
    try:
        if parallelArrays:
            arrayPool = ThreadPoolExecutor( max_workers=numArrayWorkers )
            futures = { arrayPool.submit(check_array, varName): varName for varName in todo }
            try:
                for future in concurrent.futures.as_completed( futures ):
                    arrayPath, entry = future.result()
                    record(arrayPath, entry)
                    # Update after each array, so the check can be resumed
                    save_report(reportFile)
            except BaseException:
                # Keep the arrays finished by the other threads for the next session: the arrays
                # not started are cancelled, the running ones are finished
                arrayPool.shutdown( wait=True, cancel_futures=True )
                for future in futures:
                    if future.done() and not future.cancelled() and future.exception() is None:
                        arrayPath, entry = future.result()
                        record(arrayPath, entry)
                save_report(reportFile)
                raise
            finally:
                arrayPool.shutdown( wait=True, cancel_futures=True )
        else:
            for varName in todo:
                arrayPath, entry = check_array(varName)
                record(arrayPath, entry)
                # Update after each array, so the check can be resumed
                save_report(reportFile)
    finally:
        if multiThread:
            ioPool.shutdown( wait=True, cancel_futures=True )
            cpuPool.shutdown( wait=True, cancel_futures=True )
        if watcher is not None:
            signal.signal( checkpointSignal, previousHandler )
            stopWatcher.set()
            checkpointRequested.set()
            watcher.join()

    save_report(reportFile)
    print( f"report written to {reportFile}" )
    if os.path.exists(partialFile):
        os.remove(partialFile)


def initialize( expPath, workDir, jsonFile, targetSize,
                batchMode, debugMode, packDiscontinuousData,
                accessKey=None, secretKey=None ):
    """Initializing the zarrcurator.

    Initialize the zarrcurator library configuration with the paths, flags etc.

    Args:
            expPath    : Directory under which the simulation data (zarr stores) exists.
            workDir    : Working directory where the output will be stored.
            jsonFile   : Name of the JSON file in which the output of the zarrcurator will be stored.
            targetSize : Target size of the tarball keeping in view of the HSM constraint (200 GB as of now).
            batchMode  : Flag to indicate if mode of operation of the zarrcurator is batch mode.
            debugMode  : Flag to indicate if mode of operation of the zarrcurator is set to debugging.
            packDiscontinuousData : Flag to indicate if data with missing chunks are to be packed.
            accessKey[str]: Optional access key value/env-var name.
            secretKey[str]: Optional secret key value/env-var name.
            
    Returns: 
            None.
    """

    configObj.setZarrStorePath( expPath )
    configObj.setWorkingDir( workDir )
    configObj.setJsonFile( jsonFile )
    configObj.setTargetSize ( targetSize )
    configObj.setBatchMode( batchMode )
    configObj.setDebugMode( debugMode )
    configObj.setPackDiscontinuousData( packDiscontinuousData )
    setObjectStoreCredentials(accessKey=accessKey, secretKey=secretKey)
    print(f"In initialize {configObj}", flush = True)


def diagnose():
    """Perform the diagnosis of the input directory containing the various zarr stores.

    Creates the object of class Diagnoser, to explore the contents of each zarr store and gather the count, sizes 
    of the files inside them.

    Args:
            None.            
    Returns: 
            None.
    """
    print(f"In diagnose {configObj}", flush = True)
    diagnoserObj = Diagnoser()
    richprint(diagnoserObj.list_of_zarrs)    
    diagnoserObj.update()
    configObj.setDiagnoserObj(diagnoserObj)
    return


def diagnoseStore( storeLocation, accessKey=None, secretKey=None ):
    """Perform the diagnosis of the input zarr store.

    To find the sizes, number of chunks for each of the variables inside the store.
    The result is written to '<store>.diag' in the working directory. While the diagnosis
    runs, the entries diagnosed so far are kept in '<store>.diag.checkpoint'; if a session
    is interrupted, calling diagnoseStore again in the same working directory continues
    with the remaining entries. The checkpoint is removed once the '.diag' is written;
    delete it to diagnose the store from the start.

    Args:
            storeLocation[str]: Location of the zarr store.
            accessKey[str]: Optional access key value/env-var name.
            secretKey[str]: Optional secret key value/env-var name.
    Returns:
            None.
    """
    
    import zarr

    def _private_store_error_message(path):
        return (
            f"Access denied for store '{path}'. The store is likely not public/anonymous. "
            "Please explicitly set credentials before calling diagnoseStore: "
            "configObj.setaccessKey('<ACCESS_KEY_ENV>') and configObj.setsecretKey('<SECRET_KEY_ENV>') "
            "or provide AWS/S3 environment variables."
        )

    try:
        fs, store, storeName = updateStoretoConfig(
            storeLocation,
            accessKey=accessKey,
            secretKey=secretKey,
        )
        zarrPath = configObj.getZarrStorePath()

        store_target = store.store if isinstance(store, zarr.core.group.Group) else store
        try:
            root = zarr.open_consolidated(store_target, mode="r")
        except Exception:
            root = zarr.open_group(store_target, mode="r")
        #print( root.tree() )
    except PermissionError as exp:
        raise PermissionError(_private_store_error_message(storeLocation)) from exp


    print(f"In diagnose configObj:{configObj}", flush = True)
    diagnoserObj = Diagnoser()
    richprint(diagnoserObj.list_of_zarrs)
    print(f"In diagnose zarrPath: {zarrPath}", flush = True)

    # The entries diagnosed so far are kept in a checkpoint file, so that the diagnosis of a very
    # large store can be continued in a later session; it is removed once the '.diag' is written.
    diagFile = os.path.join( configObj.getWorkingDir( ), f"{storeName.split('.')[0]}.diag" )
    checkpointFile = f"{diagFile}.checkpoint"
    try:
        diagnoserObj.diagnose_zarr( zarrPath, checkpointFile=checkpointFile )
    except PermissionError as exp:
        raise PermissionError(_private_store_error_message(storeLocation)) from exp

    print(f"diagnosis completed, writing the output to file in {configObj.getWorkingDir( )} {storeName.split('.')[0]}.diag", flush=True)
    # Written under a temporary name and renamed, as an existing '.diag' is taken as complete
    with open( f"{diagFile}.tmp", 'w' ) as fileOut:
        # Nested by group, as the '.check' report; flattenDiagReport gives it keyed by entry path
        json_dict_str = json.dumps( nestDiagReport( diagnoserObj.exp_size_dict ), indent=4 )
        print( json_dict_str, file=fileOut )
    os.replace( f"{diagFile}.tmp", diagFile )
    if os.path.exists( checkpointFile ):
        os.remove( checkpointFile )

    configObj.setDiagnoserObj(diagnoserObj)



def display():
    """Displays the output of the diagnoser object, by creating various plots.

    Creates the object of class Displayer, to create bar plots, pie charts of the output generated by the diagnoser object viz.,
    count, sizes of the files for each of the input zarr store, the constraints of the HSM system.

    Args:
            None.            
    Returns: 
            None.
    """


    titleText = "Reorganizing the zarr store into equal sized sub-groups without segregation"
    fileName = "zarrstore_from_disk_to_tape_without_splitting.png"
    subPlotTitles=[" Variables sorted by size",
               " Variable sizes after rearrangement into sub-groups",
               " Variable names after rearrangement into sub-groups",
               " Sizes of sub-groups "]

    diagnoserObj=configObj.getDiagnoserObj()
    displayerObj=Displayer(diagnoserObj,fileName, titleText,subPlotTitles)
    displayerObj.createHBarPlotsForExp(fileCount = False, byteBins = True)

    displayerObj.createHBarPlotsForExp(fileCount=False, byteBins = False)
    displayerObj.createHBarPlotsForExp(fileCount=True, byteBins = False)
    return


def running_in_jupyter():
    try:
        from IPython import get_ipython

        shell = get_ipython().__class__.__name__

        if shell == "ZMQInteractiveShell":
            return True   # Jupyter notebook/lab
        elif shell == "TerminalInteractiveShell":
            return False  # IPython terminal
        else:
            return False
    except:
        return False




def displayStoreSunburst( storeLocation, accessKey=None, secretKey=None ):
    """Displays the output of the diagnoser object, by creating sunburst plot for the input zarr store.

    Creates the object of class Displayer, to create sunburst plot of the output generated by the diagnoser object viz.,
    count, sizes of the files for each of the variables in the input zarr store.

    Args:
            storeLocation[str]: Location of the zarr store.
            accessKey[str]: Optional access key value/env-var name.
            secretKey[str]: Optional secret key value/env-var name.
    Returns: 
            None.
    """
    
    import plotly.io as pio

    check_if_running_in_jupyter = running_in_jupyter()

    if check_if_running_in_jupyter:
        print( "Running in Jupyter environment, using 'notebook' renderer for plotly", flush=True )
        pio.renderers.default = 'notebook'
    else:
        print( "Not running in Jupyter environment, using 'browser' renderer for plotly", flush=True )
        pio.renderers.default = 'browser'

    import s3fs
    import plotly.express as px
    import plotly.io as pio

    def _human_readable_size(num_bytes):
        """Convert bytes to human-readable binary units."""

        units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
        size = float(num_bytes)
        for unit in units:
            if size < 1024.0 or unit == units[-1]:
                if unit == "B":
                    return f"{int(size)} {unit}"
                return f"{size:.2f} {unit}"
            size /= 1024.0
    
    fs,store, storeName = updateStoretoConfig(
        storeLocation,
        accessKey=accessKey,
        secretKey=secretKey,
    )

    jsonFile = os.path.join(configObj.getWorkingDir(), f"{storeName.split('.')[0]}.diag")

    if os.path.isfile( jsonFile ):
        print( f"Diagnosis file {jsonFile} found, loading the diagnosis for sunburst plot!!!", flush=True )
    else:
        print( f"Diagnosis file {jsonFile} not found, running diagnosis for sunburst plot!!!", flush=True )
        diagnoseStore(
            storeLocation,
            accessKey=accessKey,
            secretKey=secretKey,
        )

    # load json produced by diagnoser to get the details of the store contents, to be used for creating the sunburst plot.
    with open(jsonFile) as f:
        data = flattenDiagReport( json.load(f) )

    # Build the tree of each store: the store, its groups (e.g. 'multiscales/zoom_11')
    # and their arrays and metadata files. Nodes are identified by their path, as names
    # like 'tas' repeat across groups, and labelled by their own name. The size and
    # count of each group is the sum of those of its members.
    nodes = {}  # id -> [label, parent id, size, count]
    for store, entries in data.items():
        storeParts = [p for p in store.replace("\\", "/").split("/") if p]
        storeId = store
        nodes.setdefault(storeId, [storeParts[-1] if storeParts else storeName, "", 0, 0])
        for path, entry in entries.items():
            if not isinstance(entry, dict):  # store totals
                continue
            parts = [p for p in path.split("/") if p]
            parentId = storeId
            for depth in range(1, len(parts) + 1):
                nodeId = f"{storeId}/{'/'.join(parts[:depth])}"
                nodes.setdefault(nodeId, [parts[depth - 1], parentId, 0, 0])
                parentId = nodeId
            size, count = entry.get("size", 0), entry.get("count", 0)
            nodeId = parentId
            while nodeId:
                nodes[nodeId][2] += size
                nodes[nodeId][3] += count
                nodeId = nodes[nodeId][1]

    ids = list(nodes)
    labels = [nodes[i][0] for i in ids]
    parents = [nodes[i][1] for i in ids]
    values = [nodes[i][2] for i in ids]
    size_labels = [f"{_human_readable_size(nodes[i][2])}<br>count: {nodes[i][3]}" for i in ids]

    try:
        fig = px.sunburst(
            ids=ids,
            names=labels,
            parents=parents,
            values=values )
        fig.update_traces(
            branchvalues="total",
            customdata=size_labels,
            texttemplate="%{label}<br>%{customdata}",
            hovertemplate="<b>%{label}</b><br>%{customdata}<extra></extra>",
        )
        fig.update_layout(margin=dict(t=20, l=20, r=20, b=20))
        fig.show()
    except Exception as exp :
        print( sys.exc_info() )
        print( f"Error {exp} in creating sunburst plot in {__file__}" )
    return


def displayZarrStoreVariables(zarrStore,fileCount,byteBins):
    """Displays the output of a given zarr store from the diagnoser object , by creating variable sizes plot.

    Creates create bar plots of the input zarr store from output generated by the diagnoser object viz.,
    count, sizes of the files for each of the variable in the input zarr store.

    Args:
            zarrStore[str]: Name of the zarr store.
            fileCount[int]: Flag to indicate if file counts are to be plotted.
            byteBins[int]: Flag to indicate if file sizes are to be plotted.
    Returns: 
            None.
    """

    diagnoserObj=configObj.getDiagnoserObj()
    displayerObj=Displayer(diagnoserObj,"", "","")
    displayerObj.createHBarPlotForStoreVariables(zarrStore, fileCount, byteBins)
    return


def distribute():
    """Distribute the output of the diagnoser object into subgroups of 'zarr', 'var' and 'chunk'.

    Creates the object of class Distributor, to create subgroups of 'zarr', 'var' and 'chunk', based on the size of the
    contents of the zarr store and the constraints of the HSM system.

    Args:
            None.            
    Returns: 
            None.
    """

    DEBUG_ZARRCURATOR = True
    
    diagnoserObj=configObj.getDiagnoserObj()
    if diagnoserObj is None:
        diagnoserObj = Diagnoser()
        configObj.setDiagnoserObj(diagnoserObj)
        diagnoserObj.update()
    distributorObj=Distributor(diagnoserObj,200*1024*1024*1024)

    distributorObj.updateFrequencyGroupDict()
    distributorObj.updateFrequencySubGroupDictWithSingleZarrStore()

    if DEBUG_ZARRCURATOR :
        print("frequencySubGroupDict - Before redistribution!",flush=True)
        for key in distributorObj.frequencySubGroupDict.keys():
            print(distributorObj.frequencySubGroupDict[key].keys(),flush=True)

    distributorObj.redistributeSubGroups()
    configObj.setDistributorObj(distributorObj)

    if DEBUG_ZARRCURATOR :
        print("frequencySubGroupDict - After redistribution!",flush=True)
        for key in distributorObj.frequencySubGroupDict.keys():
            for childKey in distributorObj.frequencySubGroupDict[key].keys():
                print(distributorObj.frequencySubGroupDict[key][childKey],flush=True)

    distributorObj.updateDimensionsToSubGroups()

    # Store the 'frequencySubGroupDict' to a file, to enable subGroup selection for the user,
    # while creating tarballs using the 'dispatcher'
    outputPath=configObj.getWorkingDir()
    
    dictOutFileName = os.path.join( outputPath, "subGroup.json" )
    with open(dictOutFileName, "w") as outFile:
        json.dump(distributorObj.frequencySubGroupDict, outFile, indent = 4, default=subGroup_to_dict)
    return


def distributeStoreToSubStores( storeLocation, accessKey=None, secretKey=None ):
    """Distribute the output of the diagnoser object into subgroups.

    Creates the object of class Distributor, to create subgroups of 'zarr', 'var' and 'chunk', based on the size of the
    contents of the zarr store and the constraints of the HSM system.
    """
    DEBUG_ZARRCURATOR = True
    
    diagnoserObj=configObj.getDiagnoserObj()
    if diagnoserObj is None:
        
        fs,store, storeName = updateStoretoConfig(
        storeLocation,
        accessKey=accessKey,
        secretKey=secretKey )

        diagnoserObj = Diagnoser()
        # Detect if .diag file exists and update the info to diagnoserObj
        diagState = diagnoserObj.update()
        
        if diagState: # .diag file not found!
            print( f"Running diagnosis!!!", flush=True )
            diagnoseStore(
            storeLocation,
            accessKey=accessKey,
            secretKey=secretKey,
        )
        else:
            configObj.setDiagnoserObj( diagnoserObj )

    diagnoserObj=configObj.getDiagnoserObj()
    print( diagnoserObj, flush=True )
    print("Creating Distributor obj!!!", flush = True)
    distributorObj = Distributor( diagnoserObj, 200*1024*1024*1024 )

    distributorObj.updateFrequencyGroupDict()
    distributorObj.updateFrequencySubGroupDictWithSingleZarrStore()

    if DEBUG_ZARRCURATOR :
        print("frequencySubGroupDict - Before redistribution!",flush=True)
        for key in distributorObj.frequencySubGroupDict.keys():
            print(distributorObj.frequencySubGroupDict[key].keys(),flush=True)

    distributorObj.redistributeSubGroups()
    configObj.setDistributorObj(distributorObj)

    if DEBUG_ZARRCURATOR :
        print("frequencySubGroupDict - After redistribution!",flush=True)
        for key in distributorObj.frequencySubGroupDict.keys():
            for childKey in distributorObj.frequencySubGroupDict[key].keys():
                print(distributorObj.frequencySubGroupDict[key][childKey],flush=True)

    distributorObj.updateDimensionsToSubGroups()

    # Store the 'frequencySubGroupDict' to a file, to enable subGroup selection for the user,
    # while creating tarballs using the 'dispatcher'
    outputPath=configObj.getWorkingDir()
    
    zarrPath = configObj.getZarrStorePath()    
    storeName = zarrPath.split(os.path.sep)[-1]
    print(f"distribution completed, writing the output to file in {configObj.getWorkingDir( )} {storeName.split('.')[0]}.dist", flush=True)
    # The members of each subgroup are nested by group, as in the '.diag' file
    flatDist = { freq: { subGroupID: subGroup_to_dict( subGroup ) for subGroupID, subGroup in subGroups.items() }
                 for freq, subGroups in distributorObj.frequencySubGroupDict.items() }
    with open( os.path.join( configObj.getWorkingDir( ), f"{storeName.split('.')[0]}.dist" ), 'w' ) as fileOut:
        json.dump(nestDistReport( flatDist, zarrPath ), fileOut, indent = 4)
    return


def checkStoreOpensWithXarray( storeTarget, storeLocation ):
    """Check that a zarr store can be opened with xarray, with all its groups.

    The tarballs are read back with xarray, directly or through the Kerchunk references, which
    needs the dimension names of the arrays ('_ARRAY_DIMENSIONS' in zarr v2, 'dimension_names'
    in zarr v3). Stores written with plain zarr may lack them.

    Args:
            storeTarget: Path of a local zarr store, or zarr store object of an object store.
            storeLocation[str]: Location of the zarr store, for the error message.
    Returns:
            None.
    Raises:
            ValueError: If xarray cannot open the store.
    """
    import warnings

    try:
        with warnings.catch_warnings():
            # Stores without consolidated metadata are opened without, after a warning.
            warnings.simplefilter("ignore", RuntimeWarning)
            xr.open_datatree(storeTarget, engine="zarr")
    except Exception as exp:
        raise ValueError(
            f"Zarr store '{storeLocation}' cannot be opened with xarray, so its tarballs could not be "
            f"read back with xarray: {exp}"
        ) from exp


def dispatchStoreToTarStores(storeLocation, accessKey=None, secretKey=None):
    """Dispatch the output of the distributor object into tarballs.

    Creates the object of class Dispatcher, to create tarballs for each of the subgroups of 'zarr', 'var' and 'chunk'.
    Fails with a ValueError before diagnosing, distributing or creating tarballs if the store cannot be
    opened with xarray, see checkStoreOpensWithXarray().

    """

    fs, store, _ = updateStoretoConfig(storeLocation, accessKey=accessKey, secretKey=secretKey)
    checkStoreOpensWithXarray(store.store if fs is not None else configObj.getZarrStorePath(), storeLocation)

    distributorObj = configObj.getDistributorObj()

    if distributorObj is None:
    
        fs,store, storeName = updateStoretoConfig(
        storeLocation,
        accessKey=accessKey,
        secretKey=secretKey )

        diagnoserObj = configObj.getDiagnoserObj()

        if diagnoserObj is None:
            diagnoserObj = Diagnoser()
            # Detect if .diag file exists and update the info to diagnoserObj
            diagState = diagnoserObj.update()

            if diagState: # .diag file not found!
                print( f"Running diagnosis!!!", flush=True )
                diagnoseStore(
                storeLocation,
                accessKey=accessKey,
                secretKey=secretKey,
            )
            else:
                configObj.setDiagnoserObj( diagnoserObj )
            
        distributorObj = Distributor( diagnoserObj, 200*1024*1024*1024 )
        
        # Detect if .diag file exists and update the info to diagnoserObj
        distState = distributorObj.update()
    
        if distState: # .dist file not found!
            print( f"Running distributor!!!", flush=True )
            distributeStoreToSubStores(
                storeLocation,
                accessKey=accessKey,
                secretKey=secretKey,
                )
        else:
            configObj.setDistributorObj( distributorObj )

    distributorObj=configObj.getDistributorObj()
    print( distributorObj, flush=True )
    
    dispatcherObj=Dispatcher(None,distributorObj)
    configObj.setDispatcherObj(dispatcherObj)
    
    subGroupID = -1
    # Set the store path in the config, from which the dispatcher creates the tarballs.
    updateStoretoConfig(storeLocation)

    dispatcherObj.createTarForFrequencySubGroupDict()
    dispatcherObj.executor( subGroupID )

    # Store the 'frequencySubGroupDict' with tarballs updated to a file.
    outputPath=configObj.getWorkingDir()
    
    dictOutFileName = os.path.join( outputPath, "subGroupTar.json" )
    with open(dictOutFileName, "w") as outFile:
        json.dump(distributorObj.frequencySubGroupDict, outFile, indent = 4, default=subGroup_to_dict)
    return


def createKerchunkReferenceFileForTar(tarFileName):
   """Create kerchunk reference file for given tar file.

   To generate the kerchunk reference file in JSON format for the contents of the input tar archive.

   Args:
           tarFileName[str]: Path of the tar archive.
   Returns: 
           None.
   """

   workDir = configObj.getWorkingDir()

   indexFile = os.path.basename(tarFileName).split('.')[0]+'_Offset_kerchunk.json'
   zarrName = os.path.basename(tarFileName).split('.')[0].split(os.path.sep)[-1]
   zarrNameList = zarrName.split('_')
   print( zarrNameList, flush = True )
   zarrNameNew = ('_').join(zarrNameList[:-1])
   print(zarrNameNew)
   
   print( f"{workDir} {indexFile}", flush = True )
   if workDir is None:
       workDir = os.getcwd()
   kerchunkIndexFile = os.path.join( workDir, indexFile )
   
   print( f"{kerchunkIndexFile}", flush = True )
   kerchunkDict = {
                       "version": 1,
                       "refs": {}
                  }
   ctr = 0
   with tarfile.open( tarFileName, 'r' ) as db:
     for tarinfo in db:
        currentseek = tarinfo.offset_data
        rec = "%d\t%d\t%d\t%s\n" % ( ctr, tarinfo.offset_data, tarinfo.size, tarinfo.name )
        kerchunkDict["refs"][tarinfo.name.replace( zarrNameNew + '.zarr' + os.path.sep,'')] = [ f"file://{tarFileName}", tarinfo.offset_data, tarinfo.size ]         
        ctr += 1
        if ctr % 1000 == 0:
           db.members = []
   
   kerchunkIndexFile = os.path.join( workDir, indexFile )
   with open( kerchunkIndexFile, 'w' ) as fp:
       json.dump( kerchunkDict, fp )
   fp.close()
   
   
def mergeKerchunkReferences( jsonFiles ):
    """Merge the Kerchunk references of the tarballs of a zarr store into the references of the store.

    The tarballs of a zarr store are parts of it: each holds some of its variables, or some of the
    chunks of a variable, along with the metadata of the store, its groups and its arrays and the
    coordinate variables it needs. So the references of the store are the union of the references
    of its tarballs. A chunk of a data variable is in one tarball; metadata and the chunks of
    coordinate variables are in several, and are kept once after checking that their content is the
    same. The consolidated metadata ('.zmetadata') is left out, as the parquet references hold their own.

    Args:
            jsonFiles[list[str]]: Paths of the Kerchunk reference files (JSON) of the tarballs.
    Returns:
            dict: Merged references, key -> metadata content or [url, offset, size].
    Raises:
            ValueError: If a key is found in two tarballs with a different content or location.
    """

    merged = {}
    origin = {}
    for jsonFile in jsonFiles:
        with fsspec.open(jsonFile) as f:
            refs = ujson.load(f)["refs"]
        for key, value in refs.items():
            if key.rsplit('/', 1)[-1] == '.zmetadata':
                continue
            if key in merged:
                if merged[key] != value and _readReference(merged[key]) != _readReference(value):
                    raise ValueError(f"Reference '{key}' differs between {origin[key]} and {jsonFile}")
                continue
            merged[key] = value
            origin[key] = jsonFile
    return merged


def _readReference( ref ):
    """Return the content of a Kerchunk reference: inline metadata, or the bytes [url, offset, size] point to."""
    if not isinstance( ref, list ):
        return ref
    url, offset, size = ref
    fs, path = fsspec.core.url_to_fs( url )
    return fs.cat_file( path, offset, offset + size )


def convertKerchunkReferenceFilesOfZarrStoreToParquet( storeLocation ):
    """Convert given Kerchunk reference file to parquet file.

    To generate the Kerchunk reference file in JSON format for the contents of the input tar archive.
    The references of all tarballs of the store are merged, see mergeKerchunkReferences().
    The references are combined in the zarr v2 layout: for zarr v3 stores the zarr.json metadata is
    translated to zarr v2 metadata and the chunks are referenced unchanged, so only zarr v3 arrays
    with a zarr v2 equivalent are supported; sharded arrays are referenced by their inner chunks,
    read from the shard indexes. Stores with nested groups (e.g. written
    from an xarray DataTree) are opened from the parquet references with consolidated=True.

    Args:
            tarFile[str]: Path of the tar archive.
    Returns:
            None.
    """

    def use_dot_dimension_separator(key, content):
        """Set dimension_separator to '.' in .zarray (and .zmetadata) content."""

        name = key.split('/')[-1]
        if name not in (".zarray", ".zmetadata"):
            return content
        meta = json.loads(content)
        arrays = [meta] if name == ".zarray" else [
            v for k, v in meta.get("metadata", {}).items() if k.endswith(".zarray")
        ]
        changed = False
        for array_meta in arrays:
            if array_meta.get("dimension_separator") == "/":
                array_meta["dimension_separator"] = "."
                changed = True
        return json.dumps(meta) if changed else content

    def clear_dict(ref):

        refm = copy(ref)
        todel = [a for a in refm.keys() if refm[a][2] == 0]
        todel += [a for a in refm.keys() if "rechunker" in a]
        todel = list(set(todel))
        for td in todel:
            del refm[td]
        # Metadata files (.zarray, .zattrs, .zgroup, .zmetadata) of the root and of every
        # group and array, also in nested groups (e.g. z2/ocean/sst/.zarray).
        decode = [a for a in refm.keys() if a.split('/')[-1].startswith('.')]
        for dc in decode:
            refm[dc] = fs.cat_file(refm[dc][0], refm[dc][1], refm[dc][1] + refm[dc][2]).decode("utf-8")
            # Nested chunk keys (e.g. var/0/1) are renamed to the dot-separated form
            # below, so the array metadata must use the '.' separator as well.
            refm[dc] = use_dot_dimension_separator(dc, refm[dc])
        # zarr v3 stores: the references are combined in the zarr v2 layout, so the zarr.json of each
        # group and array is replaced by the zarr v2 metadata files; the chunks are referenced unchanged.
        v3KeyEncodings = {}
        v3Shardings = {}
        for meta_key in [a for a in refm.keys() if a.split('/')[-1] == 'zarr.json']:
            meta = json.loads(fs.cat_file(refm[meta_key][0], refm[meta_key][1], refm[meta_key][1] + refm[meta_key][2]))
            prefix = meta_key[:-len('zarr.json')]
            for name, content in v3MetadataToV2(meta).items():
                refm[prefix + name] = json.dumps(content)
            if meta.get('node_type') == 'array':
                v3KeyEncodings[prefix.rstrip('/')] = meta.get('chunk_key_encoding', {})
                sharding = v3ShardingLayout(meta)
                if sharding is not None:
                    v3Shardings[prefix.rstrip('/')] = sharding
            del refm[meta_key]
        # Chunk keys are renamed relative to their array, e.g. z2/ocean/sst/0/1 -> z2/ocean/sst/0.1,
        # so the array path is taken from the '.zarray' keys, longest first; keys of arrays without
        # a '.zarray' key are taken to belong to a top-level array, e.g. var/0/1 -> var/0.1.
        arrayPaths = sorted((a[:-len('/.zarray')] for a in refm.keys() if a.endswith('/.zarray')), key=len, reverse=True)
        torename = [a for a in refm.keys() if '/' in a and not a.split('/')[-1].startswith('.')]
        # The inner chunks of shards are added after renaming, as their keys may be those of other shards.
        innerChunks = {}
        for tr in torename:
            arrayPath = next((ap for ap in arrayPaths if tr.startswith(ap + '/')), tr.split('/')[0])
            chunkKey = tr[len(arrayPath) + 1:]
            if arrayPath in v3Shardings:
                # e.g. shard z2/tas/c/1/0 -> inner chunks z2/tas/2.0, z2/tas/2.1, z2/tas/3.0, ...
                shardKey = v3ChunkKeyToV2(chunkKey, v3KeyEncodings[arrayPath])
                readRange = lambda url, start, end: fs.cat_file(url, start, end)
                for innerKey, innerRef in shardChunkReferences(refm[tr], shardKey, v3Shardings[arrayPath], readRange):
                    innerChunks[arrayPath + '/' + innerKey] = innerRef
                del refm[tr]
                continue
            if arrayPath in v3KeyEncodings:
                # e.g. z2/tas/c/0/1 -> z2/tas/0.1
                nn = arrayPath + '/' + v3ChunkKeyToV2(chunkKey, v3KeyEncodings[arrayPath])
            else:
                nn = arrayPath + '/' + chunkKey.replace('/', '.')
            if nn != tr:
                refm[nn] = copy(refm[tr])
                del refm[tr]
        refm.update(innerChunks)
        return refm

    workDir = configObj.getWorkingDir()
    fs = fsspec.filesystem("file")

    # Extract and set zarr path from input based on storage tier.
    configObj.setZarrStorePath(storeLocation)

    # zarrPath extracted after identifying the storage tier from input 'storeLocation'
    zarrPath = configObj.getZarrStorePath()

    zarrName = zarrPath.split(os.path.sep)[-1]
    # If the zarrName has '.zarr'
    zarrName = zarrName.split('.')[0]

    # Create copies of the original Kerchunk reference files in JSON format.
    for oldjson in tqdm(sorted(glob.glob((os.path.sep).join([workDir, zarrName]) + "_*Offset_kerchunk.json"))):
        print(oldjson)
        target = (os.path.sep).join([workDir, f"{oldjson.split(os.path.sep)[-1]}.copy"])
        refs = ujson.load(fsspec.open(oldjson).open())
        refs["refs"] = clear_dict(refs["refs"])
        ujson.dump(refs, fsspec.open(target, "w").open())

    jsons = sorted(glob.glob((os.path.sep).join([workDir, zarrName]) + "_*Offset_kerchunk.json.copy"))

    if not jsons:
        return

    target = os.path.join(workDir, zarrName + ".parq")

    refs = mergeKerchunkReferences(jsons)

    def _translate_refs_to_parquet():
        # URLs are not stored as categoricals: fsspec reads a chunk missing from a categorical
        # column as [nan] instead of as missing, and zarr leaves out chunks holding only the fill
        # value, so most arrays of a tarball (many chunks, one URL) would read wrongly.
        refs_to_dataframe({"version": 1, "refs": refs}, target, categorical_threshold=sys.maxsize)

    # In notebooks an event loop is usually already running; write the parquet references
    # in a worker thread so libraries using asyncio.run() remain sync-callable.
    import asyncio
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        _translate_refs_to_parquet()
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(_translate_refs_to_parquet).result()
    return
   
    
def updateArchBasePath( archBasePath ):
    """Update the base path of the tape archive.

    To set the base path on the tape archive under which the tarballs created for each of the subgroups of 'zarr', 'var' and 'chunk' are stored.

    Args:
            archBasePath[str]: Path on the tape archive.            
    Returns: 
            None.
    """

    configObj.setArchBasePath(archBasePath)
    print(f"In:{archBasePath} Out:{configObj.getArchBasePath()}", flush=True)


def updateTarToTapeMapper(tarFile):
    """Update the mapper for tarfiles and tape IDs.

    To update the mapper which maps the input tar file to the ID of the tape on which this tar file resides.

    Args:
            tarFile[str]: Path on the tar file.            
    Returns: 
            None.
    """

    dispatcherObj=configObj.getDispatcherObj()
    tarTapeDict = dispatcherObj.subGroupTarTapeDict
    
    archBasePath=configObj.getArchBasePath()

    tarName = tarFile.split(os.path.sep)[-1]
    tarTapeDict[tarName] = []
    
    # The pyslk call returns a dict {173408: 'M31763M8'} , from that we take the 'value' which is the barcode ID
    tapeID = pyslk.get_resource_tape( os.path.join( archBasePath, tarName ) ).values()
    
    # TODO : Get info if a tar ball can be partially stored on two tapes
    tarTapeDict[tarName].extend(list(tapeID))


def mapTapeIDsToFrequencySubGroupDict():
    """Update the tape IDs to the FrequencySubGroupDict.

    Creates the list of tape IDs for the tarballs of each subgroup in the FrequencySubGroupDict. To be called after the tarballs
    are transferred to the HSM tapes.

    Args:
            None
    Returns: 
            None.
    """

    
    distributorObj=configObj.getDistributorObj()
    dispatcherObj = configObj.getDispatcherObj()

    # First esńsure a valid distributorObj exists
    if distributorObj is None:
        print("distributorObj  is None")
        workingDir = configObj.getWorkingDir()
        # 'subGroupTar.json' is 'subGroup.json' filled with 'groupTarMembers[]'
        # if 'subGroupTar.json' is not available simply copy 'subGroup.json' and create 'subGroupTar.json'
        subGroupTarFile = os.path.join( workingDir, "subGroupTar.json" )
        
        if not os.path.isfile( subGroupTarFile ):
            subGroupFile = os.path.join( workingDir, "subGroup.json" )
            print( f"Sub group tar file {subGroupTarFile} not found!!!", flush=True )
            
            print( f"Creating Sub group tar file from {subGroupFile}!!!", flush=True )
            shutil.copy2( subGroupFile, subGroupTarFile )
            
        with open( subGroupTarFile, 'r' ) as expJSONFile:
            frequencySubGroupDict = json.load( expJSONFile )
            
        diagnoserObj=configObj.getDiagnoserObj()
        distributorObj=Distributor(diagnoserObj,200*1024*1024*1024)
        distributorObj.setFrequencySubGroupDict(frequencySubGroupDict)
        configObj.setDistributorObj(distributorObj)
    
    frequencySubGroupDict = distributorObj.getFrequencySubGroupDict()    
    print(frequencySubGroupDict, flush=True)

    # Create a dispatcherObj if it doesn't exist ( as in standalone mode directly executing tartapeId mapper)
    if dispatcherObj is None:
        print("dispatcherObj  is None", flush=True)
        dispatcherObj = Dispatcher(None,distributorObj)
        configObj.setDispatcherObj(dispatcherObj)

    outputPath = configObj.getWorkingDir()
    
    for freq in frequencySubGroupDict.keys():
        freqDict = frequencySubGroupDict[freq]
        for subGroupID in list(freqDict.keys()):
            print(subGroupID, flush=True)
            frequencySubGroupDict[freq][subGroupID]['groupTarTapeIDs'] = []
            
            if len(freqDict[subGroupID]['groupTarMembers']) == 0:
                groupType = freqDict[subGroupID]['groupType']
                if groupType == 'chunk':
                    tarSearchStr = os.path.join(outputPath,subGroupID + "_*.tar")
                else:
                    tarSearchStr = os.path.join(outputPath,subGroupID + ".tar")
                tarFilesFromZarrcurator = glob.glob(tarSearchStr)
                freqDict[subGroupID]['groupTarMembers'].extend(tarFilesFromZarrcurator)
            else:
                tarFilesFromZarrcurator = freqDict[subGroupID]['groupTarMembers']

            if( len(tarFilesFromZarrcurator) == 0 ): 
                print( f"Tar balls for {subGroupID} not found!!!", flush=True )
                continue
         
            start = time.time()
            with concurrent.futures.ThreadPoolExecutor( max_workers=len(tarFilesFromZarrcurator) ) as rangeExecutor:
                results=rangeExecutor.map( updateTarToTapeMapper, tarFilesFromZarrcurator )
            stop=time.time()
            print( f"Total time for Experiment : {(stop-start)} secs", flush=True )

            for tarFile in freqDict[subGroupID]['groupTarMembers']:
                tapeID = dispatcherObj.subGroupTarTapeDict[tarFile.split(os.path.sep)[-1]]
                
                # 'groupTarMembers' and 'tarTapeIDs' have one-to-one correspondence
                frequencySubGroupDict[freq][subGroupID]['groupTarTapeIDs'].extend(tapeID)

    if distributorObj is None:
        distributorObj.setFrequencySubGroupDict(frequencySubGroupDict)    
        
    dictOutFileName = os.path.join( outputPath, "subGroupTarTape.json" )
    with open(dictOutFileName, "w") as outFile:
        json.dump(distributorObj.frequencySubGroupDict, outFile, indent = 4, default=subGroup_to_dict)

    return
    
    
def displayZarrStoresTarTapes():
    """Displays the tar ball count and tape count for the zarr stores.

    Creates create bar plots for the tar balls and tape counts for all the zarr stores.

    Args:
            None.
    Returns: 
            None.
    """
    
    diagnoserObj=configObj.getDiagnoserObj()
    displayerObj=Displayer(diagnoserObj,"", "","")
    
    distributorObj=configObj.getDistributorObj()
    
    # First esńsure a valid distributorObj exists
    if distributorObj is None:
        
        workingDir = configObj.getWorkingDir()
        # if 'subGroupTar.json' is not available simply return
        subGroupTarFile = os.path.join( workingDir, "subGroupTarTape.json" )
        
        if not os.path.isfile( subGroupTarFile ):
            print( f"Mapping for tarballs and tapes not found!!!", flush=True )
            return
        
        with open( subGroupTarFile, 'r' ) as expJSONFile:
            frequencySubGroupDict = json.load( expJSONFile )
        
        diagnoserObj=configObj.getDiagnoserObj()
        distributorObj=Distributor(diagnoserObj,200*1024*1024*1024)
        distributorObj.setFrequencySubGroupDict(frequencySubGroupDict)
        configObj.setDistributorObj(distributorObj)
    
    frequencySubGroupDict = distributorObj.getFrequencySubGroupDict() 
    
    print( frequencySubGroupDict, flush=True )
    zarrStoreSubGroupDict = {}
    
    for freq in frequencySubGroupDict.keys():
        freqDict = frequencySubGroupDict[freq]
        for subGroupID in list( freqDict.keys() ):
            zarrStore = ('_').join( subGroupID.split('_')[0:3] )
            if zarrStore not in zarrStoreSubGroupDict.keys():
                zarrStoreSubGroupDict[ zarrStore ] = {}
                zarrStoreSubGroupDict[ zarrStore ][ 'tarBallList' ] =  []
                zarrStoreSubGroupDict[ zarrStore ][ 'tapeIDList' ] =  []
    
            zarrStoreSubGroupDict[ zarrStore ][ 'tarBallList' ].extend( freqDict[ subGroupID ]['groupTarMembers'] )
            zarrStoreSubGroupDict[ zarrStore ][ 'tapeIDList' ].extend( freqDict[ subGroupID ]['groupTarTapeIDs'] )
    
    for zarrStore in zarrStoreSubGroupDict.keys():
        zarrStoreSubGroupDict[ zarrStore ][ 'tarBallList' ] = list( set( zarrStoreSubGroupDict[ zarrStore ][ 'tarBallList' ] ) )
        zarrStoreSubGroupDict[ zarrStore ][ 'tapeIDList' ] = list( set( zarrStoreSubGroupDict[ zarrStore ][ 'tapeIDList' ] ) )
    

    displayerObj.createHBarPlotForStoreTarTapes( zarrStoreSubGroupDict, tarCount =  True, tapeCount = False )
    displayerObj.createHBarPlotForStoreTarTapes( zarrStoreSubGroupDict, tarCount =  False, tapeCount = True )


def displayZarrStoreVarTarTapes(zarrStoreInput, varInput):
    """Displays the tar ball count and tape count for a given variable of a zarr store.

    Creates create bar plots for the tar balls and tape counts for a particular variable from a zarr store.

    Args:
            zarrStoreInput[str]: Name on the zarr store.
            varInput[list(str)]: List of names of the variables.
    Returns: 
            None.
    """

    
    diagnoserObj=configObj.getDiagnoserObj()
    displayerObj=Displayer(diagnoserObj,"", "","")
    
    distributorObj=configObj.getDistributorObj()
    
    # First esńsure a valid distributorObj exists
    if distributorObj is None:
        
        workingDir = configObj.getWorkingDir()
        # if 'subGroupTar.json' is not available simply return
        subGroupTarFile = os.path.join( workingDir, "subGroupTarTape.json" )
        
        if not os.path.isfile( subGroupTarFile ):
            print( f"Mapping for tarballs and tapes not found!!!", flush=True )
            return
        
        with open( subGroupTarFile, 'r' ) as expJSONFile:
            frequencySubGroupDict = json.load( expJSONFile )
        
        diagnoserObj=configObj.getDiagnoserObj()
        distributorObj=Distributor(diagnoserObj,200*1024*1024*1024)
        distributorObj.setFrequencySubGroupDict(frequencySubGroupDict)
        configObj.setDistributorObj(distributorObj)
    
    frequencySubGroupDict = distributorObj.getFrequencySubGroupDict() 
    
    print( frequencySubGroupDict, flush=True )
    
    zarrStoreVarTarDict = {}
    
    for var in varInput:
        zarrStoreVarTarDict[var] = {}
        zarrStoreVarTarDict[var]['tarBallList'] = []
        zarrStoreVarTarDict[var]['tapeIDList'] = []
    
    for freq in frequencySubGroupDict.keys():
        freqDict = frequencySubGroupDict[freq]
        for subGroupID in list( freqDict.keys() ):
            zarrStore = ('_').join( subGroupID.split('_')[0:3] )
            if zarrStore != zarrStoreInput:
                continue
            
            groupType = freqDict[ subGroupID ]['groupType'] 
            
            # Single tarball for all vars case
            if groupType == "zarr":
                for var in varInput:
                    zarrStoreVarTarDict[var]['tarBallList'].extend( freqDict[ subGroupID ]['groupTarMembers'] )
                    zarrStoreVarTarDict[var]['tapeIDList'].extend( freqDict[ subGroupID ]['groupTarTapeIDs'] ) 
                continue
            else:
                groupMembers = freqDict[ subGroupID ]['groupMembers']
                groupVars = [ var[0].split(os.path.sep)[-1] for var in groupMembers ]
                for var in varInput:
                    if var not in groupVars:
                        continue
                    else:
                            zarrStoreVarTarDict[var]['tarBallList'].extend( freqDict[ subGroupID ]['groupTarMembers'] )
                            zarrStoreVarTarDict[var]['tapeIDList'].extend( freqDict[ subGroupID ]['groupTarTapeIDs'] ) 
            
    
    
    for var in zarrStoreVarTarDict.keys():
        zarrStoreVarTarDict[ var ][ 'tarBallList' ] = list( set( zarrStoreVarTarDict[ var ][ 'tarBallList' ] ) )
        zarrStoreVarTarDict[ var ][ 'tapeIDList' ] = list( set( zarrStoreVarTarDict[ var ][ 'tapeIDList' ] ) )
    
    print( zarrStoreVarTarDict, flush=True )

    displayerObj.createHBarPlotForStoreTarTapes( zarrStoreVarTarDict, tarCount =  True, tapeCount = False )
    displayerObj.createHBarPlotForStoreTarTapes( zarrStoreVarTarDict, tarCount =  False, tapeCount = True )
