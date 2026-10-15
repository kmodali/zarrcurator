"""
This module contains the declaration and definition of the class Diagnoser. 
"""

#Standard modules
import os
import sys
import glob
import time
import json
import logging
import collections
import concurrent.futures
from rich import print as richprint


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

#Non-Standard modules
try:
    import fsspec
except:
    print( sys.exc_info() )
    print( f"Module 'fsspec' import error in {__file__}" )

#Local modules
try:
    from .config import configObj
except:
    print( sys.exc_info() )
    print( f"Module 'config' import error in {__file__}" )

try:
    from .chunkkeys import numThreadsForChunks, maxThreads
except:
    print( sys.exc_info() )
    print( f"Module 'chunkkeys' import error in {__file__}" )

try:
    from .storetree import isZarrGroupDir, flattenDiagReport
except:
    print( sys.exc_info() )
    print( f"Module 'storetree' import error in {__file__}" )

# Diagnoser
class Diagnoser:
    """ Class to Diagonose the given experiment / zarr store / variable etc and 
        gather the file sizes.
    """
    
    def __init__( self ):

        self.exp_path = configObj.getZarrStorePath()
        """path: Path of the zarr stores.
        The directory under which the zarr stores for each healpix and frequency combination exist. 
        """

        self.fileSystemObj = configObj.getFileSystemObj()
        """obj: File system object.
        The file system object for the URL under which the zarr stores for each healpix and frequency combination exist. 
        """

        self.jsonFile = configObj.getJsonFile()
        """str: Name of the jsonFile produced by zarrcurator.
        The JSON file contains the output[file sizes, count] of the diagnosis of the input zarr stores.
        """

        self.outputDir = configObj.getWorkingDir()
        """path: Path to working directory.
        The location of the directory under which the output prouced by zarrcurator tool will be stored.
        """

        self.zeroSizeFilesFlag = False
        """bool: Flag to indicate if zero size files exist.
        The input zarr stores could contain some chunks with zero size.This flag is used to indicate that such
        chunks are encountered during the diagnosis.
        """

        self.zeroSizeFilesDict = collections.defaultdict(list) #"Diagnoser_errorFile.log"
        """dict: Dictionary of zero size files per each zarr store.
        The dictionary of zero size files encountered in the input zarr stores.
        """

        self.missingFilesDict = {} #"Diagnoser_missingFile.log"
        """dict: Dictionary of missing files per each zarr store.
        The dictionary of missing files encountered in the input zarr stores.
        """

        self.missingFilesFlag = False
        """bool: Flag to indicate if missing files exist.
        The input zarr stores could contain some missing chunks.This flag is used to indicate that such
        chunks are encountered during the diagnosis.
        """

        self.var_size_dict = {}
        """dict: Dictionary containing the sizes of the files for each variable.
        The dictionary of file sizes, count for each variable in a given zarr store from the input zarr stores.
        """

        self.exp_size_dict = {}
        """dict: Dictionary containing the sizes for all the zarr stores.
        The dictionary of file sizes, count, variable for all the input zarr store.
        """

        self.sorted_tuplelist_obj = []
        """dict: Dictionary containing tuples of the variables and sizes.
        The dictionary containing tuples of variables and file sizes, arranged in an ascending order.
        """

        self.list_of_zarrs = []
        """list: List of zarr stores found in the input directory.
        The list of zarr stores in the input directory.
        """
        
        if self.fileSystemObj is not None : # Object store case

            #The experiment path is itself a zarr store or a group inside one, single store case
            if self.isSingleStore( self.exp_path ) :
                if  self.fileSystemObj.exists( self.exp_path.strip( os.path.sep )  )  : # check if the zarr store exists
                    self.list_of_zarrs = [ self.exp_path.strip( os.path.sep ) ]
                            # Error in input path, neither a directory nor a zarr store
                else : 
                    self.list_of_zarrs = None

            else : # List of stores in the experiment path                 
                self.list_of_zarrs = self.fileSystemObj.listdir( self.exp_path,detail = False )
                self_path = self.exp_path.replace( 'https://swift.dkrz.de/v1','swift://swift.dkrz.de' )

                # strip the trailing file path separator
                self.list_of_zarrs = [ store.strip( os.path.sep ) for store in self.list_of_zarrs ]
                
                # For swift object store the list contains self path too!
                if self_path in self.list_of_zarrs :
                    self.list_of_zarrs.remove( self_path )

        else : # Local directory case
            # Error case check, as the input path should be a directory containing,
            # zarr stores or a single zarr store, but not a file
            if os.path.isdir( self.exp_path ) : 
                # Single store case, the store itself or a group inside it
                if self.isSingleStore( self.exp_path ) :
                    if os.path.exists( self.exp_path ) : # check if the zarr store exists
                        logger.debug("Diagnoser single-store path detected: %s", self.exp_path)
                        # strip only the trailing separator, so that absolute paths stay absolute
                        self.list_of_zarrs = [ self.exp_path.rstrip( os.path.sep ) ]
                    else : 
                        self.list_of_zarrs = None                    
                else : # Multiple stores case
                    self.list_of_zarrs = glob.glob( os.path.join( self.exp_path, "*.zarr" ), recursive=True )
            # Error in input path, neither a directory nor a zarr store
            else : 
                self.list_of_zarrs = None
                
        if self.list_of_zarrs is None:
            logger.error("Invalid input path for zarr stores: %s", configObj.getZarrStorePath())
            sys.exit(1)

        if len( self.list_of_zarrs ) == 0:
            logger.error("No zarr stores found at input path: %s", configObj.getZarrStorePath())
            sys.exit(1)

        # For debugging use a subset of self.list_of_zarrs
        logger.info("Diagnoser initialized with %d zarr store(s)", len(self.list_of_zarrs))
        self.list_of_zarrs =  self.list_of_zarrs


    def isSingleStore( self, path ):
        """Check whether the input path is a single zarr store.

        The path is a single store if it ends with '.zarr' or is a zarr group, e.g. a group
        of a store written from an xarray DataTree, like 'd3hp003.zarr/P1D_mean_atm'.

        Args:
                path: Input path.
        Returns:
                bool: True if the path is a single store, False if it is a directory of stores.
        """

        path = path.rstrip( os.path.sep )
        if path.endswith('.zarr'):
            return True
        if self.fileSystemObj is None:
            return os.path.isdir( path ) and isZarrGroupDir( path )
        return isZarrGroupDir( path, self.fileSystemObj )


    def get_list_of_vars( self, zarr_path ):
        """Get the variables in a given zarr store.

        For getting the list of variables in a given zarr store, by recursively scanning the 
        zarr store directory.

        Args:
                path:Path to the given zarr store.
        Returns:
                list: List of variables found in the given store.
        """

        list_of_vars = None
        # MKM 7 Mar 2026 added 'include_hidden = True'
        if os.path.isdir( zarr_path ):
            list_of_vars = glob.glob( os.path.join( zarr_path, "*" ),
                                                       recursive=True, include_hidden=True )
        else:
            list_of_vars = None
        return list_of_vars
    
    
    def list_var_files( self, var ):
        """List all files of a variable, including chunks nested in sub directories.

        Chunks separated by '/' (e.g. '0/1' in zarr v2 or 'c/0/1' in zarr v3) lie in
        sub directories of the variable, so the whole tree of the variable is listed.

        Args:
                var: Variable path (local store) or fsspec detail dict (S3 store).
        Returns:
                list: File paths (local store) or fsspec detail dicts with their sizes (S3 store).
        """

        if self.fileSystemObj is None:
            return [ os.path.join( root, fileName ) for root, _, fileNames in os.walk( var ) for fileName in fileNames ]
        # A single recursive listing, which already holds the sizes of the objects
        objects = self.fileSystemObj.find( var['name'], detail=True )
        return [ info for info in objects.values() if info.get('type') == 'file' ]


    def file_size( self, var_file ):
        """Get the size of a file of a variable.

        Args:
                var_file: File path (local store) or fsspec detail dict (S3 store).
        Returns:
                int: Size of the file in bytes, None if it could not be read.
        """

        try:
            if self.fileSystemObj is None:
                return os.stat( var_file ).st_size
            return var_file['size']
        except ( OSError, KeyError ) as e:
            logger.warning("Finding file size failed for %s error=%s", var_file, e)
            return None


    def diagnose_var( self, var, zarr_path ):
        """Diagnose a single variable in a zarr store.

        Lists all files of the variable first and then finds their sizes. When
        ZARRCURATOR_MULTITHREAD=1, the sizes of the files of a local store are found
        in parallel, the number of threads scaling with the number of files and capped
        by the available CPUs (see numThreadsForChunks); for an object store the listing
        already holds the sizes.

        Args:
                var: Variable path (local store) or fsspec detail dict (S3 store).
                zarr_path: Path to zarr store.
        Returns:
                int,int,float: Cumulative size, count and time taken for diagnosis.
        """

        start = time.time()

        var_files = self.list_var_files( var )
        num_files = len( var_files )
        numThreads = numThreadsForChunks( num_files )
        multiThread = os.getenv('ZARRCURATOR_MULTITHREAD') == '1'

        if multiThread and numThreads > 1 and self.fileSystemObj is None:
            logger.debug("diagnose_var files=%d threads=%d", num_files, numThreads)
            with concurrent.futures.ThreadPoolExecutor( max_workers=numThreads ) as executor:
                sizes = list( executor.map( self.file_size, var_files ) )
        else:
            logger.debug("diagnose_var files=%d threads=1", num_files)
            sizes = [ self.file_size( var_file ) for var_file in var_files ]

        total_var_size = 0
        for var_file, size in zip( var_files, sizes ):
            if size is None:
                continue
            total_var_size += size
            if size == 0:
                name = var_file if self.fileSystemObj is None else var_file['name']
                logger.warning("Zero-sized file encountered: %s", name)
                self.zeroSizeFilesDict[zarr_path.split('.')[0]].append( name )
                self.zeroSizeFilesFlag = True

        stop = time.time()
        return total_var_size, num_files, (stop-start)


    def expand_groups( self, zarr_vars, prefix='' ):
        """Replace the sub groups among the entries of a store by their own entries.

        For stores with nested groups, e.g. written from an xarray DataTree, so that each
        array is diagnosed on its own and named by its path from the store root.

        Args:
                list: Entry paths (local store) or fsspec detail dicts (S3 store).
                str: Path prefix of the entries relative to the store root, e.g. 'z2/'.
        Returns:
                list[tuple]: (entry, name) pairs, name being the path from the store root.
        """

        expanded = []
        for var in zarr_vars:
            if self.fileSystemObj is None:
                name = prefix + var.split(os.path.sep)[-1]
                if os.path.isdir(var) and isZarrGroupDir(var):
                    expanded.extend( self.expand_groups( self.get_list_of_vars(var), name + '/' ) )
                    continue
            else:
                name = prefix + var['name'].rstrip('/').split('/')[-1]
                if var['type'] == 'directory' and isZarrGroupDir(var['name'], self.fileSystemObj):
                    expanded.extend( self.expand_groups( self.fileSystemObj.listdir(var['name'], detail=True), name + '/' ) )
                    continue
            expanded.append( (var, name) )
        return expanded


    def diagnose_zarr_var( self, var, zarr_path, var_name=None ):
        """Diagnose a single entry (variable or metadata file) of a zarr store.

        Args:
                var: Entry path (local store) or fsspec detail dict (S3 store).
                zarr_path: Path to zarr store.
                var_name: Name to report the entry by, e.g. its path 'z2/ocean/sst' in a store
                        with nested groups; defaults to the entry's own name.
        Returns:
                tuple: (var_name, var_size, var_chunk_count, var_time).
        """

        entry_name = var_name
        var_name = ''
        var_size = 0
        var_chunk_count = 0
        var_time = 0.0

        # Check local store or S3 store
        if self.fileSystemObj is None: # Local directory store
            var_name = var.split(os.path.sep)[-1]
            logger.debug("diagnose_zarr variable=%s", var_name)

            # Check if file .zmetadata or .zgroup or .zattrs etc., 
            if os.path.isfile(var):                        
                var_size = os.stat(var).st_size
                var_chunk_count = 1
            else:
                var_size, var_chunk_count, var_time = self.diagnose_var( var, zarr_path )
        else: # S3 store        
            var_name = var['name'].split(os.path.sep)[-1]
            logger.debug("diagnose_zarr variable=%s", var_name)
            if var['type'] == 'file' :
                try:                            
                    var_size = var['size']
                    var_chunk_count = 1
                except Exception as e:
                    logger.warning("Metadata size read failed for %s error=%s", var, e)
            else: # call diagnose_var
                var_size, var_chunk_count, var_time = self.diagnose_var( var, zarr_path )

        if entry_name is not None:
            var_name = entry_name
        return var_name, var_size, var_chunk_count, var_time


    checkpointInterval = 30
    """int: Seconds between two writes of the checkpoint file of a diagnosis, see diagnose_zarr()."""


    def loadDiagCheckpoint( self, checkpointFile, zarr_path ):
        """Load the checkpoint of an interrupted diagnosis of a zarr store.

        Args:
                checkpointFile: Path of the checkpoint file, or None.
                zarr_path: Path to zarr store.
        Returns:
                tuple: (entry name -> (name, size, count, time), list of zero-size files); empty if
                there is no checkpoint or it belongs to another store.
        """

        if checkpointFile is None or not os.path.isfile( checkpointFile ):
            return {}, []
        try:
            with open( checkpointFile ) as f:
                checkpoint = json.load( f )
        except ( OSError, ValueError ) as e:
            logger.warning("Ignoring unreadable checkpoint file %s error=%s", checkpointFile, e)
            return {}, []
        if checkpoint.get( 'store' ) != zarr_path:
            logger.warning("Ignoring checkpoint file %s of another store %s", checkpointFile, checkpoint.get( 'store' ))
            return {}, []
        entries = { name: ( name, entry['size'], entry['count'], entry.get( 'time', 0.0 ) )
                    for name, entry in checkpoint.get( 'entries', {} ).items() }
        return entries, list( checkpoint.get( 'zeroSizeFiles', [] ) )


    def saveDiagCheckpoint( self, checkpointFile, zarr_path, results ):
        """Write the checkpoint of a diagnosis in progress, atomically.

        Args:
                checkpointFile: Path of the checkpoint file.
                zarr_path: Path to zarr store.
                results: Entry name -> (name, size, count, time) of the entries diagnosed so far.
        Returns:
                None.
        """

        checkpoint = {
            'store': zarr_path,
            'entries': { name: { 'size': size, 'count': count, 'time': var_time }
                         for name, ( _, size, count, var_time ) in results.items() },
            'zeroSizeFiles': list( self.zeroSizeFilesDict[ zarr_path.split('.')[0] ] ),
        }
        tmpFile = f"{checkpointFile}.tmp"
        with open( tmpFile, 'w' ) as f:
            json.dump( checkpoint, f )
        os.replace( tmpFile, checkpointFile )
        logger.info("Diagnosis checkpoint written file=%s entries=%d", checkpointFile, len(results))


    def diagnose_zarr( self, zarr_path, checkpointFile=None ):
        """Diagnose a single zarr store.
        
        For diagnosing a single zarr store. When ZARRCURATOR_MULTITHREAD=1,
        the variables of the store are diagnosed in parallel. Arrays in nested
        groups are recorded by their path from the store root, e.g. 'z2/ocean/sst',
        and each group's metadata files likewise, e.g. 'z2/.zgroup'.

        With a checkpoint file, the entries diagnosed so far are written to it every
        'checkpointInterval' seconds and when the diagnosis stops on an error, and the
        entries it lists are not diagnosed again, so the diagnosis of a very large store
        can be continued in a later session. The result does not depend on the number of
        sessions; the caller removes the checkpoint file when the diagnosis is complete.
        
        Args:
                path: Path to zarr store.
                checkpointFile: Path of the checkpoint file, or None for no checkpoints.
        Returns:
                int:Time in secs for diagnosing.
        """
        
        start = time.time()
        zarr_vars =  None
        zarr_size = 0
        zarr_count = 0
        numThreads = min( 10, maxThreads() )

        threadFlag = os.getenv('ZARRCURATOR_MULTITHREAD')
        multiThread = threadFlag == '1'
        if multiThread:
            logger.info("diagnose_zarr store=%s mode=multi-thread flag=%s", zarr_path, threadFlag)
        else:
            logger.info("diagnose_zarr store=%s mode=single-thread flag=%s", zarr_path, threadFlag)
        
        if self.fileSystemObj is None:
            if os.path.isdir(zarr_path):
                zarr_vars = self.get_list_of_vars(zarr_path)
        else:
            # MKM 6 Mar 2026
            zarr_vars = self.fileSystemObj.listdir(zarr_path, detail=True) # existing code
        
        self.exp_size_dict[zarr_path]={}
        if zarr_vars != None :
            zarr_entries = self.expand_groups( zarr_vars )
            names = [ name for _, name in zarr_entries ]

            # Entries diagnosed in an earlier session
            results, zeroSizeFiles = self.loadDiagCheckpoint( checkpointFile, zarr_path )
            results = { name: result for name, result in results.items() if name in set( names ) }
            storeKey = zarr_path.split('.')[0]
            self.zeroSizeFilesDict[ storeKey ].extend( f for f in zeroSizeFiles if f not in self.zeroSizeFilesDict[ storeKey ] )
            todo = [ ( entry, name ) for entry, name in zarr_entries if name not in results ]
            if results:
                print( f"resuming the diagnosis from {checkpointFile}: {len(results)} of {len(names)} entries already diagnosed", flush=True )
                logger.info("diagnose_zarr resuming store=%s done=%d todo=%d", zarr_path, len(results), len(todo))

            lastSave = time.time()
            def record( result ):
                nonlocal lastSave
                results[ result[0] ] = result
                if checkpointFile is not None and time.time() - lastSave >= self.checkpointInterval:
                    self.saveDiagCheckpoint( checkpointFile, zarr_path, results )
                    lastSave = time.time()

            futures = []
            try:
                if multiThread and len(todo) > 1:
                    # With multi-threading for diagnosing the variables of the store; the results are
                    # recorded in the calling thread as they complete
                    var_executor = concurrent.futures.ThreadPoolExecutor( max_workers=min(numThreads, len(todo)) )
                    try:
                        futures = [ var_executor.submit( self.diagnose_zarr_var, entry, zarr_path, name ) for entry, name in todo ]
                        for future in concurrent.futures.as_completed( futures ):
                            record( future.result() )
                    finally:
                        # Pending entries are cancelled, the running ones are finished
                        var_executor.shutdown( wait=True, cancel_futures=True )
                else:
                    # Without multi-threading
                    for entry, name in todo:
                        record( self.diagnose_zarr_var( entry, zarr_path, name ) )
            except BaseException:
                # Keep the entries diagnosed so far, including those finished by other threads,
                # for the next session
                if checkpointFile is not None:
                    for future in futures:
                        if future.done() and not future.cancelled() and future.exception() is None:
                            result = future.result()
                            results[ result[0] ] = result
                    self.saveDiagCheckpoint( checkpointFile, zarr_path, results )
                raise

            # Aggregate the results in the order of the entries, so that the result does not depend
            # on the order the entries completed in or on the number of sessions
            for name in names:
                var_name, var_size, var_chunk_count, var_time = results[name]
                if var_size == 0 :
                    logger.warning("Zero-sized variable encountered: %s", var_name)
                    if var_name not in self.zeroSizeFilesDict[ storeKey ]:
                        self.zeroSizeFilesDict[ storeKey ].append( var_name )
                    self.zeroSizeFilesFlag = True

                logger.debug("diagnose_zarr variable=%s size=%s count=%s", var_name, var_size, var_chunk_count)
                self.exp_size_dict[zarr_path].update( { var_name: { 'size':var_size, 'count':var_chunk_count, 'time':var_time } } )
                zarr_size += var_size
                zarr_count += var_chunk_count
            if self.zeroSizeFilesDict[ storeKey ]:
                self.zeroSizeFilesFlag = True
                
        else:
            logger.warning("Zarr store has no variables: %s", zarr_path)
        
        self.exp_size_dict[zarr_path].update( {'size':zarr_size} )
        self.exp_size_dict[zarr_path].update( {'count':zarr_count} )
        
        stop=time.time()
        
        logger.info("diagnose_zarr completed store=%s elapsed_secs=%.3f", zarr_path, (stop-start))
        return (stop-start)


    def diagnose_experiment(self):
        """Diagnose the experiment.

        For diagnosing all the zarr stores in parallel using multithreads.

        Args:
                None.
        Returns:
                None.
        """

        numThreads = min( 10, maxThreads() )
        start = time.time()

        threadFlag = os.getenv('ZARRCURATOR_MULTITHREAD')


        

        # Identify the missing chunks for each of the zarr stores
        # Initialize the missing chunks list per store
        for store in self.list_of_zarrs:
            self.zeroSizeFilesDict[ store.split('.')[0] ] = []
            self.missingFilesDict[ store.split('.')[0] ] = []

            # Without multi-threading
            if threadFlag != '1' or threadFlag is None:
                logger.info("Diagnosing store=%s threadFlag=%s", store, threadFlag)
                self.diagnose_zarr( store )

        #With multi-threading for diagnosing each zarr store and finding the missing chunks in each store
        if threadFlag == '1':
            #with alive_bar( len(self.list_of_zarrs)) as bar:
            with concurrent.futures.ThreadPoolExecutor( max_workers = numThreads ) as zarr_executor:
                for _ in zarr_executor.map(self.diagnose_zarr, self.list_of_zarrs):
                    pass
                #bar()
        
        stop=time.time()
        logger.info("Experiment diagnosis completed elapsed_secs=%.3f", (stop-start))
        logger.debug("Experiment diagnosis output=%s", self.exp_size_dict)
        if self.zeroSizeFilesFlag:
            logger.warning("Zero-sized files found: %s", self.zeroSizeFilesDict)
        if self.missingFilesFlag:
            logger.warning("Missing files found: %s", self.missingFilesDict)

        return self.zeroSizeFilesFlag and self.missingFilesFlag


    def update(self):
        """To update the diagnoser object with the data obtained from the diagnosis of the input zarr stores.

        The diagnoser object will be updated either by scanning each of the zarr stores in the input experiment path,
        if starting afresh or use the JSON file created from a previous diagnosis of the experiment.

        Args:
                None.
        Returns:
                None.
        """

        zarrPath = configObj.getZarrStorePath() 
        storeName = zarrPath.split(os.path.sep)[-1]
        jsonFile = os.path.join(configObj.getWorkingDir(), f"{storeName.split('.')[0]}.diag")
        
        
        if os.path.isfile( jsonFile ):
            self.jsonFile = jsonFile
            print( f"Diagnosis file {jsonFile} found, loading the diagnosis!!!", flush=True )
            exp_size_dict_JSON_file = os.path.join( self.outputDir, self.jsonFile )
            with open( exp_size_dict_JSON_file, 'r' ) as expJSONFile:
                # The file is nested by group (older versions wrote it flat)
                self.exp_size_dict = flattenDiagReport( json.load( expJSONFile ) )
            expJSONFile.close()
            return 
        else:
            print( f"Diagnosis file {jsonFile} not found, running diagnoser!!!", flush=True )
            # Return a non zero value to trigger the diagnoser from calling function            
            diagJSONnotfound = 1
            return diagJSONnotfound


    def createStatistics(self):
        """Create statistics of the output from the entire experiment.

        Generate some statistics like min, max file sizes, counts etc.

        Args:
                None.
        Returns:
                None.
        """
        

        if not self.sorted_tuplelist_obj:
            if not self.exp_path:
                logger.warning('Diagnoser path not set!')
            else:
                logger.info('Diagnoser main_func() not executed!')
            return
        else:
            minVar = self.sorted_tuplelist_obj[0]
            maxVar = self.sorted_tuplelist_obj[-1]
            logger.info('Min. Var: %s Min. Var Size: %s', minVar[0], minVar[1])
            logger.info('Max. Var: %s Max. Var Size: %s', maxVar[0], maxVar[1])
        return
