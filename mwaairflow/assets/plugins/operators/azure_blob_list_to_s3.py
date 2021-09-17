#
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#

import tempfile
from typing import Optional, Sequence, Union

from airflow.models import BaseOperator
from airflow.contrib.hooks.wasb_hook import WasbHook
from airflow.hooks.S3_hook import S3Hook

from airflow.utils.decorators import apply_defaults


class AzureBlobStorageListToS3Operator(BaseOperator):
    """
    Operator transfers a list of blobs from Azure Blob Storage to specified bucket in Amazon S3
    .. seealso::
        For more information on how to use this operator, take a look at the guide:
        :ref:`howto/operator:AzureBlobStorageToS3Operator`
    :param wasb_conn_id: Reference to the wasb connection. Default is wasb_default.
    :type wasb_conn_id: str
    :param aws_conn_id: The connection ID to use when fetching connection info. Default is aws_default.
    :type aws_conn_id: str
    :param blob_list_path_file: Path to the file that has the list of blobs with size on csv format. Ex: path,size
    :type blob_list_path_file: str
    :param container_name: Name of the container
    :type container_name: str
    :param bucket_name: The bucket to upload to
    :type bucket_name: str
    :param gzip: If True, the file will be compressed locally. Default is False.
    :type gzip: bool
    :param replace: A flag to decide whether or not to overwrite the key
            if it already exists. If replace is False and the key exists, an
            error will be raised. Default is False.
    :type replace: bool
    :param encrypt: If True, the file will be encrypted on the server-side
            by S3 and will be stored in an encrypted form while at rest in S3. Default is False.
    :type encrypt: bool
    :param acl_policy: String specifying the canned ACL policy for the file being
            uploaded to the S3 bucket. Default is None.
    :type acl_policy: str
    :param s3_prefix: Option to upload data on a prefix in your Amazon S3 Bucket. Default is ''.
    :type s3_prefix: str
    """

    @apply_defaults
    def __init__(
        self,
        *,
        wasb_conn_id: str = "wasb_default",
        aws_conn_id: str = "aws_default",
        blob_list_path_file: str,
        container_name: str,
        bucket_name: str,
        gzip: bool = False,
        replace: bool = False,
        encrypt: bool = False,
        acl_policy: str = None,
        s3_prefix: str = "",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.wasb_conn_id = wasb_conn_id
        self.aws_conn_id = aws_conn_id
        self.blob_list_path_file = blob_list_path_file
        self.container_name = container_name
        self.bucket_name = bucket_name
        self.gzip = gzip
        self.replace = replace
        self.encrypt = encrypt
        self.acl_policy = acl_policy
        self.s3_prefix = s3_prefix

    template_fields = (
        "blob_list_path_file",
        "container_name",
        "bucket_name",
    )

    def execute(self, context: dict) -> str:
        azure_hook = WasbHook(wasb_conn_id=self.wasb_conn_id)
        s3_hook = S3Hook(aws_conn_id=self.aws_conn_id)
        print("Listing blob from: %s", self.blob_list_path_file)

        s3_list = []

        with open(self.blob_list_path_file, "r") as f:
            for blob in f:
                blob = blob.rstrip("\n")
                blob_name = blob.split(",")[0]
                s3_object_key_no_prefix = blob.split(",")[1]
                blob_size = int(blob.split(",")[2])

                print("blob_name: %s", blob_name)

                with tempfile.NamedTemporaryFile() as temp_file:
                    self.log.info(
                        "Downloading data from container: %s and blob: %s on temp_file: %s",
                        self.container_name,
                        blob_name,
                        temp_file.name,
                    )

                    azure_hook.get_file(
                        file_path=temp_file.name,
                        container_name=self.container_name,
                        blob_name=blob_name,
                    )

                    s3_object_key = self.s3_prefix + s3_object_key_no_prefix

                    upload_or_replace = False

                    if s3_hook.check_for_key(
                        key=s3_object_key, bucket_name=self.bucket_name
                    ):
                        s3_object_size = s3_hook.get_key(
                            key=s3_object_key, bucket_name=self.bucket_name
                        ).content_length
                        self.log.info(
                            "Object exists on s3 on bucket_name: %s and key: %s with size: %s ",
                            self.bucket_name,
                            s3_object_key,
                            s3_object_size,
                        )

                        if blob_size != s3_object_size:
                            upload_or_replace = True
                            self.log.info(
                                "Object does not have the same size on Amazon S3 than on Azure Blob Storage."
                            )
                        else:
                            self.log.info(
                                "Object has the same size on Amazon S3 than on Azure Blob Storage. Upload to Amazon S3 will be discarded"
                            )
                    else:
                        self.log.info(
                            "Object doesn't exists on s3 on bucket_name: %s and key: %s ",
                            self.bucket_name,
                            s3_object_key,
                        )
                        upload_or_replace = True

                    if upload_or_replace:
                        self.log.info(
                            "Uploading data from blob's: %s into Amazon S3 bucket: %s",
                            s3_object_key,
                            self.bucket_name,
                        )
                        s3_hook.load_file(
                            filename=temp_file.name,
                            key=s3_object_key,
                            bucket_name=self.bucket_name,
                            replace=self.replace,
                            encrypt=self.encrypt,
                            gzip=self.gzip,
                            acl_policy=self.acl_policy,
                        )
                        self.log.info(
                            "Resources have been uploaded from blob: %s to Amazon S3 bucket:%s",
                            s3_object_key,
                            self.bucket_name,
                        )
                        s3_list.append(f"s3://{self.bucket_name}/{s3_object_key}")
        return s3_list
