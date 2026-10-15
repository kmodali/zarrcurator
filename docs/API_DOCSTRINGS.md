# zarrcurator API Documentation

Generated from source docstrings.

Generated on: 2026-10-10

## Module: __init__

Source: src/zarrcurator/__init__.py

No docstring provided.

### Functions

#### enable_logging()

Enable zarrcurator logging for notebooks and library usage.

This configures both console logging and a timestamped log file,
using the same behavior as the CLI.

## Module: benchmark

Source: src/zarrcurator/benchmark.py

Micro-benchmark harness for zarrcurator.

Run examples:
  python -m zarrcurator.benchmark --synthetic
  python -m zarrcurator.benchmark --store-path /path/to/store.zarr --phase diagnose
  python -m zarrcurator.benchmark --synthetic --phase both --log-level INFO

### Functions

#### create_synthetic_store()

Create a lightweight local zarr-like directory tree for benchmarking I/O paths.

#### benchmark_diagnose()

No docstring provided.

#### benchmark_dispatch()

No docstring provided.

#### parse_args()

No docstring provided.

#### main()

No docstring provided.

### Classes

#### _BenchDistributor

No docstring provided.

## Module: chunkkeys

Source: src/zarrcurator/chunkkeys.py

This module contains helpers for zarr chunks: parsing chunk keys and
scaling the number of threads with the number of chunks and the available CPUs.

### Functions

#### parseChunkKey()

Parse the chunk coordinates from a chunk key relative to its variable.

Supports zarr v2 keys separated by '.' (0.1) or '/' (0/1), and zarr v3 keys
with the 'c' prefix separated by '/' (c/0/1) or '.' (c.0.1).

Args:
        str: Chunk key relative to the variable directory.
Returns:
        tuple: Chunk coordinates, or None if the key is not a chunk key.

#### availableCpus()

Number of CPUs this process may run on.

Within a SLURM job (or with another CPU affinity), this is the number of CPUs allocated to it,
not the number of CPUs of the node.

Returns:
        int: Number of available CPUs, at least 1.

#### maxThreads()

Maximum number of threads for processing the chunks of an array.

The environment variable ZARRCURATOR_MAX_THREADS, if set to a positive integer, sets the
maximum for all work. Otherwise it is the number of available CPUs for CPU-bound work, e.g.
decompressing chunks, and IO_THREADS_PER_CPU times that for I/O-bound work, e.g. listing
files and querying their sizes.

Args:
        ioBound[bool]: True for I/O-bound work, False for CPU-bound work.
Returns:
        int: Maximum number of threads, at least 1.

#### numThreadsForChunks()

Number of threads for processing the chunks of an array.

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

#### arrayWorkers()

Number of arrays of a store processed at once, e.g. by findMissingChunksInStore.

The environment variable ZARRCURATOR_ARRAY_WORKERS, if set to a positive integer, sets it;
otherwise it is DEFAULT_ARRAY_WORKERS, at most the number of available CPUs.

Returns:
        int: Number of arrays processed at once, at least 1.

## Module: cli

Source: src/zarrcurator/cli.py

No docstring provided.

### Functions

#### configure_logging()

Configure root logging for zarrcurator CLI usage.

Priority:
1. CLI --log-level value
2. ZARRCURATOR_LOG_LEVEL environment variable
3. INFO default

#### main()

No docstring provided.

## Module: config

Source: src/zarrcurator/config.py

This module contains the configuration variables to handle the various features of the zarrcurator tool. 
The configuration variables consists of the various path, the flag to handle the mode of operation viz.,
interactive or batch mode.

### Classes

#### configVars

Config class to hold the configuration variables to be used across the modules in the package.

##### Methods of configVars

