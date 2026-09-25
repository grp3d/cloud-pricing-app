# Creation of standardized architecture templates
- This functional update will create shared architectures under the Admin user so other users can build off of existing architectures
- These architectures should be persisted in postgres so there are immediately available to the application
- You'll need to determine which services in the parquet file can be used to match the descriptions in the architectures listed below. If there are multiple matches, it's ok to take the first available match (no need to prompt). For this phase, there is no need to create application application collections. Components listed for each architecture can be created under it's own VPC. If an architeccture lists more than one region, there should be a VPC for each region listed.
- Introduce a new functionality to export user architectures to disk and import architectures from disk. This functionality is separate from the import functionality on the Cloud Pricing tab. This new import/export functionality will be available only to the admin on the Admin tab. There will be two new columns added after the Password column and before the Purge column. Import Architectures from Disk, Export Architectures to Disk. Word wrap the header. In the Import Architectures from Disk column, there will be an Import button. In the Export Architectures to Disk column, there will be an Export button. The header text should be word wrapped to save space. The disk where files will be downloaded to/uploaded from will be on the user's file system (not the server's filesystem). File format should be json. For exports, files should be named as username_architecture_name_<timestamp-of-download>.json. On import, if the entire file is not in a valid format, let admin know import failed. If only one of the architectures in the import file is invalid or cannot be imported (e.g. service not in db or architecture name already exists), exclude that entry but process others. Post import, show the admin a popup window with a table containing the import status - each line contains 3 columns: status, architecture name, error message - status will be either a red x if import failed or a green checkmark if success. The line items with a red x should have a brief reason for the failure in the error message column
- Import/Export functionality noted above should use its own format that contains all of the data necessary to import the definitions into postgres as they exist today (the formats below should not be used - these are for baseline definitions to start requirement effort)

## Common Architectures
1. Active-Standby Multi-Region Web Application
High-availability enterprise web app with a primary active region and a cold/warm standby disaster recovery (DR) region.
Primary Region: us-east-1
Secondary DR Region: us-west-2
Components & Baseline Parameters:
Route 53: Global DNS with latency routing and health checks.
CloudFront: CDN caching global requests.
Application Load Balancer (ALB): 2 LCU baseline per region.
Compute (EC2): 4× t4g.xlarge (ARM-based Graviton3, Linux) in Auto Scaling Groups per region.
Database (Amazon RDS Aurora PostgreSQL): Multi-AZ primary instance (db.r6g.xlarge) with cross-region read-replica in us-west-2 for fast failover.
Storage (Amazon S3): 2 TB Standard S3 storage with Cross-Region Replication (CRR) to us-west-2.

2. Modern Data Lake & ETL Analytics Pipeline
Scalable event-driven ingestion platform for batch and real-time processing.
Region: us-east-1
Components & Baseline Parameters:
Ingestion (Amazon Kinesis Data Streams): 4 shards, continuous streaming.
Processing (AWS Glue): Serverless Apache Spark ETL running scheduled night jobs (10 DPU per job, ~2 hrs/day).
Object Storage (Amazon S3):
Raw Zone: 10 TB S3 Standard.
Analytics Zone: 5 TB S3 Standard (Parquet format).
Archive: Glacier Instant Retrieval (50 TB).
Data Catalog: AWS Glue Data Catalog.
Query Engine (Amazon Athena): Serverless SQL queries (~2 TB data scanned/day).
Data Warehouse (Amazon Redshift Serverless): 32 RPU base capacity for complex BI reporting.

3. Serverless Microservices Back-End
Cost-optimized, highly scalable API back-end with pay-per-use components.
Region: eu-west-1
Components & Baseline Parameters:
Edge & Auth: Amazon CloudFront + Amazon Cognito (10,000 Monthly Active Users).
API Layer: Amazon API Gateway (HTTP APIs) processing ~20 million requests/month.
Compute (AWS Lambda): 15 million executions/month (1024 MB memory, average duration 250 ms).
Database (Amazon DynamoDB): On-demand capacity mode, 50 GB storage, 5 million read units, 2 million write units per month.
Asynchronous Decoupling (Amazon SQS / SNS): Standard queues for background job processing (~10 million messages/month).

4. Containerized Microservices Platform (EKS)
Kubernetes-based enterprise platform hosting internal services and APIs.
Region: us-west-2
Components & Baseline Parameters:
Control Plane: Amazon EKS cluster fee ($0.10/hour).
Worker Nodes (EC2 / Fargate): 6× m6i.large managed node groups across 3 Availability Zones.
Container Registry (Amazon ECR): 100 GB stored image artifacts.
Internal Networking: Network Load Balancer (NLB) + AWS App Mesh.
Database (Amazon ElastiCache Redis): 2-node cluster (cache.m6g.large) for session caching.
Managed Database (Amazon RDS MySQL): Multi-AZ deployment on db.m6g.xlarge with 500 GB Provisioned IOPS (gp3) storage.

