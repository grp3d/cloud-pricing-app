{
  "version": "1.1",
  "generated_at": "2026-09-25T11:55:00Z",
  "architectures": [
    {
      "id": "arch_web_multi_region_active_standby",
      "name": "Active-Standby Multi-Region Web Application",
      "description": "High-availability enterprise web app with a primary active region and a cold/warm standby disaster recovery (DR) region.",
      "category": "Web & Mobile Application",
      "regions": ["us-east-1", "us-west-2"],
      "components": [
        {
          "id": "r53_global_dns",
          "service": "AmazonRoute53",
          "region": "global",
          "type": "DNS",
          "description": "Global DNS with latency routing and health checks to route traffic between primary and DR regions.",
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
          "description": "CDN caching global user requests and accelerating static and dynamic web content.",
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
          "description": "Application Load Balancer (ALB) distributing incoming HTTP/HTTPS traffic to application servers in us-east-1.",
          "attributes": {
            "count": 1
          },
          "usage": {
            "lcuPerHour": 2,
            "runningHoursPerMonth": 730
          }
        },
        {
          "id": "ec2_app_primary",
          "service": "AmazonEC2",
          "region": "us-east-1",
          "type": "ComputeInstance",
          "description": "4x t4g.xlarge (ARM-based Graviton3, Linux) in Auto Scaling Groups running in primary region us-east-1.",
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
          "description": "Multi-AZ primary instance (db.r6g.xlarge) running Amazon RDS Aurora PostgreSQL in us-east-1.",
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
          "description": "2 TB Standard S3 storage bucket hosting application assets in us-east-1.",
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
          "description": "Cross-Region Replication (CRR) data transfer from primary us-east-1 bucket to DR us-west-2 bucket.",
          "attributes": {
            "sourceRegion": "us-east-1",
            "destinationRegion": "us-west-2"
          },
          "usage": {
            "dataTransferGB": 250
          }
        },
        {
          "id": "alb_secondary",
          "service": "ElasticLoadBalancing",
          "region": "us-west-2",
          "type": "ApplicationLoadBalancer",
          "description": "Standby Application Load Balancer (ALB) waiting to distribute traffic in DR region us-west-2.",
          "attributes": {
            "count": 1
          },
          "usage": {
            "lcuPerHour": 2,
            "runningHoursPerMonth": 730
          }
        },
        {
          "id": "ec2_app_secondary",
          "service": "AmazonEC2",
          "region": "us-west-2",
          "type": "ComputeInstance",
          "description": "4x t4g.xlarge (ARM-based Graviton3, Linux) in Auto Scaling Groups running in standby region us-west-2.",
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
          "id": "rds_aurora_replica",
          "service": "AmazonRDS",
          "region": "us-west-2",
          "type": "ReadReplicaInstance",
          "description": "Cross-region read-replica (db.r6g.xlarge) in us-west-2 configured for fast failover.",
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
          "description": "Secondary S3 Standard storage bucket receiving replicated assets in us-west-2.",
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
      "description": "Scalable event-driven ingestion platform for batch and real-time processing.",
      "category": "Analytics & Big Data",
      "regions": ["us-east-1"],
      "components": [
        {
          "id": "kinesis_stream",
          "service": "AmazonKinesis",
          "region": "us-east-1",
          "type": "DataStream",
          "description": "Amazon Kinesis Data Streams (4 shards) handling continuous streaming event ingestion.",
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
          "description": "Serverless Apache Spark ETL running scheduled nightly processing jobs (10 DPUs, ~2 hrs/day).",
          "attributes": {
            "workerType": "G.1X",
            "dpuCount": 10
          },
          "usage": {
            "executionHoursPerDay": 2
          }
        },
        {
          "id": "glue_catalog",
          "service": "AWSGlue",
          "region": "us-east-1",
          "type": "DataCatalog",
          "description": "AWS Glue Data Catalog storing metadata, table schemas, and partition information.",
          "attributes": {
            "objectsStored": 10000
          },
          "usage": {
            "requestsPerMonth": 1000000
          }
        },
        {
          "id": "s3_raw_zone",
          "service": "AmazonS3",
          "region": "us-east-1",
          "type": "StorageBucket",
          "description": "Raw data zone in S3 Standard storing unformatted ingested data (10 TB).",
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
          "description": "Analytics data zone in S3 Standard storing transformed, optimized Parquet files (5 TB).",
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
          "description": "Archive storage layer in S3 Glacier Instant Retrieval for long-term data preservation (50 TB).",
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
          "description": "Serverless SQL engine analyzing ad-hoc query data (~2 TB scanned per day).",
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
          "description": "Amazon Redshift Serverless with 32 base RPUs for complex analytics and business intelligence.",
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
      "description": "Cost-optimized, highly scalable API back-end with pay-per-use components.",
      "category": "Serverless & APIs",
      "regions": ["eu-west-1"],
      "components": [
        {
          "id": "cloudfront_edge",
          "service": "AmazonCloudFront",
          "region": "global",
          "type": "CDN",
          "description": "Edge CDN routing traffic to API Gateway and serving cached dynamic payload delivery.",
          "attributes": {
            "priceClass": "PriceClass_100"
          },
          "usage": {
            "dataTransferOutGB": 500,
            "requestsCount": 20000000
          }
        },
        {
          "id": "cognito_user_pools",
          "service": "AmazonCognito",
          "region": "eu-west-1",
          "type": "Authentication",
          "description": "Amazon Cognito managing user authentication and tokens for ~10,000 Monthly Active Users (MAUs).",
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
          "description": "Amazon API Gateway (HTTP APIs) handling ~20 million serverless API requests monthly.",
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
          "description": "AWS Lambda functions (ARM64, 1024 MB) executing microservice logic (~15M invocations/month, 250ms avg).",
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
          "description": "Amazon DynamoDB in On-Demand capacity mode with 50 GB storage, 5M reads, and 2M writes monthly.",
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
          "description": "Amazon SQS standard queues for decoupled, asynchronous background job processing (~10M messages/month).",
          "attributes": {},
          "usage": {
            "requestsPerMonth": 10000000
          }
        },
        {
          "id": "sns_topic",
          "service": "AmazonSNS",
          "region": "eu-west-1",
          "type": "NotificationTopic",
          "description": "Amazon SNS pub/sub topics fanning out event notifications to downstream Lambda and SQS consumers.",
          "attributes": {},
          "usage": {
            "publishRequestsPerMonth": 2000000
          }
        }
      ]
    },
    {
      "id": "arch_containerized_eks_platform",
      "name": "Containerized Microservices Platform (EKS)",
      "description": "Kubernetes-based enterprise platform hosting internal services and APIs using a hybrid compute layer (EC2 managed nodes + AWS Fargate for serverless workloads).",
      "category": "Containers & Orchestration",
      "regions": ["us-west-2"],
      "components": [
        {
          "id": "eks_control_plane",
          "service": "AmazonEKS",
          "region": "us-west-2",
          "type": "Cluster",
          "description": "Amazon EKS managed Kubernetes control plane cluster fee.",
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
          "description": "6x m6i.large managed EC2 worker nodes distributed across 3 Availability Zones.",
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
          "id": "fargate_pods",
          "service": "AWSFargate",
          "region": "us-west-2",
          "type": "ServerlessCompute",
          "description": "Serverless compute engine for running bursty or isolated EKS pods without managing EC2 instances.",
          "attributes": {
            "platform": "Linux",
            "averagePodCount": 10
          },
          "usage": {
            "vCPUPerPod": 1,
            "memoryGBPerPod": 2,
            "runningHoursPerMonth": 730
          }
        },
        {
          "id": "ecr_repository",
          "service": "AmazonECR",
          "region": "us-west-2",
          "type": "ContainerRegistry",
          "description": "Amazon Elastic Container Registry (ECR) storing 100 GB of container image artifacts.",
          "attributes": {
            "type": "PrivateRepository"
          },
          "usage": {
            "storageGB": 100
          }
        },
        {
          "id": "nlb_ingress",
          "service": "ElasticLoadBalancing",
          "region": "us-west-2",
          "type": "NetworkLoadBalancer",
          "description": "Network Load Balancer (NLB) providing high-throughput, low-latency ingress to EKS services.",
          "attributes": {
            "count": 1
          },
          "usage": {
            "lcuPerHour": 3,
            "runningHoursPerMonth": 730
          }
        },
        {
          "id": "app_mesh",
          "service": "AWSAppMesh",
          "region": "us-west-2",
          "type": "ServiceMesh",
          "description": "AWS App Mesh control plane providing application-level networking, service discovery, and traffic routing.",
          "attributes": {
            "virtualNodes": 12
          },
          "usage": {
            "activeMeshes": 1
          }
        },
        {
          "id": "elasticache_redis",
          "service": "AmazonElastiCache",
          "region": "us-west-2",
          "type": "RedisCluster",
          "description": "2-node Redis cluster (cache.m6g.large) providing low-latency session caching and fast key-value queries.",
          "attributes": {
            "nodeType": "cache.m6g.large",
            "numNodes": 2,
            "engine": "Redis"
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
          "description": "Managed Multi-AZ Amazon RDS MySQL deployment on db.m6g.xlarge with 500 GB Provisioned IOPS (gp3) storage.",
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