- getZarrStorePath(): Get the path of the zarr stores.  To get the directory under which the zarr stores, for each healpix and frequency combination exist.   Args:         None. Returns:         path: Path to zarr stores.
- setZarrStorePath(): Set the path of the zarr stores.  To set the directory under which the zarr stores, for each healpix and frequency combination exist.   Args:         path: Path to zarr stores. Returns:         None.
- getFileSystemObj(): Get the file system object.  To get the file system object, so that it can be used in other classes of the zarrcurator viz., diagnoser.  Args:         None. Returns:         object[class FileSystem]: File system object.
- setFileSystemObj(): Set the file system object.  To set the file system object, so that it can be used in other classes of the zarrcurator viz., diagnoser.  Args:         None. Returns:         None.
- parse_object_store_url(): Parse an object-store HTTP URL into: - endpoint - bucket - object key - s3 uri
- getWorkingDir(): Get the path of the working directory.  To get the directory under which the output produced by zarrcurator will be stored.   Args:         None. Returns:         path: Path to working directory.
- setWorkingDir(): Set the path of the working directory.  To set the directory under which the output produced by zarrcurator will be stored.   Args:         path: Path to working directory. Returns:         None.
- getArchBasePath(): Get the path of the directory on HSM.  To get the location of the directory on HSM under which the tarballs prouced by zarrcurator tool will be stored.  Args:         None. Returns:         path: Path to base directory on HSM.
- setArchBasePath(): Set the path of the directory on HSM.  To set the location of the directory on HSM under which the tarballs prouced by zarrcurator tool will be stored.  Args:         path: Path to base directory on HSM. Returns:         None.
- getJsonFile(): Get the name of the JSON file.  To get the name of the output JSON file produced by zarrcurator.   Args:         None. Returns:         str: Name of the JSON file.
- setJsonFile(): Set the name of the JSON file.  To set the name of the output JSON file produced by zarrcurator.   Args:         str: Name of the JSON file. Returns:         None.
- getTargetSize(): Get the target size of the tarball.  To get the target size of the tar ball keeping in view the constraints of the HSM system, as of now 200 GB.  Args:         None. Returns:         int: Target size of the tarball.
- setTargetSize(): Set the target size of the tarball.  To set the target size of the tar ball keeping in view the constraints of the HSM system, as of now 200 GB.  Args:         int: Target size of the tarball. Returns:         None.
- getBatchMode(): Get the mode of operation of the zarrcurator.  To get the mode of operation of the zarrcurator viz., interactive or batch mode.  Args:         None. Returns:         bool: mode of operation of the zarrcurator.
- setBatchMode(): Set the mode of operation of the zarrcurator.  To set the mode of operation of the zarrcurator viz., interactive or batch mode.  Args:         bool: mode of operation of the zarrcurator. Returns:         None.
- getDebugMode(): Get the debug mode of operation of the zarrcurator.  To get the debug mode of operation of the zarrcurator.  Args:         None. Returns:         bool: Debug mode of operation of the zarrcurator.
- setDebugMode(): Set the debug mode of operation of the zarrcurator.  To set the debug mode of operation of the zarrcurator.  Args:         bool: Debug mode of operation of the zarrcurator. Returns:         None.
- getPackDiscontinuousData(): Get the flag for packing the discontinuous data.  To get flag to pack the data even if the chunks are missing.  Args:         None. Returns:         bool: Flag to indicate the packing of missing chunks.
- setPackDiscontinuousData(): Set the flag for packing the discontinuous data.  To set the flag to pack the data even if the chunks are missing .  Args:         bool: Flag to indicate the packing of missing chunks. Returns:         None.
- getaccessKey(): Get the accessKey for accessing the object store.  To get the access key environment variable name.  Args:         None. Returns:         str: Name of the environment variable.
- setaccessKey(): Set the accessKey for accessing the object store.  To set the access key environment variable name.  Args:         str: Name of the environment variable. Returns:         None.
- getsecretKey(): Get the secretKey for accessing the object store.  To get the secret key environment variable name.  Args:         None. Returns:         str: Name of the environment variable.
- setsecretKey(): Set the secretKey for accessing the object store.  To set the secret key environment variable name.  Args:         str: Name of the environment variable. Returns:         None.
- getDistributorObj(): Get the distributor object.  To get the distributor object, so that it can be used in other classes of the zarrcurator viz., dispatcher.  Args:         None. Returns:         object[class Distributor]: Distributor object.
- setDistributorObj(): Set the distributor object.  To set the distributor object, so that it can be used in other classes of the zarrcurator viz., dispatcher.  Args:         object[class Distributor]: Distributor object. Returns:         None.
- getDiagnoserObj(): Get the diagnoser object.  To get the diagnoser object, so that it can be used in other classes of the zarrcurator viz., displayer.  Args:         None. Returns:         object[class Diagnoser]: Diagnoser object.
- setDiagnoserObj(): Set the diagnoser object.  To set the diagnoser object, so that it can be used in other classes of the zarrcurator viz., displayer.  Args:         object[class Diagnoser]: Diagnoser object. Returns:         None.
- getDispatcherObj(): Get the dispatcher object.  To get the dispatcher object, so that it can be used in other parts of the zarrcurator viz., utils.  Args:         None. Returns:         object[class Dispatcher]: Dispatcher object.
- setDispatcherObj(): Set the dispatcher object.  To set the dispatcher object, so that it can be used in other parts of the zarrcurator viz., utils.  Args:         object[class Dispatcher]: Dispatcher object. Returns:         None.
- toFile(): Save the config object to a JSON file.  To save the zarrcurator configuration object, so that it can be edited and used.  Args:         str: File name for storing the config object in JSON format. Returns:         None.
- fromFile(): Read the config object from a JSON file.  To read the zarrcurator configuration object, so that it can be used in the current session.  Args:         str: File name for reading the config object in JSON format. Returns:         None.

## Module: core

Source: src/zarrcurator/core.py

No docstring provided.

### Functions

#### hello()

No docstring provided.

#### helloFrom()

No docstring provided.

## Module: diagnoser

Source: src/zarrcurator/diagnoser.py

This module contains the declaration and definition of the class Diagnoser.

### Classes

#### Diagnoser

Class to Diagonose the given experiment / zarr store / variable etc and 
gather the file sizes.

##### Methods of Diagnoser

