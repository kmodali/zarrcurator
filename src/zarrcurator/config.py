"""
This module contains the configuration variables to handle the various features of the zarrcurator tool. 
The configuration variables consists of the various path, the flag to handle the mode of operation viz.,
interactive or batch mode.
"""
#Standard Modules
import os
import sys
import json
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

#Non-Standard modules
try:
    import validators
except:
    logger.exception("Module 'validators' import error in %s", __file__)

try:
    import fsspec
except:
    logger.exception("Module 'fsspec' import error in %s", __file__)


# Dictionary to store variables realmwise for ICON model.
# atmos_* -- Received coupling fields on the ocean side.
#

realmDict = {
    "dimensions" : [ 
        "time", "pfull", "phalf", "zghalf", "delhi", "depth_full", "depth_half", "dzghalf", "level_full", "level_half" ],
    
    "atmosphere" : [
        "cli",  "clivi",  "cllvi",  "clw",    "crs",
        "hfls", "hfss",  "hus",
        "pr", "pres_msl", "pres_sfc", "prls", "prw",
        "qg",  "qgvi",  "qr",  "qrvi",  "qs",  "qsvi",  "qv2m",
        "rlds",  "rlus",  "rlut",  "rsds",  "rsdt",  "rsus",  "rsut",
        "sic",   "sit",   "sfcwind",   
        "ta", "tas", "tauu", "tauv",  "ts",
        "ua", "uas", 
        "va", "vas", 
        "wa_phy",
        "zg"
    ],
    "ocean" : [
        "atmos_fluxes_FrshFlux_Evaporation",
        "atmos_fluxes_FrshFlux_Precipitation",
        "atmos_fluxes_FrshFlux_Runoff",
        "atmos_fluxes_FrshFlux_SnowFall",
        "atmos_fluxes_HeatFlux_Latent",
        "atmos_fluxes_HeatFlux_LongWave",
        "atmos_fluxes_HeatFlux_Sensible",
        "atmos_fluxes_HeatFlux_ShortWave",
        "atmos_fluxes_HeatFlux_Total",
        "atmos_fluxes_stress_x",
        "atmos_fluxes_stress_xw",
        "atmos_fluxes_stress_y",
        "atmos_fluxes_stress_yw",
        "conc",
        "ocean_fraction_depth_full",
        "ocean_fraction_depth_half",
        "ocean_fraction_surface",
        "hi", "hs",
        "heat_content_seaice",
        "heat_content_snow",
        "heat_content_total",
        "heatOceI",
        "heatOceW",
        "ice_u",
        "ice_v",
        "mlostst",
        "newice",
        "snow_to_ice",
        "so",
        "stretch_c",
        "tke", "to",
        "u", "v", "w",
        "u_vint", "v_vint",
        "zos"
    ],
    "land" : [
        "hydro_canopy_cond_limited_box",
        "hydro_snow_soil_dens_box",
        "hydro_discharge_ocean_box",
        "hydro_transpiration_box",
        "hydro_drainage_box",
        "hydro_weq_snow_box",
        "hydro_ice_soil_sl_box",
        "hydro_wtr_soil_sl_box",
        "hydro_runoff_box",
        "soil_depth_water_level",
        "soil_depth_energy_level",
        "sse_t_soil_sl_box",
        "seb_forc_hflx_box", 
        "sse_grnd_hflx_old_box", 
        "seb_heat_cap_box",
    ],
    "biogeo" : []
}


