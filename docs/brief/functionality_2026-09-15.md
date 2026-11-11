# Issues
# Updates
1. aws pricing retrieval now includes additional aws regions (each in its own partition), the following needs to be updated accordingly 
   1a. add a region attribute to vpc collections and application component collections: (1) Change text of APplication Components to Applications (the goal is to reduce the size of the VPC / Applications dropdown and make more room for the collection name (2) on  click of +Add for a collection, present a pop up with a dropdown of available regions that this collection will be placed in
   1b. Once a collection contains a service (or in the case of the VPC, an application component or a service), the aws region cannot be changed
   1c. An application collection belonging to region X can only be dragged into a VPC in region X
   1d. The service search should only show service within the region for the collection that has been selected 
   1e. For connectors (which can connect 2 VPCs in different regions) the service list displayed should be based on the "from" collection
   1f. For connectors: when clicking Add Connector, there is an explicit from collection and to collection, so step 1e should be straight forward - however, when clicking the connect button in the collections section of column 2, it's unclear -> in this scenario, the box selected 1st will be the from collection and the box selected second will be the to collection. Lastly, connectors should have arrows, with the arrow pointing to the "to" collection

2. Let's update the pricing breakdown per sku in column 5 to be separated by region and include subtotals by region, so now, under the total will be 
   Region          region-name
   line item             $ 
   ... 
   line item n           $
   region-name total     $ 

   Region          region-name 2
   line item             $ 
   ... 
   line item n           $
   region-name-2 total   $ 

   Data Timestamp: 