- isSingleStore(): Check whether the input path is a single zarr store.  The path is a single store if it ends with '.zarr' or is a zarr group, e.g. a group of a store written from an xarray DataTree, like 'd3hp003.zarr/P1D_mean_atm'.  Args:         path: Input path. Returns:         bool: True if the path is a single store, False if it is a directory of stores.
- get_list_of_vars(): Get the variables in a given zarr store.  For getting the list of variables in a given zarr store, by recursively scanning the  zarr store directory.  Args:         path:Path to the given zarr store. Returns:         list: List of variables found in the given store.
- list_var_files(): List all files of a variable, including chunks nested in sub directories.  Chunks separated by '/' (e.g. '0/1' in zarr v2 or 'c/0/1' in zarr v3) lie in sub directories of the variable, so the whole tree of the variable is listed.  Args:         var: Variable path (local store) or fsspec detail dict (S3 store). Returns:         list: File paths (local store) or fsspec detail dicts with their sizes (S3 store).
- file_size(): Get the size of a file of a variable.  Args:         var_file: File path (local store) or fsspec detail dict (S3 store). Returns:         int: Size of the file in bytes, None if it could not be read.
- diagnose_var(): Diagnose a single variable in a zarr store.  Lists all files of the variable first and then finds their sizes. When ZARRCURATOR_MULTITHREAD=1, the sizes of the files of a local store are found in parallel, the number of threads scaling with the number of files and capped by the available CPUs (see numThreadsForChunks); for an object store the listing already holds the sizes.  Args:         var: Variable path (local store) or fsspec detail dict (S3 store).         zarr_path: Path to zarr store. Returns:         int,int,float: Cumulative size, count and time taken for diagnosis.
- expand_groups(): Replace the sub groups among the entries of a store by their own entries.  For stores with nested groups, e.g. written from an xarray DataTree, so that each array is diagnosed on its own and named by its path from the store root.  Args:         list: Entry paths (local store) or fsspec detail dicts (S3 store).         str: Path prefix of the entries relative to the store root, e.g. 'z2/'. Returns:         list[tuple]: (entry, name) pairs, name being the path from the store root.
- diagnose_zarr_var(): Diagnose a single entry (variable or metadata file) of a zarr store.  Args:         var: Entry path (local store) or fsspec detail dict (S3 store).         zarr_path: Path to zarr store.         var_name: Name to report the entry by, e.g. its path 'z2/ocean/sst' in a store                 with nested groups; defaults to the entry's own name. Returns:         tuple: (var_name, var_size, var_chunk_count, var_time).
- loadDiagCheckpoint(): Load the checkpoint of an interrupted diagnosis of a zarr store.  Args:         checkpointFile: Path of the checkpoint file, or None.         zarr_path: Path to zarr store. Returns:         tuple: (entry name -> (name, size, count, time), list of zero-size files); empty if         there is no checkpoint or it belongs to another store.
- saveDiagCheckpoint(): Write the checkpoint of a diagnosis in progress, atomically.  Args:         checkpointFile: Path of the checkpoint file.         zarr_path: Path to zarr store.         results: Entry name -> (name, size, count, time) of the entries diagnosed so far. Returns:         None.
- diagnose_zarr(): Diagnose a single zarr store.  For diagnosing a single zarr store. When ZARRCURATOR_MULTITHREAD=1, the variables of the store are diagnosed in parallel. Arrays in nested groups are recorded by their path from the store root, e.g. 'z2/ocean/sst', and each group's metadata files likewise, e.g. 'z2/.zgroup'.  With a checkpoint file, the entries diagnosed so far are written to it every 'checkpointInterval' seconds and when the diagnosis stops on an error, and the entries it lists are not diagnosed again, so the diagnosis of a very large store can be continued in a later session. The result does not depend on the number of sessions; the caller removes the checkpoint file when the diagnosis is complete.  Args:         path: Path to zarr store.         checkpointFile: Path of the checkpoint file, or None for no checkpoints. Returns:         int:Time in secs for diagnosing.
- diagnose_experiment(): Diagnose the experiment.  For diagnosing all the zarr stores in parallel using multithreads.  Args:         None. Returns:         None.
- update(): To update the diagnoser object with the data obtained from the diagnosis of the input zarr stores.  The diagnoser object will be updated either by scanning each of the zarr stores in the input experiment path, if starting afresh or use the JSON file created from a previous diagnosis of the experiment.  Args:         None. Returns:         None.
- createStatistics(): Create statistics of the output from the entire experiment.  Generate some statistics like min, max file sizes, counts etc.  Args:         None. Returns:         None.

## Module: dispatcher

Source: src/zarrcurator/dispatcher.py

This module contains the declaration and definition of the class Dispatcher.

### Classes

#### Dispatcher

Class to Dispatch the diagnoser output to create tar balls.

##### Methods of Dispatcher

- tarExists(): Check whether a tar ball can be skipped, as it was created completely in an earlier session.  Args:         str: Path of the tar ball. Returns:         bool: True if skipping is enabled and the tar ball exists completely.
- createTarForFrequencySubGroupDict(): Create the tar balls for all the zarr stores.  For creating tar balls for all the zarr stores in the experiment and listed in the 'frequencySubgroupDict' dictionary  created by the diagnoser.  Args:         None. Returns:         None.
- createTarForFrequencySubGroups(): Create the tar balls for all the zarr stores in a given frequency.  For creating tar balls for all the zarr stores in the experiment for a given  frequency listed in the 'frequencySubgroupDict' dictionary created by the diagnoser.  Args:         str: Frequency for which the tar balls are to be created. Returns:         None.
- createTarForSubGroup(): Create the tar balls for a sub group.  For creating tar balls for a sub group based on the type and name them with a specific name.  Args:         object[Class Subgroup]: Sub group object.         str:Name of the tar ball that will be created for the subGroup. Returns:         None.
- createTarForZarr(): Create the tar balls for a sub group of type 'zarr'.  For creating tar balls for 'zarr' type sub group based on the type and and name them with a specific name.  Args:         object[Class Subgroup]: Sub group object.         str:Name of the tar ball that will be created for the subGroup. Returns:         None.
- createTarForVar(): Create the tar balls for a sub group of type 'var'.  For creating tar balls for 'var' type sub group based on the type and and name them with a specific name.  Args:         object[Class Subgroup]: Sub group object.         str:Name of the tar ball that will be created for the subGroup. Returns:         None.
- createTarForChunk(): Create the tar balls for a sub group of type 'chunk'.  For creating tar balls for 'chunk' type sub group based on the type and and name them with a specific name.  Args:         object[Class Subgroup]: Sub group object.         str:Name of the tar ball that will be created for the subGroup. Returns:         None.
- executor(): Create the tar balls.  For creating tar balls for all the subgroups with their respective names.  Args:         int:Index of the subgroup for which the tar balls are to be created. Returns:         None.

