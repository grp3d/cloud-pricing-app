# Issues
* Failure to price instance sku 2AB37QDFJZBGQ5YP
* In column 4, it's possible to add multiple services to a connector, but only 1 shows up -> let's allow only 1 service per connector, but it's possible to have multiple connectors between collections (must ensure that the connectors do not hide other connectors / overlap 100%)
* In column 4, the architecture diagram will sometimes go blank in the following scenarios: (1) add an application component, add a service to new application component, delete service, delete application component - on removal of the recently added application component, the architecture diagram goes blank. On refresh, the previously added applicaiton components appear and the deleted one is gone, so this is an issue specific to the front end rendering (2) when the architecture diagram is clicked several times: some sequence of clicking elements in the diagram and then blank space in the diagram (haven't been able to establish the pattern yet), the architecture diagram goes blank ... a page refresh fixes the issue
* In column 5, the price change is not adjusting when the duration is adjusted - if there is no architecture change, but the user changes the duration, the price change should adjust proportional to the duration change - for example, a month price change of -100 would need to be adjusted to a yearly price change of -100*12

# Updates
* In column 2, in the Add a Service section, below the 3 user search fields (and above the servies returned), add the text n of m services displayed in red if n < m (where m is the total number of services available for this search criteria and n is the number of services showing on the screen)
* In column 5 (pricing column), add thousand separators (',') to all pricing values
* In column 5 (pricing column), remove text like this "For 1 month, priced from snapshot YYYY-MM-DD" below the total price and price change. 
* In column 5 (pricing column), add text at bottom of column: "Data Timestamp: YYYY-MM-DD" (same date value as mentioned in previous bullet point) 
* In column 4 (arch diagram), do not include the collection type in the diagram.
* In column 4 (arch diagram), the border around the collection box should be darker.
* In column 4 (arch diagram), add a border around the service
* In column 4 (arch diagram), the collection box should only be resizeable from the bottom right corner and there should be a visual indicator of this (same as what exists around the entire architecture diagram)
* Reduce the font size everywhere by one unit, but in the architecture diagram in column 4, reduce it by 3 units
* In column 4 (arch diagram), spacing between components should be increased 
* In column 4 (arch diagram), when a user adjusts sizes and spacing, those new settings need to be saved so when the screen is refreshed / reloaded, the new sizes and positions stay the same
* In column 4 (arch diagram), underline the name of the selected application component, connector, service to clearly indicate when an object is selected
* Currently, the only way to add a connector In column 4 (arch diagram), is to highlight two application components (or vpcs) and click the connect button, let's add an "Add Connector" button - on click
* In column 2, when a service w/ service code = AWSDataTransfer appears, there needs to be (1) a better way to filter based on the fromRegionCode and toRegionCode fields (2) a better way to show the DataTransfer fields in the diagram - idea to consider -> for services w/ servicecode = "AWSDataTransfer", make a new text value "fromRegionCode=>"toRegionCode" ... this display text can (1) be added to the service list in column 2 (2) be used as the label in the arch diagram in column 4 (instead of the sku) (3) be used in the price per service list in column 5

