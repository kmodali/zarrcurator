#Standard modules
import sys
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("zarrcurator")
except PackageNotFoundError:
    __version__ = "0+unknown"

def enable_logging(log_level=None):
    """Enable zarrcurator logging for notebooks and library usage.

    This configures both console logging and a timestamped log file,
    using the same behavior as the CLI.
    """

    from .cli import configure_logging

    return configure_logging(log_level)


__all__ = ["__version__", "enable_logging"]

'''
try:
    from .config import configObj
except:
    print( sys.exc_info() )
    print( f"Module 'config' import error in {__file__}" )
'''

try:
    from .utils import (
        convertKerchunkReferenceFilesOfZarrStoreToParquet,
        createKerchunkReferenceFileForTar,
        diagnoseStore,
        dispatchStoreToTarStores,
        displayStoreSunburst,
        distributeStoreToSubStores,
        findMissingChunksInStore,
        flattenCheckReport,
        loadConfigFromFile,
        nestCheckReport,
        saveConfigToFile,
        setObjectStoreCredentials,
        usage,
    )
                
    '''
                       displayZarrStoreVariables, updateArchBasePath, \
                       mapTapeIDsToFrequencySubGroupDict, displayZarrStoresTarTapes, displayZarrStoreVarTarTapes
    '''
except:
    print( sys.exc_info() )
    print( f"Module 'utils' import error in {__file__}" )