## Module: displayer

Source: src/zarrcurator/displayer.py

This module contains the declaration and definition of the class Displayer.

### Classes

#### Displayer

Class to create plots for the groups created using the distributorObj and diagnoserObj.

##### Methods of Displayer

- make_autopct(): No docstring provided.
- createPiePlotsForSubGroups(): Create Pie chart plots for the subgroups.  For creating pie chart plots for the subgroups based on the sub group distribution method.  Args:         None. Returns:         None.
- createHBarPlotsForExp(): Create horizontal bar plots for the subgroups.  For creating horizontal bar plots for the entire zarr stores in an experiment. The plots can be based on file count or file sizes.  Args:         bool:Flag to indicate if the count of the files is represented on the axis.         bool:Flag to indicate if the sizes of the files is represented on the axis. Returns:         None.
- createHBarPlotForStoreVariables(): Create horizontal bar plots for the sizes of the variables for a given zarr store.  For creating horizontal bar plots for the entire variables in a zarr store. The plots can be based on file count or file sizes.  Args:         bool:Flag to indicate if the count of the files is represented on the axis.         bool:Flag to indicate if the sizes of the files is represented on the axis. Returns:         None.
- createHBarPlotForStoreTarTapes(): Create horizontal bar plots for the sizes of the variables for a given zarr store.  For creating horizontal bar plots for the entire variables in a zarr store. The plots can be based on file count or file sizes.  Args:         bool:Flag to indicate if the count of the files is represented on the axis.         bool:Flag to indicate if the sizes of the files is represented on the axis. Returns:         None.

## Module: distributor

Source: src/zarrcurator/distributor.py

This module contains the declaration and definition of the class Distributor.

### Classes

#### Distributor

Distribute the list of tuples of type (variable ,size) into different sub groups,
either equal size or based on target size specified by user etc.

##### Methods of Distributor

- setFrequencySubGroupDict(): To set the frequency subGroup dictionary directly from JSON file.          To set frequencySubGroupDict directly, if  for example, loaded from JSON file from an earlier run of 'zarrcurator'.  Args:         frequencySubGroupDict[dict]: Dictionary of the frequencies and subGroups.  Returns:         None.
- getFrequencySubGroupDict(): To get the frequency subGroup dictionary directly.          To get frequencySubGroupDict directly, if  for example, from utils of 'zarrcurator'.  Args:         None.  Returns:         frequencySubGroupDict[dict]: Dictionary of the frequencies and subGroups.
- updateFrequencyGroupDict(): To create the dictionary per frequency and it's groups.  For storing the file sizes and counts for each zarr store per frequency in a dictionary.  Args:         None. Returns:         None.
- updateFrequencySubGroupDictWithSingleZarrStore(): To update the sub group dictionary per frequency with single subgroup of type 'zarr'.  For initializing each of the zarr stores (per freq and healpix) in the sub group dictionary with sub group of type 'zarr', if the size of the entire zarr store is less than the target size.  Args:         None. Returns:         None.
- updateFrequencySubGroupDictWithTargetSize(): To update the sub group dictionary per frequency with subgroups of size as per target size.  For updating each of the zarr stores (per freq and healpix) in the sub group dictionary with sub group whose size is greater than the target size and splitting the sub groups  into more subgroups if larger than the target size.   Args:         None. Returns:         None.
- groupEntriesByGroup(): To sort the entries of a zarr store by the group they belong to.  For stores with nested groups (e.g. written from an xarray DataTree), the entries are named by their path from the store root, e.g. 'multiscales/zoom_11/tas', and belong to the group of that path, e.g. 'multiscales/zoom_11'. Each group is distributed on its own, so that a subgroup, and so a tarball, holds the arrays of a single group, e.g. of a single HEALPix zoom level. Groups with metadata files only (e.g. the store root above 'multiscales') are added to the first group with arrays; the dispatcher adds the metadata of the enclosing groups to every tarball anyway. For a store without nested groups all entries belong to the root group ''.  Args:         dict: Entry name -> {'size', 'count'} for the entries of a zarr store. Returns:         dict: Group path -> list of (entry name, size), groups sorted by path.
- split_zarr_into_equalSized_bins(): To split a zarr store larger than the target size into subgroups.  The entries of each group of the store (see groupEntriesByGroup) are split on their own, so that a subgroup never mixes the arrays of different groups, e.g. of different HEALPix zoom levels of a store written from an xarray DataTree. Within a group, each array larger than the target size becomes a subgroup of type 'chunk', the other entries are packed into subgroups of type 'var' of about equal size. The metadata files of a group whose arrays are all split into chunk subgroups are left out, as the chunk tarballs carry them.  Args:         dict: Entry name -> {'size', 'count'} for the entries of a zarr store, plus its               'size' and 'count'. Returns:         list[SubGroup]: Per group, its subgroups of type 'var', then those of type 'chunk';         each with the path of its group as 'groupPath', e.g. 'multiscales/zoom_11'.
- packEntries(): To pack entries smaller than the target size into subgroups of type 'var' of about equal size.  The number of subgroups is the total size divided by the target size, rounded; the entries are added from the smallest to the largest, each to the subgroup with the smallest size.  Args:         list[tuple]: (entry name, size) of the entries. Returns:         list[SubGroup]: Non-empty subgroups of type 'var'.
- redistributeSubGroups(): To redistribute the subgroups.  For redistributing each of the zarr stores (per freq and healpix) in the sub group dictionary based on each of the sub group and it's size in comparison with the target size,by splitting  the sub groups into more subgroups if their size is larger than the target size.   Args:         obj: None. Returns:         None.
- subGroupLabels(): To get the labels naming the subgroups of the groups of a zarr store.  A group is labelled by its name, e.g. 'zoom_11' for 'multiscales/zoom_11', or by its path with '_' for '/' if several groups have that name, e.g. 'atmos_zoom_0' and 'ocean_zoom_0'. The root group '' has no label.  Args:         list[str]: Group paths, e.g. ['multiscales/zoom_0', 'multiscales/zoom_11']. Returns:         dict: Group path -> label.
- updateDimensionsToSubGroups(): To update the dimensions to the subgroups.  For each of the sub group dictionary based on it's type, for the 'var' and 'chunk' types, the  dimensions of the original zarr store are to be appended, so that the tar ball is self-contained and could be utiized by the downstream applications.   Args:         obj: None. Returns:         None.
- getZarrstoreDimensions(): To get the coordinate variables of the zarr store.  For getting the coordinate variables of the original zarr store, which are to be appended to the tar balls. These are the dimension coordinates (arrays named after a dimension, e.g. 'time' or the HEALPix 'cell'), the auxiliary coordinates listed in the 'coordinates' attribute and the variables named in the 'grid_mapping' attribute. Dimension names are read from '_ARRAY_DIMENSIONS' (zarr v2) or 'dimension_names' (zarr v3).  For stores with nested groups (e.g. written from an xarray DataTree), the coordinates used by the arrays of each of the given groups are collected. As a group can use the coordinates of its parent groups, each coordinate is looked up in the group itself first and then in its parents up to the store root.   Args:         str: Frequency of the model data.          str: Path to the location of the zarr store.         list[str]: Group paths relative to the store root, e.g. ['z2/ocean']; defaults to the root group ''. Returns:         list: sorted list of (coordinate variable path, size) tuples.
- update(): To update the distributor object with the data obtained from the distribution of the input zarr stores.  The distributor object will be updated either by scanning each of the zarr stores in the input experiment path, if starting afresh or use the JSON file created from a previous distribution of the experiment.  Args:         None. Returns:         None.

