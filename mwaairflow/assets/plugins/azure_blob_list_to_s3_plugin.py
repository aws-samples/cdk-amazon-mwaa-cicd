#
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#

from airflow.plugins_manager import AirflowPlugin
from operators.azure_blob_list_to_s3 import AzureBlobStorageListToS3Operator


class AzureBlobStorageListToS3Plugin(AirflowPlugin):
    name = "AzureBlobStorageListToS3Operator"
    operators = [AzureBlobStorageListToS3Operator]
