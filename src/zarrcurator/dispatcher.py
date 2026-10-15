"""
This module contains the declaration and definition of the class Dispatcher. 
"""

#Standard modules
import os
import io
import sys
import time
import logging
import tarfile
import contextlib
import concurrent.futures


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

#Local modules
try:
    from .subgroup import SubGroup, subGroup_to_dict
except:
    print( sys.exc_info() )
    print( f"Module 'subgroup' import error in {__file__}" )

try:
    from .config import configObj
except:
    print( sys.exc_info() )
    print( f"Module 'config' import error in {__file__}" )

try:
    from .chunkkeys import parseChunkKey
except:
    print( sys.exc_info() )
    print( f"Module 'chunkkeys' import error in {__file__}" )

try:
    from .storetree import groupAncestors
except:
    print( sys.exc_info() )
    print( f"Module 'storetree' import error in {__file__}" )


TAR_BLOCK_SIZE = 512
"""int: Size of a tar block; an archive ends with two zero blocks."""


def _isCompleteTar( tarFileName ):
    """Check whether a tar file was written completely.

    A tar file is complete if all its member headers can be read, the data of each member lies
    within the file, and the two zero blocks marking the end of the archive follow the last member.
    A tarball cut off by an interrupted session fails one of these checks.

    Args:
            str: Path of the tar file.
    Returns:
            bool: True if the tar file is complete.
    """
    try:
        fileSize = os.path.getsize( tarFileName )
        with tarfile.open( tarFileName, "r:" ) as tar:
            end = 0
            for member in tar:
                dataEnd = member.offset_data + ( member.size if member.isreg() else 0 )
                if dataEnd > fileSize:
                    return False
                end = max( end, dataEnd )
        end = -( -end // TAR_BLOCK_SIZE ) * TAR_BLOCK_SIZE
        if fileSize < end + 2 * TAR_BLOCK_SIZE:
            return False
        with open( tarFileName, "rb" ) as f:
            f.seek( end )
            return not any( f.read( 2 * TAR_BLOCK_SIZE ) )
    except ( OSError, EOFError, tarfile.TarError ):
        return False


@contextlib.contextmanager
def _openTarForWriting( tarFileName ):
    """Open a tar file for writing under a temporary name, renamed to the given name when complete.

    The tarball is written as '<name>.part' and renamed to '<name>' only after it was closed without
    error, so a tarball with the given name is always complete, even if a session is interrupted;
    an incomplete '.part' file is removed on error and overwritten by the next session otherwise.

    Args:
            str: Path of the tar file.
    Yields:
            tarfile.TarFile: The tar file opened for writing.
    """
    partFileName = f"{tarFileName}.part"
    tar = tarfile.open( partFileName, "w" )
    try:
        yield tar
        tar.close()
    except BaseException:
        tar.close()
        if os.path.exists( partFileName ):
            os.remove( partFileName )
        raise
    os.replace( partFileName, tarFileName )


def _resolveStoreMember( zarr_store_path, name ):
    """Return the absolute path of a store member, which may be given relative to the store."""
    return name if os.path.isabs( name ) else os.path.join( zarr_store_path, name )


def _isZarrMetadataFile( name ):
    """Return True for zarr v2 ('.z*') and v3 ('zarr.json') metadata file names."""
    return name.startswith( '.z' ) or name == "zarr.json"


def _listGroupMetadataFiles( zarr_store_path, members ):
    """List the metadata files of the root group and of every group enclosing the members.

    A tarball needs the metadata of each group from the store root down to its members,
    e.g. 'z2/.zgroup' (v2) or 'z2/zarr.json' (v3) for 'z2/ocean/sst', so that stores with
    nested groups (e.g. written from an xarray DataTree) can be reopened from it.

    Args:
            str: Path of the zarr store.
            list[str]: Store members, relative to the store or absolute.
    Returns:
            list[str]: Absolute paths of the metadata files, root group first.
    """
    files = []
    for member in members:
        rel_path = os.path.relpath( _resolveStoreMember( zarr_store_path, member ), zarr_store_path )
        for group in groupAncestors( rel_path ):
            group_dir = os.path.join( zarr_store_path, group ) if group else zarr_store_path
            if not os.path.isdir( group_dir ):
                continue
            files.extend( os.path.join( group_dir, content.name ) for content in os.scandir( group_dir )
                          if content.is_file() and _isZarrMetadataFile( content.name ) )
    return list( dict.fromkeys( files ) )


def _listChunksByFirstIndex( var_path ):
    """Group the chunk files of a variable by their index along the first axis.

    Args:
            str: Path of the variable directory.
    Returns:
            dict: First-axis chunk index -> sorted list of chunk keys relative to the variable.
    """
    chunks = {}
    for root_dir, _, files in os.walk( var_path ):
        for file_name in files:
            key = os.path.relpath( os.path.join( root_dir, file_name ), var_path )
            if _isZarrMetadataFile( file_name ):
                continue
            coord = parseChunkKey( key )
            if coord:
                chunks.setdefault( coord[0], [] ).append( ( coord, key ) )
    return { index: [ key for _, key in sorted( members ) ] for index, members in chunks.items() }


# Dispatcher
class Dispatcher:
    """ Class to Dispatch the diagnoser output to create tar balls.
    """
    
    def __init__( self, tarBaseName, distributorObj ):
        
        self.tarBaseName = tarBaseName
        """str: A prefix string for the tar balls that will be created.
        The tarballs created by the dispatcher will be named with this prefix. 
        """

        self.distributorObj = distributorObj
        """object[class Distributor]: Distributor Object.
        The zarrcurator creates an object of class Distributor to handle the task of distributing the input zarr stores.
        """

        self.subGroupCount = 0
        """int: To keep a count of the sub groups in a given zarr store.
        The subgroups in a given zarr store are counted to generate the suffix for the names of the tarballs created. 
        """
        
        self.frequencySubGroupDict = self.distributorObj.frequencySubGroupDict
        """dict: Dictionary to store the subgroups.
        The subgroups of all the zarr stores are stored frequency wise ('P1D','PT15M',PT3H'). 
        """
        
        self.subGroups = []
        """list: List of the subgroups.
        The list of subgroups for a given zarr store. 
        """
        
        self.subGroupTarNames = []
        """list: List of the tar names.
        The list of name  corresponding to the subgroups for a given zarr store. 
        """

        self.subGroupTarTapeDict = {}
        """dict: Dict of the tar names and tape IDS.
        The dict of tape ID corresponding to the tar of subgroups for a given zarr store. 
        """

        self.isTest = False
        """bool: Flag to indicate testing mode.
        This flag is used to skip the tar creation and just emulate it during development, for testing purposes. 
        """

        self.skipExistingTars = True
        """bool: Flag to skip the tar balls that already exist.
        A tar ball that already exists completely in the working directory is not created again, so the
        tar balls of a store can be created in several sessions. Tar balls are written under a temporary
        name and renamed when complete, so an interrupted session leaves no incomplete tar ball behind.
        """
    
    
    def tarExists( self, tarFileName ):
        """Check whether a tar ball can be skipped, as it was created completely in an earlier session.

        Args:
                str: Path of the tar ball.
        Returns:
                bool: True if skipping is enabled and the tar ball exists completely.
        """
        if not self.skipExistingTars or self.isTest or not os.path.exists( tarFileName ):
            return False
        if _isCompleteTar( tarFileName ):
            logger.info("Skipping existing tar file: %s", tarFileName)
            return True
        logger.warning("Existing tar file is incomplete and is created again: %s", tarFileName)
        return False


    def createTarForFrequencySubGroupDict( self ):
        """Create the tar balls for all the zarr stores.

        For creating tar balls for all the zarr stores in the experiment and listed in the 'frequencySubgroupDict' dictionary 
        created by the diagnoser.

        Args:
                None.
        Returns:
                None.
        """

        
        for freq in list( self.frequencySubGroupDict.keys() ):
            self.createTarForFrequencySubGroups( freq )
    
    
    def createTarForFrequencySubGroups( self, freq ):
        """Create the tar balls for all the zarr stores in a given frequency.

        For creating tar balls for all the zarr stores in the experiment for a given 
        frequency listed in the 'frequencySubgroupDict' dictionary created by the diagnoser.

        Args:
                str: Frequency for which the tar balls are to be created.
        Returns:
                None.
        """

        
        freqDict = self.frequencySubGroupDict[freq]
        self.subGroups.clear()
        self.subGroupTarNames.clear()
        
        for subGroupID in list(freqDict.keys()):
            logger.debug("Selected subgroup id=%s for frequency=%s", subGroupID, freq)
            self.subGroups.append(freqDict[subGroupID])
            self.subGroupTarNames.append(f"{subGroupID}")
    
    
    def createTarForSubGroup( self, subGroup, subGroupTarName ):
        """Create the tar balls for a sub group.

        For creating tar balls for a sub group based on the type and name them with a specific name.

        Args:
                object[Class Subgroup]: Sub group object.
                str:Name of the tar ball that will be created for the subGroup.
        Returns:
                None.
        """


        logger.info("Creating tar for subgroup name=%s type=%s", subGroupTarName, subGroup.groupType)
        
        if subGroup.groupType == "zarr":
            self.createTarForZarr(subGroup, subGroupTarName)
        elif subGroup.groupType == "var":
            self.createTarForVar(subGroup, subGroupTarName)
        elif subGroup.groupType == "chunk":
            self.createTarForChunk(subGroup, subGroupTarName)
        return

    
    def createTarForZarr( self, subGroup, subGroupTarName ):
        """Create the tar balls for a sub group of type 'zarr'.

        For creating tar balls for 'zarr' type sub group based on the type and and name them with a specific name.

        Args:
                object[Class Subgroup]: Sub group object.
                str:Name of the tar ball that will be created for the subGroup.
        Returns:
                None.
        """

        logger.debug("createTarForZarr members=%s type=%s name=%s", subGroup.groupMembers, subGroup.groupType, subGroupTarName)
        outputPath=configObj.getWorkingDir()

        if self.tarBaseName is not None:
            tarFileName = f"{self.tarBaseName}_{subGroupTarName}.tar"
        else:
            tarFileName = f"{subGroupTarName}.tar"

        tarFileName = os.path.join( outputPath, tarFileName )

        if self.tarExists( tarFileName ):
            subGroup.setGroupTarMembers([tarFileName])
            return

        # Get the list of files in the variable.
        # Divide the number of chunks into bins with equal number of chunks.
        # Create Tar balls for each of those index ranges.
        grp_files = []
        # NOTE: For zarr stores on object stores, the group members are listed with 
        # fsspec listing of files.        
        fs = configObj.getFileSystemObj()
        if configObj.getFileSystemObj() is not None:
            zarr_files = fs.find(subGroup.groupMembers[0][0])
            logger.debug("Found %d object-store files for subgroup=%s", len(zarr_files), subGroupTarName)
            grp_files.extend( zarr_files )
        else:
            grp_files.append( subGroup.groupMembers[0][0])
            
        logger.info("Writing tar file: %s", tarFileName)
        if not self.isTest:            
            try:
                #with alive_bar(len(grp_files)) as bar:
                #bar.title(f"{tarFileName}")
                with _openTarForWriting(tarFileName) as tar:
                    for name in grp_files:
                        logger.debug("Adding file to tar file=%s member=%s", tarFileName, name)
                        if not configObj.getDebugMode():
                            #Object store
                            if configObj.getFileSystemObj() is not None:
                                rel_path = name.replace(subGroup.groupMembers[0][0].rstrip("/") + "/", "")
                                # Stream object-store members directly into tar to avoid full in-memory reads.
                                try:
                                    info = tarfile.TarInfo(name=rel_path)
                                    info.size = fs.size(name)
                                    with fs.open(name, "rb") as fobj:
                                        tar.addfile(info, fobj)
                                except Exception:
                                    # Fallback for filesystems without reliable size metadata.
                                    with fs.open(name, "rb") as fobj:
                                        data = fobj.read()
                                    info = tarfile.TarInfo(name=rel_path)
                                    info.size = len(data)
                                    tar.addfile(info, io.BytesIO(data))
                            else: # Local file system
                                tar.add( name, arcname=name.replace(subGroup.groupMembers[0][0],'') )
                        #bar.text(f'{name.split(os.path.sep)[-1]}')
            except Exception as e:
                logger.exception("Exception occurred while creating zarr tar file=%s", tarFileName)

        subGroup.setGroupTarMembers([tarFileName])
        return
    
    
    def createTarForVar( self, subGroup, subGroupTarName ):
        """Create the tar balls for a sub group of type 'var'.

        For creating tar balls for 'var' type sub group based on the type and and name them with a specific name.

        Args:
                object[Class Subgroup]: Sub group object.
                str:Name of the tar ball that will be created for the subGroup.
        Returns:
                None.
        """


        logger.debug("createTarForVar members=%s type=%s name=%s", subGroup.groupMembers, subGroup.groupType, subGroupTarName)
        
        zarr_store_path=configObj.getZarrStorePath()
        logger.debug("zarr_store_path=%s", zarr_store_path)
        
        size = subGroup.groupSize / (1024*1024*1024)
        logger.info("createTarForVar subgroup=%s size_gb=%.3f", subGroupTarName, size)
        
        outputPath=configObj.getWorkingDir()

        if self.tarBaseName is not None:
            tarFileName = f"{self.tarBaseName}_{subGroupTarName}.tar"
        else:
            tarFileName = f"{subGroupTarName}.tar"

        tarFileName = os.path.join( outputPath, tarFileName )

        if self.tarExists( tarFileName ):
            subGroup.setGroupTarMembers([tarFileName])
            return

        # Create the group of files for this tar, consisting of the attrs of the root and enclosing groups,
        # the var's and the coordinate variables
        grp_files = []
        grp_files.extend( _listGroupMetadataFiles( zarr_store_path, [ varGroup[0] for varGroup in subGroup.groupMembers ] ) )
        grp_files.extend([ _resolveStoreMember( zarr_store_path, varGroup[0] ) for varGroup in subGroup.groupMembers])
        grp_files = list( dict.fromkeys( grp_files ) )

        logger.info("Writing tar file: %s", tarFileName)
        logger.debug("Tar members count=%d", len(grp_files))

        subList = subGroupTarName.split('_')
        if len(subList) == 3:
            zarrStoreName = subGroupTarName + ".zarr"
        else:
            zarrStoreName = '_'.join(subList[0:3])+ ".zarr"
            
        if not self.isTest:
            try:
                #with alive_bar(len(grp_files)) as bar:
                #bar.title(f"{tarFileName}")
                with _openTarForWriting(tarFileName) as tar:
                    for name in grp_files:
                        logger.debug("Adding file to tar file=%s member=%s", tarFileName, name)
                        tname = os.path.join( zarr_store_path, zarrStoreName )
                        tname = tname + os.path.sep
                        if not configObj.getDebugMode():
                            tar.add( name, arcname=os.path.relpath( name, zarr_store_path ) )
                        #bar.text(f'{name.split(os.path.sep)[-1]}')
            except Exception as e:
                logger.exception("Exception occurred while creating var tar file=%s", tarFileName)
        subGroup.setGroupTarMembers([tarFileName])
        return 
    
    
    def createTarForChunk( self, subGroup, subGroupTarName ):
        """Create the tar balls for a sub group of type 'chunk'.

        For creating tar balls for 'chunk' type sub group based on the type and and name them with a specific name.

        Args:
                object[Class Subgroup]: Sub group object.
                str:Name of the tar ball that will be created for the subGroup.
        Returns:
                None.
        """

        logger.debug("createTarForChunk members=%s type=%s name=%s", subGroup.groupMembers, subGroup.groupType, subGroupTarName)
        zarr_store_path=configObj.getZarrStorePath()
        logger.debug("zarr_store_path=%s", zarr_store_path)
        size = subGroup.groupSize / (1024*1024*1024)
        logger.info("createTarForChunk subgroup=%s size_gb=%.3f", subGroupTarName, size)
        outputPath=configObj.getWorkingDir()
        
        targetSize = self.distributorObj.targetSize / (1024*1024*1024)
        
        if size > targetSize:
            logger.debug("Chunk subgroup requires splitting subgroup=%s", subGroupTarName)
            num_bins, remainder = divmod( int(size) , int(targetSize) )
            if remainder > 0 :
                num_bins += 1
        else:
            num_bins = 1
        
        logger.info("Chunk subgroup binning subgroup=%s bins=%d target_gb=%.3f", subGroupTarName, num_bins, targetSize)
        
        # Get the chunks of the variable, grouped by their index along the first axis.
        # Works for '.' and '/' separated chunk keys of zarr v2 and v3 stores.
        var_path = os.path.join( zarr_store_path, subGroup.groupMembers[0][0] )
        chunks_by_first_index = _listChunksByFirstIndex( var_path )
        list_of_chunks = sorted( chunks_by_first_index )
        list_of_attrs = [ content for content in os.scandir( var_path ) if content.is_file() and _isZarrMetadataFile( content.name ) ]
        
        logger.info("Chunk subgroup=%s chunk_count=%d", subGroupTarName, len(list_of_chunks))
        
        # Get the dimensions
        # '0' is the current variable, hence from  gathering names from index '1' to len(subGroup.groupMembers)
        list_of_dimensions = [ subGroup.groupMembers[index][0]  for index in range(1,len(subGroup.groupMembers))  ]

        # Attrs of the root group and of the groups enclosing the variable and its dimensions
        list_of_group_attrs = _listGroupMetadataFiles( zarr_store_path, [ subGroup.groupMembers[0][0] ] + list_of_dimensions )
        
        # Divide the number of chunks into bins with equal number of chunks.
        numChunks = len(list_of_chunks)
        if numChunks == 0:
            logger.error("No chunks found in %s", var_path)
            return
        num_bins = min( num_bins, numChunks )
        binSize = int ( numChunks / num_bins )

        # Check to find any missing chunks , discontinuities in the data.
        missingChunks = False
        maxChunkID = list_of_chunks[ numChunks - 1 ]
        if  numChunks - 1  !=  maxChunkID:
            missingChunks = True
            if not configObj.getPackDiscontinuousData() :
                logger.error("Missing chunks in %s chunk_count=%d range=%s-%s", subGroup.groupMembers[0][0], numChunks, list_of_chunks[0], maxChunkID)
                return
        tarFileNamesList = []
        try:
            # Create Tar balls for each of those index ranges.
            for binID in list(range(1,num_bins+1)):
                
                if binID > 1:
                    startChunk = binSize * (binID-1)  + 1
                else:
                    startChunk = 0
                
                if binID == num_bins:
                    endChunk = numChunks-1
                else:
                    endChunk = binSize * binID 
                    
                logger.debug("Chunk bin subgroup=%s bin=%d start=%d end=%d", subGroupTarName, binID, startChunk, endChunk)

                if self.tarBaseName is not None:
                    tarFileName = f"{self.tarBaseName}_{subGroupTarName}_{binID}.tar"
                else:
                    tarFileName = f"{subGroupTarName}_{binID}.tar"

                tarFileName = os.path.join( outputPath, tarFileName )

                if self.tarExists( tarFileName ):
                    tarFileNamesList.append(tarFileName)
                    continue
                
                grp_files = []
                grp_files.extend( list_of_group_attrs )
                grp_files.extend([ os.path.join(subGroup.groupMembers[0][0],k.name) for k in list_of_attrs ])
                grp_files.extend(list_of_dimensions)
                               
                if missingChunks:
                    logger.warning("Packing discontinuous chunks for %s", subGroup.groupMembers[0][0])
                list_of_chunk_files = []
                for k in range(startChunk, endChunk+1):
                    list_of_chunk_files.extend([ os.path.join(subGroup.groupMembers[0][0],key) for key in chunks_by_first_index[ list_of_chunks[k] ] ])
                grp_files.extend(list_of_chunk_files)
                
                logger.info("Writing tar file: %s", tarFileName)
                
                subList = subGroupTarName.split('_')
                if len(subList) == 3:
                    zarrStoreName = subGroupTarName + ".zarr"
                else:
                    zarrStoreName = '_'.join(subList[0:3]) + ".zarr"
                    
                if not self.isTest:
                    #with alive_bar(len(grp_files)) as bar:
                    #bar.title(f"{tarFileName}")
                    with _openTarForWriting(tarFileName) as tar:
                        debugChunkCount = 0    
                       
                        chunkFileCount = 0
                        chunkFileSet = set( list_of_chunk_files )
                        for name in grp_files:
                            # Print some log message for every 100th chunk of the variable
                            if name in chunkFileSet:
                                if chunkFileCount % 100 == 0:
                                    logger.debug("Adding periodic chunk file=%s tar=%s", name, tarFileName)
                                chunkFileCount += 1
                            tname = os.path.join( zarr_store_path, zarrStoreName )
                            tname = tname + os.path.sep
                            
                            srcName = _resolveStoreMember( zarr_store_path, name )
                            if not configObj.getDebugMode():
                                tar.add( srcName, arcname=os.path.relpath( srcName, zarr_store_path ) )
                            else:
                                if debugChunkCount > 10: # Debug chunk count -- user control
                                    break
                                else:
                                    tar.add( srcName, arcname=os.path.relpath( srcName, zarr_store_path ) )
                                debugChunkCount += 1
                                
                            #bar.text(f'{name.split(os.path.sep)[-1]}')
                    
                    tarFileNamesList.append(tarFileName)
        except Exception as e:
            logger.exception("Exception occurred in createTarForChunk var=%s tar=%s", subGroup.groupMembers[0][0], tarFileName)
        subGroup.setGroupTarMembers(tarFileNamesList)
        return    
    
    
    def executor(self, subGroupID=-1):
        """Create the tar balls.

        For creating tar balls for all the subgroups with their respective names.

        Args:
                int:Index of the subgroup for which the tar balls are to be created.
        Returns:
                None.
        """
        
        start=time.time()
        logger.info("Starting tar creation executor")

        if subGroupID > len(self.subGroups):
            logger.error("Input subGroupID=%d exceeds available subgroups=%d", subGroupID, len(self.subGroups))
            return

        if subGroupID > 0:
            for grp,grpName in zip( [ self.subGroups[ subGroupID-1 ] ], [ self.subGroupTarNames[ subGroupID-1 ] ]):
                logger.debug("Executor subgroup=%s name=%s", grp, grpName)
        else:
            for grp,grpName in zip(self.subGroups,self.subGroupTarNames):
                logger.debug("Executor subgroup=%s name=%s", grp, grpName)
            
        
        with concurrent.futures.ThreadPoolExecutor( max_workers = 10 ) as executor:
            try:
                if subGroupID > 0:
                    results = executor.map( self.createTarForSubGroup, [self.subGroups[ subGroupID-1 ]], [self.subGroupTarNames[ subGroupID-1 ]] )
                else:
                    results = executor.map( self.createTarForSubGroup, self.subGroups, self.subGroupTarNames )
            except Exception as e:
                logger.exception("Exception encountered in executor")

        for result in results:
            logger.debug("Thread output=%s", result)
        stop=time.time()
        logger.info("Tar creation completed elapsed_secs=%.3f", (stop-start))

    
        
        outputTarFileList = []
        for subGroup in self.subGroups:
            outputTarFileList.extend(subGroup.getTarMembers())
        
        logger.info("Created tar files count=%d", len(outputTarFileList))
