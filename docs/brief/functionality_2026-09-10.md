# Corrections
* column 4 architecture diagram sizing is still an issue: (1) no boxes within the architecture can be resized by hand (2) boxes are not sized properly to display readable text inside (3) when clicking an empty space inside of a VPC component, the entire diagram disappears and a page refresh is needed to bring it back
* column 4 proposal: Review the React Flow section for sizing/resize bugs — check node dimension handling, parentId/extent nesting, and whether resize state goes through applyNodeChanges.  Compare against the four failure modes: custom resize logic bypassing NodeResizer, implicit CSS sizing, v11/v12 API mixing, and direct state mutation.k
* column 4 proposal 2: would a full re-write of this part of the page be worth the effort?


# Updates
* reduce the font sizes used everywhere by 70%
* in the 1st column,  remove the (soon) text from the GCP and Azure entries 
* in the 1st column, each cloud provider should be on it's own line 
* in the 1st column, when the column is minimized, show the following icons from each cloud provider: gcp -> /Users/ghubs/Development/repos/personal/cloud-pricing/screenshot-samples/gcp_icon.png, aws -> /Users/ghubs/Development/repos/personal/cloud-pricing/screenshot-samples/aws_icon.png, azure -> /Users/ghubs/Development/repos/personal/cloud-pricing/screenshot-samples/azure_icon.png
* in the 1st column, move the Create button and input text to be below the last architecture listed in the AWS Architectures section
* in columns 2 and 3, add the collapse icon to the top right corner 
* in the 2nd column
    * put separators between sections and if a section is empty, then nothing will exist between the 2 separators, but the separators should still be visible
    * column header for column 2 changes from  (None) -> Architecture Editor
    * sections names in column 2 should be (1) Collections & Connectors -> Collections, (2) (None) -> Selected Collection (3) Search AWS Services -> Add a Service
* in column 3, add column header of Service Editor
* in column 3, do not hide, always show column but column 3 can be blank when the user selects a section of the architecture that is not a service 
* in column 4, the architecture window needs to have more height or be adjustable/expandable from the bottom right corner so it can occupy more space (it currently occupies all available width but only 1/3 of available height when window is resized)
* all columns should have adjustable column widths by mousing over horizontal separator to slide - widths of columns should be saved/configurable per user
* in column 5, all pricing calculation results should be rounded to 2 decimal places. 
* in column 5, when a user clicks calculate, show a new field below the total named Price Change. Price change is calculated as Current Total - Prior Total. This means we need a placeholder for prior total. Prior total should only be updated when there has been an actual update to the architecture. For example, if the user clicks Calculate twice with no architecture change between the clicks, the Price Change value should be whatever it was prior to the 1st click (not 0). If price increased, show a red arrow to the right of the price change pointing up, if price decreased, show green arrow pointing down to the right of the price change ... if no price change, no arrow. 
* in column 5, add a section (with separator) below the pricing section, named Price per Sku, that contains the total price of every sku in the architecture (sku on left hand side, total price per sku on right hand side is sufficient) 
* adding color: let's use sky color scheme in Radix combined with shaden/ui to provide color to the site
