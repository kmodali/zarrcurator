"""
This module contains the declaration and definition of the class Distributor.
"""

#Standard modules
import os
import sys
import copy
import posixpath
import re
import json
import logging
import xarray as xr
from heapq import heapreplace,heapify,heappop

import s3fs


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

#Non-Standard modules
try:
    import zarr
except:
    logger.exception("Module 'zarr' import error in %s", __file__)

#Local modules
try:
    from .subgroup import SubGroup, subGroup_to_dict, subGroup_from_dict
except:
    logger.exception("Module 'subgroup' import error in %s", __file__)

try:
    from .storetree import groupAncestors, flattenDistReport, DIAG_METADATA_NAMES
except:
    logger.exception("Module 'storetree' import error in %s", __file__)

try:
    from .config import configObj
except:
    logger.exception("Module 'config' import error in %s", __file__)


def _naturalSortKey( text ):
    """Sort key ordering the numbers in a text by value, e.g. 'zoom_2' before 'zoom_10'."""
    return [ int( part ) if part.isdigit() else part for part in re.split( r'(\d+)', text ) ]


def _storeRelativePath( zarrStorePath, member ):
    """Return the path of a store member, given relative to the store or absolute, relative to the store root."""
    path = os.path.join( zarrStorePath, str( member ).rstrip( os.path.sep ) )
    return os.path.relpath( path, zarrStorePath ).replace( os.path.sep, '/' )


def _getArrayDimensionNames( array ):
    """Return the dimension names of a zarr array (v2 '_ARRAY_DIMENSIONS' or v3 'dimension_names')."""
    names = getattr( array.metadata, 'dimension_names', None )
    if not names:
        names = array.attrs.get( '_ARRAY_DIMENSIONS', [] )
    return [ name for name in names if name ]


