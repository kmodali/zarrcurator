"""
This module contains helpers for zarr chunks: parsing chunk keys and
scaling the number of threads with the number of chunks and the available CPUs.
"""

#Standard modules
import os
import logging


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

ENV_MAX_THREADS = "ZARRCURATOR_MAX_THREADS"
"""str: Environment variable setting the maximum number of threads, overriding the CPU based cap."""

ENV_ARRAY_WORKERS = "ZARRCURATOR_ARRAY_WORKERS"
"""str: Environment variable setting the number of arrays checked at once by findMissingChunksInStore."""

DEFAULT_ARRAY_WORKERS = 8
"""int: Default number of arrays checked at once, at most the number of available CPUs."""

IO_THREADS_PER_CPU = 4
"""int: Threads per available CPU for I/O-bound work, e.g. listing files and querying their sizes,
where the threads mostly wait for the file system or object store."""


def parseChunkKey( key ):
    """Parse the chunk coordinates from a chunk key relative to its variable.

    Supports zarr v2 keys separated by '.' (0.1) or '/' (0/1), and zarr v3 keys
    with the 'c' prefix separated by '/' (c/0/1) or '.' (c.0.1).

    Args:
            str: Chunk key relative to the variable directory.
    Returns:
            tuple: Chunk coordinates, or None if the key is not a chunk key.
    """
    parts = key.replace( os.path.sep, '/' ).replace( '.', '/' ).split( '/' )
    if parts[0] == 'c':
        parts = parts[1:]
    if parts and all( p.isdigit() for p in parts ):
        return tuple( int( p ) for p in parts )
    return None


def availableCpus():
    """Number of CPUs this process may run on.

    Within a SLURM job (or with another CPU affinity), this is the number of CPUs allocated to it,
    not the number of CPUs of the node.

    Returns:
            int: Number of available CPUs, at least 1.
    """

    try:
        return max( 1, len( os.sched_getaffinity( 0 ) ) )
    except AttributeError:  # not available on all platforms
        return max( 1, os.cpu_count() or 1 )


def maxThreads( ioBound=True ):
    """Maximum number of threads for processing the chunks of an array.

    The environment variable ZARRCURATOR_MAX_THREADS, if set to a positive integer, sets the
    maximum for all work. Otherwise it is the number of available CPUs for CPU-bound work, e.g.
    decompressing chunks, and IO_THREADS_PER_CPU times that for I/O-bound work, e.g. listing
    files and querying their sizes.

    Args:
            ioBound[bool]: True for I/O-bound work, False for CPU-bound work.
    Returns:
            int: Maximum number of threads, at least 1.
    """

    value = os.getenv( ENV_MAX_THREADS )
    if value:
        try:
            if int( value ) > 0:
                return int( value )
        except ValueError:
            pass
        logger.warning("Ignoring %s=%r, which is not a positive integer", ENV_MAX_THREADS, value)
    cpus = availableCpus()
    return cpus * IO_THREADS_PER_CPU if ioBound else cpus


def numThreadsForChunks( numChunks, ioBound=True ):
    """Number of threads for processing the chunks of an array.

    Scales with the number of chunks, used by Diagnoser.diagnose_var (for the
    files of a variable) and utils.findMissingChunksInStore, and is capped by
    the available CPUs (see maxThreads).

    Args:
            numChunks[int]: Number of chunks.
            ioBound[bool]: True for I/O-bound work, e.g. querying the sizes of the chunks,
                    False for CPU-bound work, e.g. decompressing the chunks.
    Returns:
            int: 100 threads for 1000 or more chunks, 40 for 500 to 999,
            10 for 200 to 499 and 1 for fewer than 200, at most maxThreads(ioBound).
    """

    chunk_range = numChunks / 100

    if chunk_range >= 10 :
        numThreads = 100
    elif chunk_range >= 5 and chunk_range < 10 :
        numThreads = 40
    elif chunk_range >= 2 and chunk_range < 5  :
        numThreads = 10
    else:
        numThreads = 1
    return max( 1, min( numThreads, maxThreads( ioBound ) ) )


def arrayWorkers():
    """Number of arrays of a store processed at once, e.g. by findMissingChunksInStore.

    The environment variable ZARRCURATOR_ARRAY_WORKERS, if set to a positive integer, sets it;
    otherwise it is DEFAULT_ARRAY_WORKERS, at most the number of available CPUs.

    Returns:
            int: Number of arrays processed at once, at least 1.
    """

    value = os.getenv( ENV_ARRAY_WORKERS )
    if value:
        try:
            if int( value ) > 0:
                return int( value )
        except ValueError:
            pass
        logger.warning("Ignoring %s=%r, which is not a positive integer", ENV_ARRAY_WORKERS, value)
    return max( 1, min( DEFAULT_ARRAY_WORKERS, availableCpus() ) )