## Module: oceanVarsYAML

Source: src/zarrcurator/oceanVarsYAML.py

No docstring provided.

## Module: storetree

Source: src/zarrcurator/storetree.py

This module contains helpers for walking the group hierarchy of a zarr store,
e.g. a store written from an xarray DataTree, with nested groups.

### Functions

#### isZarrGroupDir()

Check whether a directory is a zarr group.

A zarr v2 group holds a '.zgroup' file, a zarr v3 group a 'zarr.json' file
with node_type 'group'. Array directories and plain directories are not groups.

Args:
        path[str]: Path of the directory.
        fs[object]: fsspec file system object for object stores, None for local stores.
Returns:
        bool: True if the directory is a zarr group.

#### listArrayPaths()

List the paths of all arrays in a zarr group and its sub groups.

Works for zarr v2 and v3 groups, with or without consolidated metadata.

Args:
        group[zarr.Group]: Opened zarr group, usually the root of the store.
Returns:
        list[str]: Sorted array paths relative to the group, e.g. ['time', 'z2/ocean/sst'].

#### groupAncestors()

List the groups enclosing a store member, from the root down.

Args:
        path[str]: Path of the member relative to the store root, e.g. 'z2/ocean/sst'.
Returns:
        list[str]: Group paths relative to the store root, '' being the root,
        e.g. ['', 'z2', 'z2/ocean'].

#### nestDiagReport()

Nest a diagnosis keyed by entry path by its groups, as for the '.check' report.

``{store: {"z2/ocean/sst": {...}, "size": N, "count": N}}`` becomes
``{store: {"z2": {"ocean": {"sst": {...}}}, "size": N, "count": N}}``.
Entries are marked with ``"type": "array"``, or ``"type": "file"`` for metadata
files such as ``zarr.json``, and carry their ``path``; all other dicts are groups.
Each group holds the totals of its entries and sub groups under ``"__total__"``,
e.g. ``{"size": N, "count": N}``; the totals of each store (``size``, ``count``)
stay at the store level.

Args:
        flatDiag[dict]: Diagnosis keyed by store, then by entry path from the store root.
Returns:
        dict: Diagnosis keyed by store, then nested by group.

#### addGroupTotals()

Add the totals of a group of a nested diagnosis, including its sub groups.

Args:
        group[dict]: Group of a nested diagnosis, updated in place.
Returns:
        tuple: (size, count) of the group.

#### flattenDiagReport()

Flatten a diagnosis nested by group to one keyed by entry path.

The inverse of nestDiagReport; a diagnosis that is already keyed by entry path
(written by older versions) is returned unchanged.