# Distributor
class Distributor:
    """ Distribute the list of tuples of type (variable ,size) into different sub groups,
        either equal size or based on target size specified by user etc.
    """
    
    def __init__(self, diagnoserObj, targetSize):

        self.diagnoserObj = diagnoserObj
        """object[class Diagnoser]: Diagnoser Object.
        The zarrcurator creates an object of class Diagnoser to handle the task of diagnosing the input zarr stores.
        """


        self.frequencyList = []
        """list: List of frequencies in the zarr stores.
        The list of the frequencies for which the data is produced by the experiment.
        """

        # NOTE: As of now treating zarr stores on object stores as mixed frequency 
        # and those on disk, have name format ngcxxxx_P*_*.zarr; stores on disk with
        # other names, e.g. a group of a store like 'd3hp003.zarr/P1D_mean_atm', are
        # treated as mixed frequency too.
        # TODO: To be handled in a better way, by for example, checking the metadata of the zarr store
        #  for frequency information, instead of relying on the name of the zarr store.
        if configObj.getFileSystemObj() is None:
            for zarr_store_name in diagnoserObj.list_of_zarrs:
                nameParts = zarr_store_name.split('.')[0].split(os.path.sep)[-1].split('_')
                freq = nameParts[1] if len(nameParts) > 1 else 'ALL'
                if freq not in self.frequencyList:
                    self.frequencyList.append(freq)
        else:
            self.frequencyList.append('ALL')
        
        
        self.frequencyGroupDict = {}
        """dict: Dictionary to store the groups per frequency available in the zarr stores.
        The list of the frequencies and the groups, for which the data is produced by the experiment.
        """
        
        self.frequencySubGroupDict = {}
        """dict: Dictionary to store the subgroups per frequency available in the zarr stores.
        The list of the frequencies and the subgroups, for which the data is produced by the experiment.
        """

        
        self.targetSize = targetSize
        """int: Target size for each tar ball.
        The size of the tar ball keeping in view the constraints of the HSM system, as of now 200 GB.
        """
        
    def setFrequencySubGroupDict(self, frequencySubGroupDict):
        """To set the frequency subGroup dictionary directly from JSON file.
                
        To set frequencySubGroupDict directly, if  for example, loaded from JSON file from an earlier run of 'zarrcurator'.
        
        Args:
                frequencySubGroupDict[dict]: Dictionary of the frequencies and subGroups.
        
        Returns:
                None.
        
        """
        self.frequencySubGroupDict = frequencySubGroupDict


    def getFrequencySubGroupDict(self):
        """To get the frequency subGroup dictionary directly.
                
        To get frequencySubGroupDict directly, if  for example, from utils of 'zarrcurator'.
        
        Args:
                None.
        
        Returns:
                frequencySubGroupDict[dict]: Dictionary of the frequencies and subGroups.
        
        """
        return self.frequencySubGroupDict

    
    
    def updateFrequencyGroupDict(self):
        """To create the dictionary per frequency and it's groups.

        For storing the file sizes and counts for each zarr store per frequency in a dictionary.

        Args:
                None.
        Returns:
                None.
        """
        
        logger.info("updateFrequencyGroupDict frequencies=%s", self.frequencyList)

        for freq in self.frequencyList:
            self.frequencyGroupDict[freq] = {}
            for freq_zarr in self.diagnoserObj.exp_size_dict.keys():
                if configObj.getFileSystemObj() is not None:
                    freq_zarr_var_dict = self.diagnoserObj.exp_size_dict[freq_zarr]
                    logger.debug("Including object-store zarr=%s", freq_zarr)
                    self.frequencyGroupDict[freq].update({freq_zarr: freq_zarr_var_dict})
                else:
                    if freq == 'ALL' or freq in freq_zarr:
                        freq_zarr_var_dict = self.diagnoserObj.exp_size_dict[freq_zarr]
                        self.frequencyGroupDict[freq].update({freq_zarr: freq_zarr_var_dict})
        logger.debug("frequencyGroupDict=%s", self.frequencyGroupDict)
        return
    
    
    def updateFrequencySubGroupDictWithSingleZarrStore(self):
        """To update the sub group dictionary per frequency with single subgroup of type 'zarr'.

        For initializing each of the zarr stores (per freq and healpix) in the sub group dictionary
        with sub group of type 'zarr', if the size of the entire zarr store is less than the target size.

        Args:
                None.
        Returns:
                None.
        """

        
        for freq in self.frequencyGroupDict.keys():
            
            self.frequencySubGroupDict[freq] = {}
            subGroupSize = 0
            subGroupMembers = []

            for freq_zarr in self.frequencyGroupDict[freq].keys():
                
                subGroupMembersSizeTupleList = [] # for subGroup Object creation
                iZarr_Size = self.frequencyGroupDict[freq][freq_zarr]['size']
                subGroupMembersSizeTupleList.append((freq_zarr,iZarr_Size))

                subGroupId = freq_zarr.split(os.path.sep)[-1].rstrip('.zarr')
                
                # Create subGroup object
                subGroupObj = SubGroup([],'zarr',[],[])
                subGroupObj.updateSubGroup(subGroupMembersSizeTupleList)
                self.frequencySubGroupDict[freq].update( { str(subGroupId) : subGroupObj } )
                
        return
    
    
    def updateFrequencySubGroupDictWithTargetSize(self):
        """To update the sub group dictionary per frequency with subgroups of size as per target size.
        
        For updating each of the zarr stores (per freq and healpix) in the sub group dictionary
        with sub group whose size is greater than the target size and splitting the sub groups 
        into more subgroups if larger than the target size.
        
        
        Args:
                None.
        Returns:
                None.
        """
        
        for freq in self.frequencyGroupDict.keys():
            self.frequencySubGroupDict[freq] = {}
            subGroupSize = 0
            subGroupMembers = []
            subGroupMembersSizeTupleList = [] # for subGroup Object creation
            subGroupId = 1
            incompleteSubGroup = 0
            nextSubGroupId = 1
            
            for freq_zarr in self.frequencyGroupDict[freq].keys():
                
                iZarr_Size = self.frequencyGroupDict[freq][freq_zarr]['size']
                
                # Small File 
                if iZarr_Size < self.targetSize: 

                    # Add the file size to the current subGroupSize and 
                    # check if the target size is exceeded
                    subGroupSize += iZarr_Size
                        
                    if subGroupSize > self.targetSize :  # exceeds 200GB
                        # Decrement the groupSize by the current zarr size
                        subGroupSize -=iZarr_Size

                        # Update the subGroup without the new member to the SubGroupDict
                        
                        # Create subGroup object
                        subGroupObj = SubGroup([],'zarr',[],[])
                        subGroupObj.updateSubGroup(subGroupMembersSizeTupleList)
                        self.frequencySubGroupDict[freq].update( { str(subGroupId) : subGroupObj } )
                        
                        #reset the subGroup values
                        subGroupSize = 0
                        subGroupMembers = []
                        subGroupMembersSizeTupleList = []
                        
                        # Set the subGroupId to the next available ID
                        subGroupId = nextSubGroupId + 1
                        
                        # Append to the subGroup , .i., new subGroup
                        subGroupMembers.append(freq_zarr)
                        subGroupMembersSizeTupleList.append((freq_zarr,iZarr_Size))
                        subGroupSize += iZarr_Size
                        
                    else:
                        subGroupMembers.append(freq_zarr)
                        subGroupMembersSizeTupleList.append((freq_zarr,iZarr_Size))
                        incompleteSubGroup = subGroupId
                        
                # Large File 
                # Create a new subgroup and add this large file to that group
                # Mark the current group as incomplete
                # Increment the next available group ID 
                # Update the subGroup to the SubGroupDict
                else:
                    
                    incompleteSubGroup = subGroupId
                    nextSubGroupId = nextSubGroupId + 1
                    #Create subGroup Object and update the dict
                    subGroupObj = SubGroup([],'zarr',[],[])
                    subGroupObj.updateSubGroup( (freq_zarr,iZarr_Size) )
                    self.frequencySubGroupDict[freq].update( { str(nextSubGroupId) : subGroupObj } )

                    
            if incompleteSubGroup > 0: 
                subGroupObj = SubGroup([],'zarr',[],[])
                subGroupObj.updateSubGroup(subGroupMembersSizeTupleList)
                self.frequencySubGroupDict[freq].update( { str(incompleteSubGroup) : subGroupObj } )
        return
    
    
    def groupEntriesByGroup(self, zarr_store):
        """To sort the entries of a zarr store by the group they belong to.

        For stores with nested groups (e.g. written from an xarray DataTree), the entries are named by
        their path from the store root, e.g. 'multiscales/zoom_11/tas', and belong to the group of that
        path, e.g. 'multiscales/zoom_11'. Each group is distributed on its own, so that a subgroup, and
        so a tarball, holds the arrays of a single group, e.g. of a single HEALPix zoom level. Groups
        with metadata files only (e.g. the store root above 'multiscales') are added to the first group
        with arrays; the dispatcher adds the metadata of the enclosing groups to every tarball anyway.
        For a store without nested groups all entries belong to the root group ''.

        Args:
                dict: Entry name -> {'size', 'count'} for the entries of a zarr store.
        Returns:
                dict: Group path -> list of (entry name, size), groups sorted by path.
        """

        groups = {}
        # Keep the order of the entries within a group, as the packing sorts them by size only
        for name in zarr_store:
            groups.setdefault( posixpath.dirname( name ), [] ).append( ( name, zarr_store[name]['size'] ) )
        groups = { group: groups[group] for group in sorted( groups, key = _naturalSortKey ) }

        def onlyMetadata( entries ):
            return all( posixpath.basename( name ) in DIAG_METADATA_NAMES for name, _ in entries )

        withArrays = [ group for group, entries in groups.items() if not onlyMetadata( entries ) ]
        if not withArrays:
            return groups
        merged = { group: list( groups[group] ) for group in withArrays }
        for group, entries in groups.items():
            if group not in merged:
                merged[withArrays[0]].extend( entries )
        return merged


    def split_zarr_into_equalSized_bins(self, zarr_store, num_bins = 10 ):
        """To split a zarr store larger than the target size into subgroups.

        The entries of each group of the store (see groupEntriesByGroup) are split on their own,
        so that a subgroup never mixes the arrays of different groups, e.g. of different HEALPix
        zoom levels of a store written from an xarray DataTree. Within a group, each array larger
        than the target size becomes a subgroup of type 'chunk', the other entries are packed into
        subgroups of type 'var' of about equal size. The metadata files of a group whose arrays are
        all split into chunk subgroups are left out, as the chunk tarballs carry them.

        Args:
                dict: Entry name -> {'size', 'count'} for the entries of a zarr store, plus its
                      'size' and 'count'.
        Returns:
                list[SubGroup]: Per group, its subgroups of type 'var', then those of type 'chunk';
                each with the path of its group as 'groupPath', e.g. 'multiscales/zoom_11'.
        """

        zarr_store.pop('count')
        zarr_store.pop('size')

        subGroups = []
        for group, entries in self.groupEntriesByGroup( zarr_store ).items():
            small_zarr_subGroups = []
            large_zarr_subGroups = []
            small = [ entry for entry in entries if entry[1] <= self.targetSize ]
            large = [ entry for entry in entries if entry[1] > self.targetSize ]
            # The metadata files of a group whose arrays are all split into chunk tarballs are
            # archived with those tarballs, which carry the metadata of their enclosing groups
            if large and all( posixpath.basename( name ) in DIAG_METADATA_NAMES for name, _ in small ):
                small = []
            small_zarr_subGroups.extend( self.packEntries( small ) )
            # Only single arrays exceed the target size; they are split into tarballs of their chunks
            for name, size in sorted( large, key = lambda x : x[1] ):
                grp = SubGroup([],'chunk',[],[])
                grp.updateSubGroup( ( name, size ) )
                large_zarr_subGroups.append( grp )
            logger.debug("split_zarr_into_equalSized_bins group=%s entries=%d", group, len(entries))
            for grp in small_zarr_subGroups + large_zarr_subGroups:
                # The group of the members, used to name the subgroup (see subGroupLabels)
                grp.groupPath = group
                subGroups.append( grp )

        return subGroups


    def packEntries(self, entries):
        """To pack entries smaller than the target size into subgroups of type 'var' of about equal size.

        The number of subgroups is the total size divided by the target size, rounded; the entries are
        added from the smallest to the largest, each to the subgroup with the smallest size.

        Args:
                list[tuple]: (entry name, size) of the entries.
        Returns:
                list[SubGroup]: Non-empty subgroups of type 'var'.
        """

        if not entries:
            return []
        totalSize = sum( size for _, size in entries )
        num_bins = round( totalSize / self.targetSize )
        if num_bins == 0:
            num_bins = 1
        if num_bins > len(entries):
            num_bins = max( 1, int(len(entries) / 2 ) )

        subGroups = [ SubGroup([],'var',[],[]) for _ in range(num_bins) ]
        for entry in sorted( entries, key = lambda x : x[1] ):
            least = subGroups[0]
            least.updateSubGroup( entry )
            heapreplace(subGroups, least)
        return [ grp for grp in subGroups if grp.groupMembers ]


    def redistributeSubGroups(self):
        """To redistribute the subgroups.

        For redistributing each of the zarr stores (per freq and healpix) in the sub group dictionary
        based on each of the sub group and it's size in comparison with the target size,by splitting 
        the sub groups into more subgroups if their size is larger than the target size.
        

        Args:
                obj: None.
        Returns:
                None.
        """
     
        newSubGroupsDict = {}
        obsoleteSubGroupDict = {}
        for freq in self.frequencySubGroupDict.keys():
            newSubGroupsDict[freq]={}
            obsoleteSubGroupDict[freq]=[]
            for groupID in self.frequencySubGroupDict[freq].keys():
                if self.frequencySubGroupDict[freq][groupID].groupSize > self.targetSize:
                    zarr_store_name = self.frequencySubGroupDict[freq][groupID].groupMembers[0][0]
                    zarr_store = copy.deepcopy(self.frequencyGroupDict[freq][zarr_store_name])
                    
                    zarr_store_subGroups = self.split_zarr_into_equalSized_bins(zarr_store)
                    # Remove the original zarr subgroup
                    obsoleteSubGroupDict[freq].append(groupID)
                    # Append the new subgroups created by splitting the original zarr store, named
                    # by the store, the group of their members (e.g. the zoom level 'zoom_11') and a
                    # number counted per group, e.g. 'P1D_mean_atm_zoom_11_3'; the tarballs are named
                    # after the subgroups. Subgroups of the root group, e.g. of a store without nested
                    # groups, are named by the store and the number only, e.g. 'ngc4008_P1D_7_3'.
                    labels = self.subGroupLabels( [ grp.groupPath for grp in zarr_store_subGroups ] )
                    subGroupCount = {}
                    for zarr_subGroup in zarr_store_subGroups:
                        label = labels[zarr_subGroup.groupPath]
                        prefix = f"{groupID}_{label}" if label else str(groupID)
                        subGroupCount[prefix] = subGroupCount.get( prefix, 0 ) + 1
                        subGroupID = f"{prefix}_{subGroupCount[prefix]}"
                        newSubGroupsDict[freq].update({subGroupID :  zarr_subGroup})
                        
        for freq in obsoleteSubGroupDict.keys():
            for groupID in obsoleteSubGroupDict[freq]:
                # Remove the original zarr subgroup
                self.frequencySubGroupDict[freq].pop(groupID)
                for newID, newSubGroup in newSubGroupsDict[freq].items():
                    self.frequencySubGroupDict[freq].update({newID:newSubGroup})


    @staticmethod
    def subGroupLabels( groupPaths ):
        """To get the labels naming the subgroups of the groups of a zarr store.

        A group is labelled by its name, e.g. 'zoom_11' for 'multiscales/zoom_11', or by its
        path with '_' for '/' if several groups have that name, e.g. 'atmos_zoom_0' and
        'ocean_zoom_0'. The root group '' has no label.

        Args:
                list[str]: Group paths, e.g. ['multiscales/zoom_0', 'multiscales/zoom_11'].
        Returns:
                dict: Group path -> label.
        """

        paths = set( groupPaths )
        names = [ posixpath.basename( path ) for path in paths if path ]
        return { path: ( posixpath.basename( path ) if names.count( posixpath.basename( path ) ) == 1
                         else path.replace( '/', '_' ) ) if path else '' for path in paths }


    def updateDimensionsToSubGroups(self):
        """To update the dimensions to the subgroups.

        For each of the sub group dictionary based on it's type, for the 'var' and 'chunk' types, the 
        dimensions of the original zarr store are to be appended, so that the tar ball is self-contained
        and could be utiized by the downstream applications.
        

        Args:
                obj: None.
        Returns:
                None.
        """
        
        for freq in self.frequencySubGroupDict.keys():
            for groupID in self.frequencySubGroupDict[freq].keys():

                if self.frequencySubGroupDict[freq][groupID].groupType != 'zarr':
                    storePath = configObj.getZarrStorePath()
                    print(f"In distributor.updateDimensionsToSubGroups.storePath: {storePath}",flush=True)
                    # Members are given by their path from the store root (e.g. 'z2/ocean/sst') or by
                    # absolute path, so compare by the path from the store root to not add a coordinate
                    # variable that is already a member of the subgroup.
                    memberPaths = { _storeRelativePath( storePath, member[0] ) for member in self.frequencySubGroupDict[freq][groupID].groupMembers }
                    # The coordinates used by the groups of the members, e.g. 'z2/ocean' for 'z2/ocean/sst'.
                    memberGroups = sorted( { posixpath.dirname( path ) for path in memberPaths } )
                    dimensionsTupleList = self.getZarrstoreDimensions(freq, storePath, memberGroups)
                    newDimensions = [ dimTuple for dimTuple in dimensionsTupleList if _storeRelativePath( storePath, dimTuple[0] ) not in memberPaths ]
                    if newDimensions:
                        self.frequencySubGroupDict[freq][groupID].updateSubGroup(newDimensions)
                else:
                    continue


    def getZarrstoreDimensions(self, freq, zarrStorePath, groups=None):
        """To get the coordinate variables of the zarr store.

        For getting the coordinate variables of the original zarr store, which are to be appended to the tar balls.
        These are the dimension coordinates (arrays named after a dimension, e.g. 'time' or the HEALPix 'cell'), the auxiliary
        coordinates listed in the 'coordinates' attribute and the variables named in the 'grid_mapping'
        attribute. Dimension names are read from '_ARRAY_DIMENSIONS' (zarr v2) or 'dimension_names' (zarr v3).

        For stores with nested groups (e.g. written from an xarray DataTree), the coordinates used by the arrays
        of each of the given groups are collected. As a group can use the coordinates of its parent groups,
        each coordinate is looked up in the group itself first and then in its parents up to the store root.
        

        Args:
                str: Frequency of the model data. 
                str: Path to the location of the zarr store.
                list[str]: Group paths relative to the store root, e.g. ['z2/ocean']; defaults to the root group ''.
        Returns:
                list: sorted list of (coordinate variable path, size) tuples.
        """
        dimensionsTupleList = []
        if groups is None:
            groups = ['']
        # Open the zarr store, distinct ways for local store and object store
        fs = configObj.getFileSystemObj()
        if fs is not None:
            store = fs.get_mapper( configObj.getZarrStorePath() )
        else:
            store = zarrStorePath
        zarrGroup = zarr.open_group( store, mode='r' )

        arrayNamesByGroup = {}
        def arrayNames( group ):
            if group not in arrayNamesByGroup:
                node = zarrGroup[group] if group else zarrGroup
                arrayNamesByGroup[group] = set( node.array_keys() )
            return arrayNamesByGroup[group]

        coordinatePaths = set()
        for group in groups:
            try:
                node = zarrGroup[group] if group else zarrGroup
            except KeyError:
                logger.warning("Group not found in zarr store: %s", group)
                continue
            coordinateNames = set()
            for arrayName in arrayNames( group ):
                array = node[arrayName]
                attrs = dict( array.attrs )
                coordinateNames.update( _getArrayDimensionNames( array ) )
                coordinateNames.update( str( attrs.get( 'coordinates', '' ) ).split() )
                # grid_mapping is either 'crs' or the extended form 'crs: lat lon'
                coordinateNames.update( name.rstrip(':') for name in str( attrs.get( 'grid_mapping', '' ) ).split() )

            # The group itself first, then its parents up to the store root, e.g. 'z2/ocean', 'z2', ''.
            searchGroups = list( reversed( groupAncestors( group + '/_' ) ) )
            for coordName in coordinateNames:
                for searchGroup in searchGroups:
                    if coordName in arrayNames( searchGroup ):
                        coordinatePaths.add( f"{searchGroup}/{coordName}" if searchGroup else coordName )
                        break

        #Construct tuple of the coordinate variable and its size, so that it can updated to subgroup
        # The diagnoser records the sizes by the variable's path from the store root.
        storeSizes = self.diagnoserObj.exp_size_dict.get( zarrStorePath, {} )
        for coordName in sorted( coordinatePaths ):
            coordPath = os.path.join( zarrStorePath, coordName )
            try:
                coordSize = storeSizes[coordName]['size']
            except KeyError:
                logger.warning("Coordinate variable not found in size dict: %s", coordPath)
                continue
            dimensionsTupleList.append( (coordPath, coordSize) )
        return dimensionsTupleList

        
    def update(self):
        """To update the distributor object with the data obtained from the distribution of the input zarr stores.

        The distributor object will be updated either by scanning each of the zarr stores in the input experiment path,
        if starting afresh or use the JSON file created from a previous distribution of the experiment.

        Args:
                None.
        Returns:
                None.
        """
               
        zarrPath = configObj.getZarrStorePath() 
        storeName = zarrPath.split(os.path.sep)[-1]
        jsonFile = os.path.join(configObj.getWorkingDir(), f"{storeName.split('.')[0]}.dist")
        
        
        if os.path.isfile( jsonFile ):            
            print( f"Distribution file {jsonFile} found, loading the distribution!!!", flush=True )
            exp_size_dict_JSON_file = os.path.join( configObj.getWorkingDir(), jsonFile )
            with open( exp_size_dict_JSON_file, 'r' ) as expJSONFile:                
                # The members of the subgroups are nested by group (older versions wrote them as a list)
                frequencySubGroupJSON = flattenDistReport( json.load( expJSONFile ) )
                self.frequencySubGroupDict = {}
                # From this dictionary create subGroup objects and update the 'self.frequencySubGroupDict'
                for freq in frequencySubGroupJSON.keys():
                    # Add 'freq'
                    self.frequencySubGroupDict[freq] = {}
                    for subGroupName in frequencySubGroupJSON[freq].keys():
                        # Add 'subGroup'
                        subGroupObj =  subGroup_from_dict( frequencySubGroupJSON[freq][subGroupName] )
                        self.frequencySubGroupDict[freq][subGroupName] = subGroupObj
                
            expJSONFile.close()
            return 
        else:
            print( f"Distribution file {jsonFile} not found, running distributor!!!", flush=True )
            # Return a non zero value to trigger the diagnoser from calling function            
            distJSONnotfound = 1
            return distJSONnotfound
