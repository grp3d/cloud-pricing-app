# New Functionality

## Replace text in the architecture canvas (column 4) with icons

- Instead of displaying text detail in the diagrams, we're going to use standard aws icons based on the service code and/or product family. 
- It's ok for a diagram to have the same icon multiple times
- On mouseover of an icon, the text that is currently being displayed in the arch canvas will be displayed in a pop-up, with a few updates to the text:
    - Rather than separating the service code and the sku with a '/', we'll put the sku on a new line with a Sku: prefix. Rather than place the group description after the dash, we'll put the group description field (when available) on a new line, followed by the UsageType (when available) and the Operation (when available).
    - Sample before and after:
      Before: AmazonDynamoDB / 3ERQSZWPAMX2JWHN -- DynamoDB PayPerRequest Read Request Units
      After: AmazonDynamoDB
             Sku: 3ERQSZWPAMX2JWHN
             DynamoDB PayPerRequest Read Request Units  <- when available
             UsageType: EU-ReadRequestUnits
             Operation: PayPerRequestThroughput 
- Icons to use
    - all official AWS icons can be found here: /Users/ghubs/Development/repos/personal/cloud-pricing/images-web/aws_architecture_icons
    - the icons we'll likely need are in /Users/ghubs/Development/repos/personal/cloud-pricing/images-web/aws_architecture_icons/Architecture-Service-Icons_07312026 and their respective sub-directories 
    - images in sub directory 48 should be sufficient size
    - to match services to the correct image, you'll need to analyze the different service codes available in parquet and do approximate matching based on the filenames of the icons under the service icon sub directories
- The icons (along with their respecitive pop-up text) should scale (smaller/larger) as the zoom out/zoom in buttons are used (as it works today for the text in the canvas.


# Issues to Resolve

## Current state for Column 5 pricing column is that when toggling between architectures, the pricing tab shows the last computation done (for any architecture). The pricing tab should maintain a pricing history per architecture, so it  should display the last calucated price (and breakdown used below the price) for the architecture that is active. If there is no prior calculation for the active arcthitecture it should be calculated and populated.
