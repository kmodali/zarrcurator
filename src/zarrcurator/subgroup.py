"""
This module contains the declaration and definition of the class SubGroup.
"""

#Standard modules
from dataclasses import dataclass, field


# SubGroup
# SubGroup Object can consist of list of zarrs or variables or chunks

@dataclass(order=True)
class SubGroup:
    """ Class to create subGroups of type 'zarr', 'var' or 'chunk' based on the size of the zarr store.
    """

    groupMembers: list = field(compare=False)
    """list: List of the subGroup members.
    The members of the subGroup could be complete 'zarr' store or some variables or some chunks of a variable.
    """

    groupType: str = field(compare=False)
    """str: Type of the subGroup.
    The subGroup could be of type 'zarr' or 'var' or 'chunk'.
    """

    groupTarMembers: list = field(compare=False)
    """list: List of the subGroup members.
    The tar names corresponding to the subGroup could be single or list based on 'groupType' complete 'zarr' 
    store or some variables or some chunks of a variable.
    """

    groupTarTapeIDs: list = field(compare=False)
    """list: List of the subGroup Tar members Tape IDs.
    The tape IDs corresponding to the tar members of the subGroup.
    """
    
    groupSize: int
    """int: The size of the subGroup.
    The subGroup could be of type 'zarr' or 'var' or 'chunk'.
    """

    _groupSize: int = field(init = False, repr = False, default = 0)
    
    
    @property
    def groupSize(self) -> int:
        """To get the group size of the subGroup.

        To get the type of the subGroup.

        Args:
                None.
        Returns:
                int: Size of the subGroup.
        """

        return self._groupSize
    
    
    @groupSize.setter
    def groupSize(self,value: int) -> None:
        """To compute the size of the subGroup.

        To compute the size of the subGroup by adding up the subGroup members.

        Args:
                int: To set the groupsize to the variable.
        Returns:
                None.
        """
        
        if type(value) is property:
            value = sum(x[1] for x in self.groupMembers)
        self._groupSize = value

    
    def setGroupType(self,typeStr):
        """To set the type of the subGroup.

        To set the type of the subGroup.

        Args:
                str: Type of the subGroup 'zarr', 'var' or 'chunk'.
        Returns:
                None.
        """

        self.groupType =  typeStr

    
    def getGroupType(self):
        """To get the type of the subGroup.

        To get the type of the subGroup.

        Args:
                None.
        Returns:
                str: Type of the subGroup 'zarr', 'var' or 'chunk'.
        """

        return self.groupType


    def setGroupTarMembers(self,tarNamesList):
        """To set the tar file names for the subGroup.

        To set the list of tar file names for the tarballs produced for the subGroup.

        Args:
                list[str]: List of tar file names.
        Returns:
                None.
        """

        self.groupTarMembers =  tarNamesList

    
    def getTarMembers(self):
        """To get the tar file names for the subGroup.

        To get the list of tar file names for the tarballs produced for the subGroup.

        Args:
                None.
        Returns:
                list[str]: List of tar file names.
        """

        return self.groupTarMembers
    
    
    def setgroupTarTapeIDs(self,groupTarTapeIDs):
        """To set the tape IDs for the tar file names for the subGroup.

        To set the list of tape IDs for the tar file names for the tarballs produced for the subGroup.

        Args:
                list[str]: List of tape IDS for tar file names.
        Returns:
                None.
        """

        self.groupTarTapeIDs =  groupTarTapeIDs
    
    
    def getTarTapeIDs(self):
        """To get the tape IDs for the tar file names for the subGroup.

        To get the list of tape IDs for the tar file names for the tarballs produced for the subGroup.

        Args:
                None.
        Returns:
                list[str]: List of tape IDs for tar file names.
        """

        return self.groupTarTapeIDs
    
    
    def updateSubGroup(self, obj):
        """To update the subGroup object with diagnoser object with the data obtained from the diagnosis of the input zarr stores.

        The diagnoser object will be updated either by scanning each of the zarr stores in the input experiment path,
        if starting afresh or use the JSON file created from a previous diagnosis of the experiment.

        Args:
                list[tuple] or tuple: Tuple or list of tuples to update the SubGroup object.
        Returns:
                None.
        """

        if type(obj) is list:
            for tupObj in obj:
                self.groupMembers.append(tupObj)
        else:
            self.groupMembers.append(obj)
        self.updateSubGroupSize()
        
    
    def updateSubGroupSize(self):
        """To update the subGroup size.

        To update the subgroup size by adding up the sizes of the subGroup members.

        Args:
                None.
        Returns:
                None.
        """

        self.groupSize = sum(x[1] for x in self.groupMembers)


def subGroup_to_dict(subGroup):
    return {
        'groupMembers':subGroup.groupMembers,
        'groupType':subGroup.groupType,
        'groupTarMembers':subGroup.groupTarMembers,
        'groupTarTapeIDs':subGroup.groupTarTapeIDs,
        'groupSize':subGroup.groupSize
    }


def subGroup_from_dict(subGroupDict):

    # check to remove .
    #if
    
    subGroup = SubGroup( subGroupDict['groupMembers'],subGroupDict['groupType'],
                         subGroupDict['groupTarMembers'],subGroupDict['groupTarTapeIDs'] )
    subGroup.updateSubGroupSize()

    return subGroup
