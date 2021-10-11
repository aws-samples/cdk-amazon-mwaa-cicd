# a Dag using the SalesForceToS3 operator to extract the last 6 months of the SalesForce Opportunity Object
# Prerequisites :
# - an S3 bucket as target
# - a Salesforce account
# - create an Airflow Aws connection with name "aws_connection"
# - create an Airflow HTTP/Salesforce connection with name "salesforce_connection"
# - create an Airflow Variable "bucket_name" with the name of the S3 bucket as value

from datetime import datetime, timedelta

from airflow import DAG
from airflow.utils.dates import days_ago
from airflow.providers.amazon.aws.operators.s3_list import S3ListOperator
from airflow.models import Variable
from operators.salesforce_to_s3_operator import SalesforceToS3Operator


# These args will get passed on to each operator
# You can override them on a per-task basis during operator initialization
default_args = {
    "owner": "user@example.com",
    "depends_on_past": False,
    "is_paused_upon_creation": True,
    "start_date": days_ago(1),
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
    "s3_bucket": Variable.get("bucket_name"),
    "sf_conn_id": "salesforce_connection",
    "s3_conn_id": "aws_connection",
}


# Definition of the dag
salesforce_to_s3_dag = DAG(
    "salesforce_to_s3",
    default_args=default_args,
    description="Ingest SalesForce Opportunities to S3",
    schedule_interval=timedelta(days=1),
    catchup=False,
)


# Definition of variables that will be used by the operators : exec date, date range for filtering, Saleforce object and fields
exec_date = "{{ execution_date }}"

# name of the Salesforce objet to import
table = "Opportunity"
# list of the Salesforce field to import
fields = ["id", "isdeleted", "accountid", "name", "stagename", "amount"]
# number of months to import
nb_months = 6
# Output format
output_format = "csv"


# Operator to get the list of result files on S3 in a xcom variable
list_s3_files = S3ListOperator(
    task_id="list_s3_files",
    bucket=default_args["s3_bucket"],
    prefix=f"{table.lower()}/raw/dt={exec_date}/",
    delimiter="/",
    aws_conn_id=default_args["s3_conn_id"],
    dag=salesforce_to_s3_dag,
)

# Python Operator to print, in the airflow task log, the list of files
@salesforce_to_s3_dag.task(task_id="print_objects")
def print_objects(objects):
    print(objects)


# creation of SalesForcetoS3 task for each batch/month
for batch in range(nb_months):
    from_date = f"LAST_N_MONTHS:{batch + 1}"
    to_date = f"LAST_N_MONTHS:{batch}"

    if batch == 0:
        to_date = "TODAY"

    salesforce_to_s3 = SalesforceToS3Operator(
        task_id=f"{table}_to_S3_batch_{batch}",
        sf_conn_id=default_args["sf_conn_id"],
        sf_obj=table,
        sf_fields=fields,
        fmt=output_format,
        from_date=from_date,
        to_date=to_date,
        s3_conn_id=default_args["s3_conn_id"],
        s3_bucket=default_args["s3_bucket"],
        s3_key=f"{table.lower()}/raw/dt={exec_date}/{table.lower()}_from_{from_date}_to_{to_date}.csv",
        dag=salesforce_to_s3_dag,
    )
    salesforce_to_s3 >> list_s3_files

list_s3_files >> print_objects(list_s3_files.output)