Args:
        nestedDiag[dict]: Diagnosis keyed by store, then nested by group.
Returns:
        dict: Diagnosis keyed by store, then by entry path, e.g. ``z2/ocean/sst``.

#### nestDistReport()

Nest the members of each subgroup of a distribution by their groups, as for the '.diag' file.

The ``groupMembers`` of a subgroup, a list of ``[member, size]``, becomes a tree keyed by the
path of each member from the store root, e.g. ``{"z2": {"ocean": {"sst": {...}}}}``. Members
are given by their path from the store root or by absolute path (e.g. coordinate variables);
a member that is the store itself (subgroup of type 'zarr') is keyed by the store name.
Each member is marked with ``"type"`` ('store', 'array' or 'file') and carries its original
name as ``path``, its ``size`` and its position in the list as ``index``, as the order of the
members matters, e.g. the first member of a 'chunk' subgroup is the array to split. Each group
holds the totals of its members under ``"__total__"``, e.g. ``{"size": N, "members": N}``.
The other fields of the subgroups are kept as they are.

Args:
        flatDist[dict]: Distribution keyed by frequency, then by subgroup, with the
                subgroups as dictionaries (see subGroup_to_dict).
        storePath[str]: Path of the zarr store the members belong to.
Returns:
        dict: Distribution with the members of each subgroup nested by group.

#### addMemberTotals()

Add the totals of a group of the members of a subgroup, including its sub groups.

Args:
        group[dict]: Group of nested subgroup members, updated in place.
Returns:
        tuple: (size, number of members) of the group.

#### flattenDistReport()

Flatten the members of each subgroup of a distribution nested by group.

The inverse of nestDistReport: the ``groupMembers`` of each subgroup become the list of
``[member, size]`` in their original order. Subgroups whose members are already a list
(written by older versions) are kept as they are.

Args:
        nestedDist[dict]: Distribution with the members of each subgroup nested by group.
Returns:
        dict: Distribution with the members of each subgroup as a list.

## Module: subgroup

Source: src/zarrcurator/subgroup.py

This module contains the declaration and definition of the class SubGroup.

### Functions

#### subGroup_to_dict()

No docstring provided.

#### subGroup_from_dict()

No docstring provided.

### Classes

#### SubGroup

Class to create subGroups of type 'zarr', 'var' or 'chunk' based on the size of the zarr store.

##### Methods of SubGroup

- groupSize(): To get the group size of the subGroup.  To get the type of the subGroup.  Args:         None. Returns:         int: Size of the subGroup.
- groupSize(): To compute the size of the subGroup.  To compute the size of the subGroup by adding up the subGroup members.  Args:         int: To set the groupsize to the variable. Returns:         None.
- setGroupType(): To set the type of the subGroup.  To set the type of the subGroup.  Args:         str: Type of the subGroup 'zarr', 'var' or 'chunk'. Returns:         None.
- getGroupType(): To get the type of the subGroup.  To get the type of the subGroup.  Args:         None. Returns:         str: Type of the subGroup 'zarr', 'var' or 'chunk'.
- setGroupTarMembers(): To set the tar file names for the subGroup.  To set the list of tar file names for the tarballs produced for the subGroup.  Args:         list[str]: List of tar file names. Returns:         None.
- getTarMembers(): To get the tar file names for the subGroup.  To get the list of tar file names for the tarballs produced for the subGroup.  Args:         None. Returns:         list[str]: List of tar file names.
- setgroupTarTapeIDs(): To set the tape IDs for the tar file names for the subGroup.  To set the list of tape IDs for the tar file names for the tarballs produced for the subGroup.  Args:         list[str]: List of tape IDS for tar file names. Returns:         None.
- getTarTapeIDs(): To get the tape IDs for the tar file names for the subGroup.  To get the list of tape IDs for the tar file names for the tarballs produced for the subGroup.  Args:         None. Returns:         list[str]: List of tape IDs for tar file names.
- updateSubGroup(): To update the subGroup object with diagnoser object with the data obtained from the diagnosis of the input zarr stores.  The diagnoser object will be updated either by scanning each of the zarr stores in the input experiment path, if starting afresh or use the JSON file created from a previous diagnosis of the experiment.  Args:         list[tuple] or tuple: Tuple or list of tuples to update the SubGroup object. Returns:         None.
- updateSubGroupSize(): To update the subGroup size.  To update the subgroup size by adding up the sizes of the subGroup members.  Args:         None. Returns:         None.

## Module: synthetic_store

Source: src/zarrcurator/synthetic_store.py

Synthetic Zarr experiment generator for zarrcurator.

This module creates local Zarr stores with predictable naming and metadata so
core zarrcurator workflows can be tested end-to-end.

Examples:
  python -m zarrcurator.synthetic_store --output-dir tests/data/synthetic_experiment
  python -m zarrcurator.synthetic_store --output-dir tests/data/synthetic_experiment --run-smoke
  python -m zarrcurator.synthetic_store --output-dir /tmp/layouts --separators .,/
  python -m zarrcurator.synthetic_store --output-dir /tmp/all --separators .,/ --shards 4,4,8 --layouts flat,tree

### Functions

#### store_variant_tag()

Return the tag of a store variant in store names, e.g. 'z2', 'z2slash', 'z3shard', 'z3dotshardtree'.

Only what differs from the default (format default separator, no sharding, flat) is added.
The tag has no '_', as store names are split on '_' by the dispatcher.

