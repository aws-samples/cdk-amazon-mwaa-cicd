# MWAA DAGs Samples

This repository includes the following sample DAGs:

## Salesforce to S3 DAG

### Purpose
A sample Dag using the SalesforceToS3Operator using "batch" mode and field selection.
This dag imports, in the target s3 bucket, the last 6 months of the opportunity object generating one file per month.
It also filters the columns, keeping only the following ones: 'id', 'isdeleted', 'accountid', 'name', 'stagename', 'amount'

### Prerequisites 

Before using this dag, you must have:
* an operational airflow environment (by using the provided cdk construct)
* a target s3 bucket
* An Airflow HTTP/Salesforce connection with name "salesforce_connection"
* An Airflow AWS connection with name "aws_connection" (the AWS role associated with the connection will need to have access to the target S3 Bucket).
* A Variable with name "bucket_name" with the name of the target S3 bucket as value.

### Source file 
salesforce_to_s3.py 