## JSON Containing Definitions for Common Architectures
{
  "version": "1.0",
  "generated_at": "2026-09-25T10:56:00Z",
  "architectures": [
    {
      "id": "arch_web_multi_region_active_standby",
      "name": "Active-Standby Multi-Region Web Application",
      "description": "Enterprise web application with primary active region and cross-region DR disaster recovery backup.",
      "category": "Web & Mobile Application",
      "regions": ["us-east-1", "us-west-2"],
      "components": [
        {
          "id": "r53_global_dns",
          "service": "AmazonRoute53",
          "region": "global",
          "type": "DNS",
          "attributes": {
            "hostedZones": 1,
            "healthChecks": 2
          },
          "usage": {
            "queriesPerMonth": 10000000
          }
        },
        {
          "id": "cloudfront_cdn",
          "service": "AmazonCloudFront",
          "region": "global",
          "type": "CDN",
          "attributes": {
            "priceClass": "PriceClass_All"
          },
          "usage": {
            "dataTransferOutGB": 5000,
            "httpRequests": 50000000,
            "httpsRequests": 50000000
          }
        },
        {
          "id": "alb_primary",
          "service": "ElasticLoadBalancing",
          "region": "us-east-1",
          "type": "ApplicationLoadBalancer",
          "attributes": {
            "count": 1
          },
          "usage": {
            "lcuPerHour": 2
          }
        },
        {
          "id": "ec2_app_primary",
          "service": "AmazonEC2",
          "region": "us-east-1",
          "type": "ComputeInstance",
          "attributes": {
            "instanceType": "t4g.xlarge",
            "operatingSystem": "Linux",
            "tenancy": "Shared",
            "count": 4,
            "purchaseOption": "OnDemand"
          },
          "usage": {
            "runningHoursPerMonth": 730
          }
        },
        {
          "id": "rds_aurora_primary",
          "service": "AmazonRDS",
          "region": "us-east-1",
          "type": "DatabaseInstance",
          "attributes": {
            "databaseEngine": "Aurora PostgreSQL",
            "instanceClass": "db.r6g.xlarge",
            "deploymentOption": "Multi-AZ",
            "count": 1
          },
          "usage": {
            "allocatedStorageGB": 250
          }
        },
        {
          "id": "s3_primary_bucket",
          "service": "AmazonS3",
          "region": "us-east-1",
          "type": "StorageBucket",
          "attributes": {
            "storageClass": "Standard"
          },
          "usage": {
            "storageGB": 2000,
            "putRequests": 50000,
            "getRequests": 500000
          }
        },
        {
          "id": "s3_crr_transfer",
          "service": "AWSDataTransfer",
          "region": "us-east-1",
          "type": "CrossRegionDataTransfer",
          "attributes": {
            "sourceRegion": "us-east-1",
            "destinationRegion": "us-west-2"
          },
          "usage": {
            "dataTransferGB": 250
          }
        },
        {
          "id": "rds_aurora_replica",
          "service": "AmazonRDS",
          "region": "us-west-2",
          "type": "ReadReplicaInstance",
          "attributes": {
            "databaseEngine": "Aurora PostgreSQL",
            "instanceClass": "db.r6g.xlarge",
            "deploymentOption": "Single-AZ",
            "count": 1
          },
          "usage": {
            "allocatedStorageGB": 250
          }
        },
        {
          "id": "s3_dr_bucket",
          "service": "AmazonS3",
          "region": "us-west-2",
          "type": "StorageBucket",
          "attributes": {
            "storageClass": "Standard"
          },
          "usage": {
            "storageGB": 2000
          }
        }
      ]
    },
    {
      "id": "arch_data_lake_etl_analytics",
      "name": "Modern Data Lake & ETL Analytics Pipeline",
      "description": "Event-driven ingestion platform for batch and real-time processing and analytics.",
      "category": "Analytics & Big Data",
      "regions": ["us-east-1"],
      "components": [
        {
          "id": "kinesis_stream",
          "service": "AmazonKinesis",
          "region": "us-east-1",
          "type": "DataStream",
          "attributes": {
            "shards": 4
          },
          "usage": {
            "putRecordsMB": 500000,
            "hoursPerMonth": 730
          }
        },
        {
          "id": "glue_etl_jobs",
          "service": "AWSGlue",
          "region": "us-east-1",
          "type": "ETLJob",
          "attributes": {
            "workerType": "G.1X",
            "dpuCount": 10
          },
          "usage": {
            "executionHoursPerDay": 2
          }
        },
        {
          "id": "s3_raw_zone",
          "service": "AmazonS3",
          "region": "us-east-1",
          "type": "StorageBucket",
          "attributes": {
            "storageClass": "Standard"
          },
          "usage": {
            "storageGB": 10000
          }
        },
        {
          "id": "s3_analytics_zone",
          "service": "AmazonS3",
          "region": "us-east-1",
          "type": "StorageBucket",
          "attributes": {
            "storageClass": "Standard"
          },
          "usage": {
            "storageGB": 5000
          }
        },
        {
          "id": "s3_archive_zone",
          "service": "AmazonS3",
          "region": "us-east-1",
          "type": "StorageBucket",
          "attributes": {
            "storageClass": "Glacier Instant Retrieval"
          },
          "usage": {
            "storageGB": 50000
          }
        },
        {
          "id": "athena_query_engine",
          "service": "AmazonAthena",
          "region": "us-east-1",
          "type": "InteractiveQuery",
          "attributes": {},
          "usage": {
            "dataScannedTBPerMonth": 60
          }
        },
        {
          "id": "redshift_serverless",
          "service": "AmazonRedshift",
          "region": "us-east-1",
          "type": "ServerlessDataWarehouse",
          "attributes": {
            "baseRPU": 32
          },
          "usage": {
            "rpuHoursPerMonth": 240
          }
        }
      ]
    },
    {
      "id": "arch_serverless_microservices",
      "name": "Serverless Microservices Back-End",
      "description": "Event-driven, cost-optimized backend using fully managed serverless infrastructure.",
      "category": "Serverless & APIs",
      "regions": ["eu-west-1"],
      "components": [
        {
          "id": "cognito_user_pools",
          "service": "AmazonCognito",
          "region": "eu-west-1",
          "type": "Authentication",
          "attributes": {
            "tier": "Lite"
          },
          "usage": {
            "monthlyActiveUsers": 10000
          }
        },
        {
          "id": "api_gateway_http",
          "service": "AmazonAPIGateway",
          "region": "eu-west-1",
          "type": "HTTP_API",
          "attributes": {},
          "usage": {
            "requestsPerMonth": 20000000
          }
        },
        {
          "id": "lambda_compute",
          "service": "AWSLambda",
          "region": "eu-west-1",
          "type": "Function",
          "attributes": {
            "allocatedMemoryMB": 1024,
            "architecture": "arm64"
          },
          "usage": {
            "executionsPerMonth": 15000000,
            "averageDurationMs": 250
          }
        },
        {
          "id": "dynamodb_nosql",
          "service": "AmazonDynamoDB",
          "region": "eu-west-1",
          "type": "NoSQLDatabase",
          "attributes": {
            "capacityMode": "On-Demand"
          },
          "usage": {
            "storageGB": 50,
            "readRequestUnits": 5000000,
            "writeRequestUnits": 2000000
          }
        },
        {
          "id": "sqs_queue",
          "service": "AmazonSQS",
          "region": "eu-west-1",
          "type": "StandardQueue",
          "attributes": {},
          "usage": {
            "requestsPerMonth": 10000000
          }
        }
      ]
    },
    {
      "id": "arch_containerized_eks_platform",
      "name": "Containerized Microservices Platform (EKS)",
      "description": "Kubernetes-based container platform with elastic caching and transactional database layer.",
      "category": "Containers & Orchestration",
      "regions": ["us-west-2"],
      "components": [
        {
          "id": "eks_control_plane",
          "service": "AmazonEKS",
          "region": "us-west-2",
          "type": "Cluster",
          "attributes": {
            "clusters": 1
          },
          "usage": {
            "hoursPerMonth": 730
          }
        },
        {
          "id": "eks_worker_nodes",
          "service": "AmazonEC2",
          "region": "us-west-2",
          "type": "ManagedNodeGroup",
          "attributes": {
            "instanceType": "m6i.large",
            "operatingSystem": "Linux",
            "count": 6
          },
          "usage": {
            "runningHoursPerMonth": 730
          }
        },
        {
          "id": "ecr_repository",
          "service": "AmazonECR",
          "region": "us-west-2",
          "type": "ContainerRegistry",
          "attributes": {},
          "usage": {
            "storageGB": 100
          }
        },
        {
          "id": "elasticache_redis",
          "service": "AmazonElastiCache",
          "region": "us-west-2",
          "type": "RedisCluster",
          "attributes": {
            "nodeType": "cache.m6g.large",
            "numNodes": 2
          },
          "usage": {
            "runningHoursPerMonth": 730
          }
        },
        {
          "id": "rds_mysql_primary",
          "service": "AmazonRDS",
          "region": "us-west-2",
          "type": "DatabaseInstance",
          "attributes": {
            "databaseEngine": "MySQL",
            "instanceClass": "db.m6g.xlarge",
            "deploymentOption": "Multi-AZ",
            "storageType": "gp3"
          },
          "usage": {
            "allocatedStorageGB": 500,
            "provisionedIOPS": 3000
          }
        }
      ]
    }
  ]
}