#### create_synthetic_experiment()

Create an experiment directory containing multiple synthetic stores.

One set of stores is created per combination of zarr format, entry in ``separators``
(None: only the format default), sharding and entry in ``layouts`` (None: only 'flat').
With ``shards``, the zarr v3 stores are created both without and with sharding of the data
variables. The variant is tagged in the store name, see store_variant_tag(), e.g.
``syntheticexp_P1D_000_z2slash.zarr`` or ``syntheticexp_P1D_000_z3shardtree.zarr``.

#### run_smoke_pipeline()

Run diagnose/distribute/dispatch on the generated synthetic experiment.

#### parse_args()

No docstring provided.

#### main()

No docstring provided.

## Module: utils

Source: src/zarrcurator/utils.py

This module contains certain utility functions that will be exposed to the user to perform various tasks.

### Functions

#### usage()

Help about the usage of zarrcurator.
Returns: 
        None.

#### saveConfigToFile()

Saving the zarrcurator config to file.

Saving the zarrcurator library configuration as a JSON file.

Args:
        configFileName    : File name in which to store the configuration.
Returns:
        None.

#### loadConfigFromFile()

Loading the zarrcurator config from file.

Reading the zarrcurator library configuration from a JSON file.

Args:
        configFileName    : File name in which to store the configuration.
Returns:
        None.

#### setObjectStoreCredentials()

Set object-store credentials for the current process.

Accepts either raw key values or environment variable names that contain
those values. Resolved values are exported to AWS/S3 standard environment
variables and wired into configObj for downstream filesystem creation.

Args:
        accessKey[str]: Access key value or env-var name containing it.
        secretKey[str]: Secret key value or env-var name containing it.
Returns:
        None.

#### updateStoretoConfig()

Update the store location to the config object.

To update the store location to the config object, to be used by other functions in the zarrcurator library.

Args:
        storeLocation[str]: Location of the zarr store.
        accessKey[str]: Optional access key value/env-var name.
        secretKey[str]: Optional secret key value/env-var name.
Returns:
        None.

#### nestCheckReport()

Nest a check report keyed by array path by its groups.

``{"/z2/ocean/sst": {...}}`` becomes ``{"z2": {"ocean": {"sst": {...}}}}``.
Array entries are marked with ``"type": "array"`` and carry their ``path``;
all other dicts are groups.

Args:
        flatReport[dict]: Report keyed by array path.
Returns:
        dict: Report nested by group.

#### flattenCheckReport()

Flatten a check report nested by group to one keyed by array path.

The inverse of nestCheckReport; a report that is already keyed by array
path (written by older versions) is returned as it is.

Args:
        nestedReport[dict]: Report nested by group.
Returns:
        dict: Report keyed by array path, e.g. ``/z2/ocean/sst``.

#### findMissingChunksInStore()

Finding missing chunks in a zarr store.

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

#### initialize()

Initializing the zarrcurator.

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

#### diagnose()

Perform the diagnosis of the input directory containing the various zarr stores.

Creates the object of class Diagnoser, to explore the contents of each zarr store and gather the count, sizes 
of the files inside them.

Args:
        None.            
Returns: 
        None.

#### diagnoseStore()

Perform the diagnosis of the input zarr store.

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

#### display()

Displays the output of the diagnoser object, by creating various plots.

Creates the object of class Displayer, to create bar plots, pie charts of the output generated by the diagnoser object viz.,
count, sizes of the files for each of the input zarr store, the constraints of the HSM system.

Args:
        None.            
Returns: 
        None.

#### running_in_jupyter()

No docstring provided.

#### displayStoreSunburst()

Displays the output of the diagnoser object, by creating sunburst plot for the input zarr store.

Creates the object of class Displayer, to create sunburst plot of the output generated by the diagnoser object viz.,
count, sizes of the files for each of the variables in the input zarr store.

Args:
        storeLocation[str]: Location of the zarr store.
        accessKey[str]: Optional access key value/env-var name.
        secretKey[str]: Optional secret key value/env-var name.
Returns: 
        None.

#### displayZarrStoreVariables()

Displays the output of a given zarr store from the diagnoser object , by creating variable sizes plot.

Creates create bar plots of the input zarr store from output generated by the diagnoser object viz.,
count, sizes of the files for each of the variable in the input zarr store.

Args:
        zarrStore[str]: Name of the zarr store.
        fileCount[int]: Flag to indicate if file counts are to be plotted.
        byteBins[int]: Flag to indicate if file sizes are to be plotted.
Returns: 
        None.

#### distribute()

Distribute the output of the diagnoser object into subgroups of 'zarr', 'var' and 'chunk'.

Creates the object of class Distributor, to create subgroups of 'zarr', 'var' and 'chunk', based on the size of the
contents of the zarr store and the constraints of the HSM system.

Args:
        None.            
Returns: 
        None.

#### distributeStoreToSubStores()

Distribute the output of the diagnoser object into subgroups.

Creates the object of class Distributor, to create subgroups of 'zarr', 'var' and 'chunk', based on the size of the
contents of the zarr store and the constraints of the HSM system.

#### checkStoreOpensWithXarray()

Check that a zarr store can be opened with xarray, with all its groups.

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

#### dispatchStoreToTarStores()

Dispatch the output of the distributor object into tarballs.

Creates the object of class Dispatcher, to create tarballs for each of the subgroups of 'zarr', 'var' and 'chunk'.
Fails with a ValueError before diagnosing, distributing or creating tarballs if the store cannot be
opened with xarray, see checkStoreOpensWithXarray().