class configVars():
    """Config class to hold the configuration variables to be used across the modules in the package.
    """

    def __init__( self, zarr_store_path=None, workingDir=os.getcwd(), jsonFile=None,
                  targetSize=200*1024*1024*1024, batchMode=False, debugMode=False,
                  packDiscontinuousData=False, accessKey=None, secretKey=None ):
        
        self.zarrStorePath = zarr_store_path
        """path: Path of the zarr stores.
        The directory under which the zarr stores for each healpix and frequency combination exist. 
        """

        self.fileSystemObj = None
        """object[class FileSystem]: File System Object.
        The zarrcurator creates an object of class File System to handle the appropriate object store,
        if the 'zarr_store_path' happens to be an URL.
        """        

        self.workingDir =  workingDir
        """path: Path to working directory.
        The location of the directory under which the output prouced by zarrcurator tool will be stored.
        """

        self.archBasePath =  None
        """path: Path to base directory on HSM.
        The location of the directory on HSM under which the tarballs prouced by zarrcurator tool will be stored.
        """
        
        self.jsonFile = jsonFile
        """str: Name of the jsonFile produced by zarrcurator.
        The JSON file contains the output[file sizes, count] of the diagnosis of the input zarr stores.
        """

        self.targetSize = targetSize
        """int: Target size for each tar ball.
        The size of the tar ball keeping in view the constraints of the HSM system, as of now 200 GB.
        """

        self.batchMode = batchMode
        """bool: Flag to handle the mode of operation.
        The zarrcurator can be used in interactive mode (jupyter notebook) or batch mode(run as a SLURM job).
        Based on the mode,plots generated will be displayed inline or saved as image files.This flag if set to
        True, indicates the mode is batch mode.
        """

        self.diagnoserObj =  None
        """object[class Diagnoser]: Diagnoser Object.
        The zarrcurator creates an object of class Diagnoser to handle the task of diagnosing the input zarr stores.
        """
        
        self.distributorObj = None
        """object[class Distributor]: Distributor Object.
        The zarrcurator creates an object of class Diagnoser to handle the task of diagnosing the input zarr stores.
        """
        
        self.dispatcherObj = None
        """object[class Dispatcher]: Dispatcher Object.
        The zarrcurator creates an object of class Dispacther to handle the task of creating and dispatching the tarballs for the input zarr stores.
        """
        
        self.debugMode = debugMode
        """bool: Flag to handle the debug mode of operation.
        True, indicates the mode is debug mode.
        """
        
        self.packDiscontinuousData = packDiscontinuousData
        """bool: Flag to handle the discontinuities in the data.
        True, indicates to pack the data even if missing chunks are detected.
        """
        
        self.accessKey = accessKey
        """string: Access key environment variable.
        Environment variable which contains the access key for the object store.
        """

        self.secretKey = secretKey
        """string: Secret key environment variable.
        Environment variable which contains the secret key for the object store.
        """
        

        

    def getZarrStorePath(self):
        """Get the path of the zarr stores.

        To get the directory under which the zarr stores, for each healpix and frequency combination exist. 

        Args:
                None.
        Returns:
                path: Path to zarr stores.
        """
        logger.debug("getZarrStorePath=%s", self.zarrStorePath)
        return self.zarrStorePath

    
    def setZarrStorePath(self, zarr_store_path):
        """Set the path of the zarr stores.

        To set the directory under which the zarr stores, for each healpix and frequency combination exist. 

        Args:
                path: Path to zarr stores.
        Returns:
                None.
        """
        logger.debug("setZarrStorePath input=%s", zarr_store_path)

        # if URL then initialize the appropriate File system object.
        if validators.url(zarr_store_path.strip(" ")):  # Object store case
            self.zarrStorePath = self.setFileSystemObj(zarr_store_path)
        else:  # Local file system case, validate the path and set the zarr store path.
            if not os.path.isdir(zarr_store_path):
                logger.error("Input zarr store path does not exist: %s", zarr_store_path)
                sys.exit()

            self.zarrStorePath = zarr_store_path

        logger.info("Configured zarr store path=%s", self.zarrStorePath)


    def getFileSystemObj(self):
        """Get the file system object.

        To get the file system object, so that it can be used in other classes of the zarrcurator viz., diagnoser.

        Args:
                None.
        Returns:
                object[class FileSystem]: File system object.
        """

        return self.fileSystemObj


    def setFileSystemObj(self,zarr_store_path):
        """Set the file system object.

        To set the file system object, so that it can be used in other classes of the zarrcurator viz., diagnoser.

        Args:
                None.
        Returns:
                None.
        """

        # Currently handling S3 and swift at DKRZ, to extend in future to other cases.
        # Strip empty spaces before validation.
        def _build_s3_filesystem(endpoint_url, region_name, store_url):
            access_key = (
                (os.getenv(self.accessKey) if self.accessKey else None)
                or os.getenv("AWS_ACCESS_KEY_ID")
                or os.getenv("S3_ACCESS_KEY_ID")
            )
            secret_key = (
                (os.getenv(self.secretKey) if self.secretKey else None)
                or os.getenv("AWS_SECRET_ACCESS_KEY")
                or os.getenv("S3_SECRET_ACCESS_KEY")
            )

            client_kwargs = {
                'endpoint_url': endpoint_url,
                'region_name': region_name,
            }

            probe_path = store_url.replace(f"{endpoint_url}/", "", 1)

            # Try anonymous access first.
            anon_fs = fsspec.filesystem(
                "s3",
                client_kwargs=client_kwargs,
                anon=True,
            )
            try:
                anon_fs.ls(probe_path)
                return anon_fs
            except Exception as exp:
                logger.warning("Anonymous access failed for %s: %s", store_url, exp)

            # If anonymous access failed, try configured credentials if available.
            if access_key and secret_key:
                auth_fs = fsspec.filesystem(
                    "s3",
                    client_kwargs=client_kwargs,
                    key=access_key,
                    secret=secret_key,
                    anon=False,
                )
                try:
                    auth_fs.ls(probe_path)
                    return auth_fs
                except Exception as exp:
                    logger.error("Credentialed access failed for %s: %s", store_url, exp)
                    sys.exit()

            logger.error(
                "Store is not publicly accessible and no access credentials are configured: %s. "
                "Set accessKey/secretKey in config or AWS/S3 credential environment variables.",
                store_url,
            )
            sys.exit()

        fsObj = None
        if validators.url(zarr_store_path.strip(" ")):
            if "swift.dkrz.de" in zarr_store_path.strip(" "):
                fsObj = fsspec.filesystem("swift")
            elif "s3.eu-dkrz-1.dkrz.cloud" in zarr_store_path.strip(" "):  # Production cluster
                fsObj = _build_s3_filesystem(
                    endpoint_url='https://s3.eu-dkrz-1.dkrz.cloud',
                    region_name='eu-dkrz-1',
                    store_url=zarr_store_path,
                )
                zarr_store_path = zarr_store_path.replace("https://s3.eu-dkrz-1.dkrz.cloud/", "")
            elif "s3.eu-dkrz-3.dkrz.cloud" in zarr_store_path.strip(" "):  # Pre-production cluster
                fsObj = _build_s3_filesystem(
                    endpoint_url='https://s3.eu-dkrz-3.dkrz.cloud',
                    region_name='eu-dkrz-3',
                    store_url=zarr_store_path,
                )
                zarr_store_path = zarr_store_path.replace("https://s3.eu-dkrz-3.dkrz.cloud/", "")
                logger.debug("Configured pre-production object store path=%s", zarr_store_path)
            elif "s3-ext" in zarr_store_path.strip(" "):
                fsObj = _build_s3_filesystem(
                    endpoint_url='https://hackathon-o.s3-ext.jc.rl.ac.uk',
                    region_name='uk',
                    store_url=zarr_store_path,
                )
                zarr_store_path = zarr_store_path.replace("https://hackathon-o.s3-ext.jc.rl.ac.uk/", "")
            else:
                logger.error("Store type for path is not handled: %s", zarr_store_path)
                sys.exit()

        self.fileSystemObj = fsObj

        logger.info("Configured object-store path=%s", zarr_store_path)
        return zarr_store_path



    @staticmethod
    def parse_object_store_url(url: str):
        """Parse an object-store HTTP URL into:
                - endpoint
                - bucket
                - object key
                - s3 uri
        """

        parsed = urlparse(url)

        # Endpoint
        endpoint = f"{parsed.scheme}://{parsed.netloc}"

        # Split path into bucket + key
        path_parts = parsed.path.lstrip("/").split("/", 1)

        if len(path_parts) < 2:
                raise ValueError("URL does not contain both bucket and object key")

        bucket = path_parts[0]
        object_key = path_parts[1]

        # Construct S3 URI
        s3_uri = f"s3://{bucket}/{object_key}"

        return {
                "endpoint": endpoint,
                "bucket": bucket,
                "object_key": object_key,
                "s3_uri": s3_uri,
        }


    def getWorkingDir(self):
        """Get the path of the working directory.

        To get the directory under which the output produced by zarrcurator will be stored. 

        Args:
                None.
        Returns:
                path: Path to working directory.
        """

        return self.workingDir


    def setWorkingDir(self, workingDir):
        """Set the path of the working directory.

        To set the directory under which the output produced by zarrcurator will be stored. 

        Args:
                path: Path to working directory.
        Returns:
                None.
        """

        if not os.path.isdir(workingDir):
            logger.error("Working directory does not exist: %s", workingDir)
            sys.exit()

        self.workingDir = workingDir
    
    
    def getArchBasePath(self):
        """Get the path of the directory on HSM.

        To get the location of the directory on HSM under which the tarballs prouced by zarrcurator tool will be stored.

        Args:
                None.
        Returns:
                path: Path to base directory on HSM.
        """

        return self.archBasePath
    
    
    def setArchBasePath(self, archBasePath):
        """Set the path of the directory on HSM.

        To set the location of the directory on HSM under which the tarballs prouced by zarrcurator tool will be stored.

        Args:
                path: Path to base directory on HSM.
        Returns:
                None.
        """
        self.archBasePath = archBasePath
        
        return
    
    
    def getJsonFile(self):
        """Get the name of the JSON file.

        To get the name of the output JSON file produced by zarrcurator. 

        Args:
                None.
        Returns:
                str: Name of the JSON file.
        """

        return self.jsonFile


    def setJsonFile(self, json_file):
        """Set the name of the JSON file.

        To set the name of the output JSON file produced by zarrcurator. 

        Args:
                str: Name of the JSON file.
        Returns:
                None.
        """

        self.jsonFile = json_file


    def getTargetSize(self):
        """Get the target size of the tarball.

        To get the target size of the tar ball keeping in view the constraints of the HSM system, as of now 200 GB.

        Args:
                None.
        Returns:
                int: Target size of the tarball.
        """

        return self.targetSize


    def setTargetSize(self, targetSize):
        """Set the target size of the tarball.

        To set the target size of the tar ball keeping in view the constraints of the HSM system, as of now 200 GB.

        Args:
                int: Target size of the tarball.
        Returns:
                None.
        """

        self.targetSize = targetSize


    def getBatchMode(self):
        """Get the mode of operation of the zarrcurator.

        To get the mode of operation of the zarrcurator viz., interactive or batch mode.

        Args:
                None.
        Returns:
                bool: mode of operation of the zarrcurator.
        """

        return self.batchMode


    def setBatchMode(self, batchMode):
        """Set the mode of operation of the zarrcurator.

        To set the mode of operation of the zarrcurator viz., interactive or batch mode.

        Args:
                bool: mode of operation of the zarrcurator.
        Returns:
                None.
        """

        self.batchMode = batchMode
    
    
    def getDebugMode(self):
        """Get the debug mode of operation of the zarrcurator.

        To get the debug mode of operation of the zarrcurator.

        Args:
                None.
        Returns:
                bool: Debug mode of operation of the zarrcurator.
        """

        return self.debugMode
    
    
    def setDebugMode(self, debugMode):
        """Set the debug mode of operation of the zarrcurator.

        To set the debug mode of operation of the zarrcurator.

        Args:
                bool: Debug mode of operation of the zarrcurator.
        Returns:
                None.
        """

        self.debugMode = debugMode
    
    
    def getPackDiscontinuousData(self):
        """Get the flag for packing the discontinuous data.

        To get flag to pack the data even if the chunks are missing.

        Args:
                None.
        Returns:
                bool: Flag to indicate the packing of missing chunks.
        """

        return self.packDiscontinuousData
    
    
    def setPackDiscontinuousData(self, packDiscontinuousData):
        """Set the flag for packing the discontinuous data.

        To set the flag to pack the data even if the chunks are missing .

        Args:
                bool: Flag to indicate the packing of missing chunks.
        Returns:
                None.
        """
    
        self.packDiscontinuousData = packDiscontinuousData
    
    
    def getaccessKey(self):
        """Get the accessKey for accessing the object store.

        To get the access key environment variable name.

        Args:
                None.
        Returns:
                str: Name of the environment variable.
        """

        return self.accessKey
    
    
    def setaccessKey(self, accessKey):
        """Set the accessKey for accessing the object store.

        To set the access key environment variable name.

        Args:
                str: Name of the environment variable.
        Returns:
                None.
        """

        self.accessKey = accessKey
    
    
    def getsecretKey(self):
        """Get the secretKey for accessing the object store.

        To get the secret key environment variable name.

        Args:
                None.
        Returns:
                str: Name of the environment variable.
        """

        return self.secretKey
    
    
    def setsecretKey(self, secretKey):
        """Set the secretKey for accessing the object store.

        To set the secret key environment variable name.

        Args:
                str: Name of the environment variable.
        Returns:
                None.
        """

        self.secretKey = secretKey
    
    
    def getDistributorObj(self):
        """Get the distributor object.

        To get the distributor object, so that it can be used in other classes of the zarrcurator viz., dispatcher.

        Args:
                None.
        Returns:
                object[class Distributor]: Distributor object.
        """

        return self.distributorObj


    def setDistributorObj(self, distObj):
        """Set the distributor object.

        To set the distributor object, so that it can be used in other classes of the zarrcurator viz., dispatcher.

        Args:
                object[class Distributor]: Distributor object.
        Returns:
                None.
        """

        if distObj is None:
            logger.error("Distributor object is None")
            sys.exit()

        self.distributorObj = distObj


    def getDiagnoserObj(self):
        """Get the diagnoser object.

        To get the diagnoser object, so that it can be used in other classes of the zarrcurator viz., displayer.

        Args:
                None.
        Returns:
                object[class Diagnoser]: Diagnoser object.
        """

        return self.diagnoserObj


    def setDiagnoserObj(self, diagObj):
        """Set the diagnoser object.

        To set the diagnoser object, so that it can be used in other classes of the zarrcurator viz., displayer.

        Args:
                object[class Diagnoser]: Diagnoser object.
        Returns:
                None.
        """

        if diagObj is None:
            logger.error("Diagnoser object is None")
            sys.exit()

        self.diagnoserObj = diagObj


    def getDispatcherObj(self):
        """Get the dispatcher object.

        To get the dispatcher object, so that it can be used in other parts of the zarrcurator viz., utils.

        Args:
                None.
        Returns:
                object[class Dispatcher]: Dispatcher object.
        """

        return self.dispatcherObj


    def setDispatcherObj(self, dispatcherObj):
        """Set the dispatcher object.

        To set the dispatcher object, so that it can be used in other parts of the zarrcurator viz., utils.

        Args:
                object[class Dispatcher]: Dispatcher object.
        Returns:
                None.
        """

        if dispatcherObj is None:
            logger.error("Dispatcher object is None")
            sys.exit()

        self.dispatcherObj = dispatcherObj

    
    def toFile(self, configFileName):
        """Save the config object to a JSON file.

        To save the zarrcurator configuration object, so that it can be edited and used.

        Args:
                str: File name for storing the config object in JSON format.
        Returns:
                None.
        """

        # Runtime objects are not persisted because they are process-local and
        # can be rebuilt from persisted configuration values when needed.
        persisted_config = {
            "zarrStorePath": self.zarrStorePath,
            "workingDir": self.workingDir,
            "archBasePath": self.archBasePath,
            "jsonFile": self.jsonFile,
            "targetSize": self.targetSize,
            "batchMode": self.batchMode,
            "debugMode": self.debugMode,
            "packDiscontinuousData": self.packDiscontinuousData,
            "accessKey": self.accessKey,
            "secretKey": self.secretKey,
        }

        with open( configFileName, "w" ) as fileObj:
            json.dump(persisted_config, fileObj, indent=4)


    def fromFile(self, configFileName):
        """Read the config object from a JSON file.

        To read the zarrcurator configuration object, so that it can be used in the current session.

        Args:
                str: File name for reading the config object in JSON format.
        Returns:
                None.
        """

        with open( configFileName, "r" ) as fileObj:
            configData = json.load( fileObj )

        for key, value in configData.items():
            if hasattr(self, key):
                setattr(self, key, value)

configObj = configVars(None,None,None,200*1024*1024*1024,False,False,False)     
