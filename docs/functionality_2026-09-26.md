# Visual improvements 
* Icons need to be 2.5x larger than currently displayed
* Icons within the vpc or application collections need to be spaced out within their collection. By default, a service icon should be at least 2x away from the nearest icon on all sides.
* Icons should be draggable within their respective collection. 
* Icons cannot hide another icon when dragged
* The following additional information should be included on the mouse over (when available), with each attribute on its own line: databaseEngine, processorArchitecture, physicalProcessor, clockSpeed, tenancy, storageType, cacheEngine, networkPerformance, memory, storageMedia, volumeType, minVolumeSize, maxVolumeSize, storageClass, deploymentOption
* The following information should be removed from the mouse over: operation 

# Issues
* the same error message appears in both column 1 and column 2 -> when adding an application collection in the eu-west-2 region into a vpc from another region, , I (correctly) received the following error: "Test is in a different region than "Test" -- an Application can only nest inside a VPC in the same region", but it should have only appeared in column two - was that by design or a mistake during implementation?
* Adding a collection to the architecture canvas (that is not nested inside of an existing collection), will sometimes create the collection out of view in the canvas. New additions to the canvas should be placed within view of the current size of the canvas whenever possible

# Assigning Icons to Services
* Create a background process within our backend server that checks to see if we've added any new date partitions for our parquet data
    ** This service will run every hour, but that frequency should be configurable via a configuration
    ** If there is new parquet data, are there any new services? If yes, are there any new services that cannot be linked to an icon?
* For any new services that are missing icons, we need to make this information available to the admin: on the Admin tab, let's add an Issues table below the Create New User section. This table will display a line item for each service that cannot be linked to an icon.
    ** If there is no new parquet data, the service icon mapping analysis can be ignored
    ** If there is no new date partition but the existing, most recent date partition has been updated, the service icon mapping analysis should be run
 
# Configurations
* If there are any hard coded variables, these need to be moved into configurations. These configurations need to be something we can override via environment variable. Use the pydantic settings library to facilitate/simplify this effort