#### createKerchunkReferenceFileForTar()

Create kerchunk reference file for given tar file.

To generate the kerchunk reference file in JSON format for the contents of the input tar archive.

Args:
        tarFileName[str]: Path of the tar archive.
Returns: 
        None.

#### mergeKerchunkReferences()

Merge the Kerchunk references of the tarballs of a zarr store into the references of the store.

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

#### convertKerchunkReferenceFilesOfZarrStoreToParquet()

Convert given Kerchunk reference file to parquet file.

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

#### updateArchBasePath()

Update the base path of the tape archive.

To set the base path on the tape archive under which the tarballs created for each of the subgroups of 'zarr', 'var' and 'chunk' are stored.

Args:
        archBasePath[str]: Path on the tape archive.            
Returns: 
        None.

#### updateTarToTapeMapper()

Update the mapper for tarfiles and tape IDs.

To update the mapper which maps the input tar file to the ID of the tape on which this tar file resides.

Args:
        tarFile[str]: Path on the tar file.            
Returns: 
        None.

#### mapTapeIDsToFrequencySubGroupDict()

Update the tape IDs to the FrequencySubGroupDict.

Creates the list of tape IDs for the tarballs of each subgroup in the FrequencySubGroupDict. To be called after the tarballs
are transferred to the HSM tapes.

Args:
        None
Returns: 
        None.

#### displayZarrStoresTarTapes()

Displays the tar ball count and tape count for the zarr stores.

Creates create bar plots for the tar balls and tape counts for all the zarr stores.

Args:
        None.
Returns: 
        None.

#### displayZarrStoreVarTarTapes()

Displays the tar ball count and tape count for a given variable of a zarr store.

Creates create bar plots for the tar balls and tape counts for a particular variable from a zarr store.

Args:
        zarrStoreInput[str]: Name on the zarr store.
        varInput[list(str)]: List of names of the variables.
Returns: 
        None.

## Module: zarrmetadata

Source: src/zarrcurator/zarrmetadata.py

This module contains helpers for translating zarr v3 metadata (zarr.json) to zarr v2
metadata (.zgroup, .zarray, .zattrs), so that the chunks of zarr v3 stores can be
referenced by Kerchunk, which combines references in the zarr v2 layout.

The chunk bytes are referenced unchanged, so only codecs with a zarr v2 equivalent are
supported: the 'bytes' codec followed by at most one compressor. 'transpose' and chained
compressors raise a ValueError.

Sharded arrays ('sharding_indexed' codec) are translated to zarr v2 arrays of their inner
chunks: each shard ends (or starts) with an index of the offset and size of its inner
chunks, which is read to reference each inner chunk as a byte range within the shard.
The inner codecs follow the rules above; nested sharding raises a ValueError.

### Functions

#### v3CodecsToV2()

Translate the codecs of a zarr v3 array to a zarr v2 compressor.

Args:
        list[dict]: The 'codecs' of the zarr v3 array metadata.
Returns:
        tuple: (endian, compressor), endian being 'little' or 'big' and compressor
        the zarr v2 compressor configuration or None.

#### v3MetadataToV2()

Translate the zarr v3 metadata of a group or array to zarr v2 metadata files.

The dimension names become the '_ARRAY_DIMENSIONS' attribute. xarray keeps the fill value
in the '_FillValue' attribute of zarr v3 arrays, in zarr v2 it is the array's fill_value,
which xarray reads as '_FillValue'. So an array without '_FillValue' and a zero fill value
gets no fill value; zarr v2 reads missing chunks (not written as they hold only the fill
value) as zeros then as well. A non-zero fill value is kept so missing chunks read correctly,
though xarray then masks it.

Args:
        dict: Content of a zarr v3 'zarr.json' file.
Returns:
        dict: zarr v2 file name ('.zgroup', '.zarray', '.zattrs') -> content.

#### v3ShardingLayout()

Get the layout of the shards of a sharded zarr v3 array.

Args:
        dict: Content of the zarr v3 'zarr.json' file of an array.
Returns:
        dict or None: None for an array without sharding, else 'shape' (of the array),
        'shard_shape', 'chunk_shape' (of the inner chunks), 'codecs' (of the inner chunks),
        'index_location' ('start' or 'end'), 'index_endian', 'index_checksum' (bool) and
        'index_size' (bytes).

#### shardChunkReferences()

Get the references of the inner chunks of a shard.

Args:
        list: Reference of the shard, [url, offset, size].
        str: Dot-separated zarr v2 key of the shard, relative to the array, e.g. '1.0'.
        dict: Layout of the shards, see v3ShardingLayout().
        callable: read_range(url, start, end) returning the bytes in [start, end) of url.
Returns:
        list[tuple]: (dot-separated key of the inner chunk relative to the array, [url, offset, size])
        for every inner chunk in the shard that is written and lies within the array.
Raises:
        ValueError: If the checksum of the shard index does not match.

#### v3ChunkKeyToV2()

Translate a chunk key of a zarr v3 array, relative to the array, to the dot-separated zarr v2 form.

Args:
        str: Chunk key, e.g. 'c/0/1' or 'c.0.1' ('default' encoding) or '0/1' ('v2' encoding).
        dict: The 'chunk_key_encoding' of the zarr v3 array metadata.
Returns:
        str: zarr v2 chunk key, e.g. '0.1'.
