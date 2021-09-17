#
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#

from airflow.plugins_manager import AirflowPlugin
from operators.salesforce_to_s3_operator import SalesforceBulkQueryToS3Operator
from operators.salesforce_to_s3_operator import SalesforceToS3Operator


class SalesforceToS3Plugin(AirflowPlugin):
    name = "SalesforceToS3Plugin"
    hooks = []
    operators = [SalesforceToS3Operator, SalesforceBulkQueryToS3Operator]
    executors = []
    macros = []
    admin_views = []
    flask_blueprints = []
    menu_links = []
