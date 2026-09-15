# Web Pages

Stack: react + vite + typescript

## (1) Landing Page
==================================================================================================
==================================================================================================

                                                       |
        |                   ----- azure                |    Provider       Service Count
        |             ------                           |    --------       -------------
price   |      ------                                  |    AWS            x   (+/-n)
changes | ----------------------- aws | -----          |    GCP            y   (+/-n)
        |                                              |    Azure          z   (+/-n)
        --------------------------                     |
                  month                                |


==================================================================================================

  cloud          architectures    Pricing inputs  Pricing Calc
  providers
 -----------     -----------      -----------      -----------  
|           |   |           |    |           |    |           |   
|           |   |           |    |           |    |           |   
|           |   |           |    |           |    |           |   
|           |   |           |    |           |    |           |   
|           |   |           |    |           |    |           |   
|           |   |           |    |           |    |           |   
|           |   |           |    |           |    |           |   
|           |   | [create]  |    |  [calc]   |    |           |   
 -----------     -----------      -----------      -----------
  

==================================================================================================
==================================================================================================
* Top Left: chart of price movement trend by cloud provider, on mouse over of the plot, the chart should show the top 5 services contributing to the pricing movement and their respective contribution
* Top Right: table of services available by provider along with change in service count from prior week
* Middle/Bottom:
    * list of Available Cloud Providers
    * list of defined Architectures defined for selected cloud provider
    * list of pricing inputs for selected architecture
    * calcuated price for arch + inputs
* Actions: 
    * Select a cloud provider (update architectures window on click)
    * select an architecture (update pricing inputs required for calculations on click)
    * calculate cost of architecture on click of calculate button in pricing window
    * Pricing: populate pricing calc pane on click of calculate button
    * Create: create a new architecute - should launch a new tab or window that allows the user to assemble an architecture for that cloud's list of services/service collections
    * Delete: each line item in the architecture pane should have a red x to the left of it. on-click of the x, the user is prompted to confirm deletion ... on confirmation, the architecture is soft deleted (ie. it marks an architecture as deleted in the postgres db, but it's not physically removed)

## (2) Create Architecture Page

     Cloud Services             Architecture
    ----------------          ------------------- 
   |                |        |                   |
   |  -----         |        | Name: ____ [Save] |
   | |     | filter |        |                   |  
   |  -----         |        |                   | 
   | [] machines    |        |                   |
   | [] network     |        |                   |
   | [] data stores |        |                   | 
   | [] ...         |        |                   |
   | [] undefined   |        |                   |
   |                |        |                   |
    ----------------         |                   |
                             |                   |
     Components              |                   |
    ----------------         |                   |
   |                |        |                   |
   | - Application  |        |                   |
   |   Component    |        |                   |
   |                |        |                   |
   | - VPC          |        |                   |
   |                |         -------------------  
    ---------------

    * Components can be dragged into Architecture
    * Cloud Services can be dragged into a component within the architecture window
    * Cloud Services can be filtered by 
        * text filter - list of services filtered based on service name / text entered
        * service classification: checkboxes, that when selected, only show services for that classification (nothing selected == all selected)
    * if more than one vpc exists in an architecture, they must be connected - only certain services can be used to connect VPCs 

    * Architectures can be builts as follows:
        * base level building blocks: cloud specific services from the parquet files
        * collections of services: 
              * machines - contains hardware specific services, like EC2 instances
              * application components: contains software services like lambda, databases, etc     
              * vpcs - contains machines and application components
              * network components - cloud services that connect VPCs (these are needed so data flows into and out of VPCs can be priced properly)

# Backend Services

Stack: python, fast-api, postgres (but up for debate), duckdb

## API to service the front end
    * provide data to front end
    * persist user entries created on the front end

## Methods to retrieve cloud pricing data from parquet files

## Methods for pricing
    * base methods are needed to pull pricing information from parquet files
    * more complex methods needed to use pricing information from parquet files for all services in an architecture combined with user input


## Methods and/or configurations for "standard" architectures: e.g. big data etl, ml pipelines, basic website 

## Methods and/or configurations for service collections such as machines, VPCs and Network Components
    

# Cloud Pricing Data 
    * base directory: /Users/ghubs/Development/repos/personal/cloud-pricing/DATA
    * aws raw data: /Users/ghubs/Development/repos/personal/cloud-pricing/DATA/pricing_aws/raw - take the most recent directory in raw (directory names are formatted as YYYYMMDD_HHMISS)
    * aws parquet data: /Users/ghubs/Development/repos/personal/cloud-pricing/DATA/pricing_aws/parquet - take the most recent directory in raw (directory names are formatted as YYYYMMDD_HHMISS)


# Open Questions
    * How do base level cloud services get classified into collections (e.g. data stores, network, machines, etc ...) to help with filtering and facilitate user lookups when building architectures? I've proposed some in this specification, but this needs to be reviewed. Can it be driven based on the cloud provided data? Can we create configuration mappings to define these relationships and then have an additional page to manage the relationships / identify unmapped services?
    * How do we identify which services can be used to connect VPCs? Same answer as above? Can it be data driven?
