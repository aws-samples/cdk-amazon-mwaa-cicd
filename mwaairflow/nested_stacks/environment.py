#
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#

import os
import zipfile
import json

from aws_cdk import (
    core,
    aws_iam as iam,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_mwaa as mwaa,
    aws_ec2 as ec2,
)


class AirflowEnvironmentStack(core.NestedStack):
    def _zip_dir(self, dir_path, zip_path):
        zipf = zipfile.ZipFile(zip_path, mode="w")
        lendir_path = len(dir_path)
        for root, _, files in os.walk(dir_path):
            for file in files:
                file_path = os.path.join(root, file)
                zipf.write(file_path, file_path[lendir_path:])
        zipf.close()

    def __init__(
        self,
        scope: core.Construct,
        construct_id: str,
        vpc: ec2.IVpc,
        subnet_ids_list: str,
        env_name: str,
        env_tags: str,
        env_class: str,
        max_workers: int,
        access_mode: str,
        secrets_backend: str,
        env=None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name

        # Create S3 bucket for MWAA
        self.bucket = s3.Bucket(
            self,
            "MwaaBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=True,
        )
        core.CfnOutput(self, "MWAA_BUCKET", value=self.bucket.bucket_name)

        # Create MWAA role
        role = iam.Role(
            self,
            "MWAARole",
            assumed_by=iam.ServicePrincipal("airflow-env.amazonaws.com"),
        )
        role.add_to_policy(
            iam.PolicyStatement(
                resources=[
                    f"arn:aws:airflow:{self.region}:{self.account}:environment/{self.env_name}"
                ],
                actions=["airflow:PublishMetrics"],
                effect=iam.Effect.ALLOW,
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                resources=[
                    f"arn:aws:s3:::{self.bucket.bucket_name}",
                    f"arn:aws:s3:::{self.bucket.bucket_name}/*",
                ],
                actions=["s3:ListAllMyBuckets"],
                effect=iam.Effect.DENY,
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                resources=[
                    f"arn:aws:s3:::{self.bucket.bucket_name}",
                    f"arn:aws:s3:::{self.bucket.bucket_name}/*",
                ],
                actions=["s3:GetObject*", "s3:GetBucket*", "s3:List*"],
                effect=iam.Effect.ALLOW,
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                resources=[
                    f"arn:aws:logs:{self.region}:{self.account}:log-group:airflow-{self.env_name}-*"
                ],
                actions=[
                    "logs:CreateLogStream",
                    "logs:CreateLogGroup",
                    "logs:PutLogEvents",
                    "logs:GetLogEvents",
                    "logs:GetLogRecord",
                    "logs:GetLogGroupFields",
                    "logs:GetQueryResults",
                    "logs:DescribeLogGroups",
                ],
                effect=iam.Effect.ALLOW,
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                resources=["*"],
                actions=["cloudwatch:PutMetricData"],
                effect=iam.Effect.ALLOW,
            )
        )

        role.add_to_policy(
            iam.PolicyStatement(
                resources=["*"], actions=["sts:AssumeRole"], effect=iam.Effect.ALLOW,
            )
        )

        role.add_to_policy(
            iam.PolicyStatement(
                resources=[f"arn:aws:sqs:{self.region}:*:airflow-celery-*"],
                actions=[
                    "sqs:ChangeMessageVisibility",
                    "sqs:DeleteMessage",
                    "sqs:GetQueueAttributes",
                    "sqs:GetQueueUrl",
                    "sqs:ReceiveMessage",
                    "sqs:SendMessage",
                ],
                effect=iam.Effect.ALLOW,
            )
        )

        if secrets_backend == "SecretsManager":
            role.add_to_policy(
                iam.PolicyStatement(
                    resources=[
                        "arn:aws:secretsmanager:*:*:airflow/connections/*",
                        "arn:aws:secretsmanager:*:*:airflow/variables/*",
                    ],
                    actions=[
                        "secretsmanager:DescribeSecret",
                        "secretsmanager:PutSecretValue",
                        "secretsmanager:CreateSecret",
                        "secretsmanager:DeleteSecret",
                        "secretsmanager:CancelRotateSecret",
                        "secretsmanager:ListSecretVersionIds",
                        "secretsmanager:UpdateSecret",
                        "secretsmanager:GetRandomPassword",
                        "secretsmanager:GetResourcePolicy",
                        "secretsmanager:GetSecretValue",
                        "secretsmanager:StopReplicationToReplica",
                        "secretsmanager:ReplicateSecretToRegions",
                        "secretsmanager:RestoreSecret",
                        "secretsmanager:RotateSecret",
                        "secretsmanager:UpdateSecretVersionStage",
                        "secretsmanager:RemoveRegionsFromReplication",
                        "secretsmanager:ListSecrets",
                    ],
                    effect=iam.Effect.ALLOW,
                )
            )

        string_like = core.CfnJson(
            self,
            "ConditionJson",
            value={f"kms:ViaService": f"sqs.{self.region}.amazonaws.com"},
        )
        role.add_to_policy(
            iam.PolicyStatement(
                not_resources=[f"arn:aws:kms:*:{self.account}:key/*"],
                actions=[
                    "kms:Decrypt",
                    "kms:DescribeKey",
                    "kms:GenerateDataKey*",
                    "kms:Encrypt",
                ],
                effect=iam.Effect.ALLOW,
                conditions={"StringLike": string_like},
            )
        )

        # Create MWAA user policy
        managed_policy = iam.ManagedPolicy(
            self,
            "cdh-mwaa-user",
            managed_policy_name="cdh-mwaa-user",
            statements=[
                iam.PolicyStatement(
                    resources=[
                        f"arn:aws:airflow:{self.region}:{self.account}:role/{self.env_name}/Op"
                    ],
                    actions=["airflow:CreateWebLoginToken"],
                    effect=iam.Effect.ALLOW,
                ),
                iam.PolicyStatement(
                    resources=[
                        f"arn:aws:airflow:{self.region}:{self.account}:environment/{self.env_name}"
                    ],
                    actions=["airflow:GetEnvironment"],
                    effect=iam.Effect.ALLOW,
                ),
                iam.PolicyStatement(
                    resources=["*"],
                    actions=["airflow:ListEnvironments"],
                    effect=iam.Effect.ALLOW,
                ),
                iam.PolicyStatement(
                    resources=[f"arn:aws:s3:::{self.bucket.bucket_name}/dags/*",],
                    actions=["s3:PutObject"],
                    effect=iam.Effect.ALLOW,
                ),
                iam.PolicyStatement(
                    resources=[
                        f"arn:aws:dynamodb:{self.region}:{self.account}:table/TrainingLab11"
                    ],
                    actions=["dynamodb:Scan"],
                    effect=iam.Effect.ALLOW,
                ),
            ],
        )

        plugins_zip = "./mwaairflow/assets/plugins.zip"
        plugins_path = "./mwaairflow/assets/plugins"
        self._zip_dir(plugins_path, plugins_zip)

        # Upload MWAA pre-reqs
        plugins_deploy = s3deploy.BucketDeployment(
            self,
            "DeployPlugin",
            sources=[
                s3deploy.Source.asset(
                    "./mwaairflow/assets", exclude=["**", "!plugins.zip"],
                )
            ],
            destination_bucket=self.bucket,
            destination_key_prefix="plugins",
            retain_on_delete=False,
        )
        req_deploy = s3deploy.BucketDeployment(
            self,
            "DeployReq",
            sources=[
                s3deploy.Source.asset(
                    "./mwaairflow/assets", exclude=["**", "!requirements.txt"]
                )
            ],
            destination_bucket=self.bucket,
            destination_key_prefix="requirements",
            retain_on_delete=False,
        )

        # Create security group
        mwaa_sg = ec2.SecurityGroup(
            self,
            "SecurityGroup",
            vpc=vpc,
            description="Allow inbound access to MWAA",
            allow_all_outbound=True,
        )
        mwaa_sg.add_ingress_rule(
            mwaa_sg, ec2.Port.all_traffic(), "allow inbound access from the SG"
        )

        # Get private subnets
        subnet_ids = self.get_subnet_ids(vpc, subnet_ids_list)
        if env_tags:
            env_tags = json.loads(env_tags)

        mwaa_env = mwaa.CfnEnvironment(
            self,
            f"MWAAEnv{self.env_name}",
            name=self.env_name,
            dag_s3_path="dags",
            airflow_version="2.0.2",
            environment_class=env_class,
            max_workers=max_workers,
            execution_role_arn=role.role_arn,
            logging_configuration=mwaa.CfnEnvironment.LoggingConfigurationProperty(
                dag_processing_logs=mwaa.CfnEnvironment.ModuleLoggingConfigurationProperty(
                    enabled=True, log_level="INFO"
                ),
                scheduler_logs=mwaa.CfnEnvironment.ModuleLoggingConfigurationProperty(
                    enabled=True, log_level="INFO"
                ),
                task_logs=mwaa.CfnEnvironment.ModuleLoggingConfigurationProperty(
                    enabled=True, log_level="INFO"
                ),
                webserver_logs=mwaa.CfnEnvironment.ModuleLoggingConfigurationProperty(
                    enabled=True, log_level="INFO"
                ),
                worker_logs=mwaa.CfnEnvironment.ModuleLoggingConfigurationProperty(
                    enabled=True, log_level="INFO"
                ),
            ),
            network_configuration=mwaa.CfnEnvironment.NetworkConfigurationProperty(
                security_group_ids=[mwaa_sg.security_group_id], subnet_ids=subnet_ids
            ),
            plugins_s3_path="plugins/plugins.zip",
            requirements_s3_path="requirements/requirements.txt",
            source_bucket_arn=self.bucket.bucket_arn,
            webserver_access_mode=access_mode,
        )
        if secrets_backend == "SecretsManager":
            options = {
                "secrets.backend": "airflow.contrib.secrets.aws_secrets_manager.SecretsManagerBackend",
                "secrets.backend_kwargs": '{"connections_prefix" : "airflow/connections", "variables_prefix" : "airflow/variables"}',
            }
            mwaa_env.add_override("Properties.AirflowConfigurationOptions", options)
        mwaa_env.add_override("Properties.Tags", env_tags)
        mwaa_env.node.add_dependency(self.bucket)
        mwaa_env.node.add_dependency(plugins_deploy)
        mwaa_env.node.add_dependency(req_deploy)
        core.CfnOutput(self, "MWAA_NAME", value=self.env_name)
        core.CfnOutput(
            self, "cdh-user-custom-policy", value=managed_policy.managed_policy_arn
        )

    @classmethod
    def get_subnet_ids(cls, vpc, subnet_ids_list):
        if not subnet_ids_list:
            subnet_ids = []
            subnets = vpc.select_subnets(subnet_type=ec2.SubnetType.PRIVATE).subnets
            first_subnet = subnets[0]
            subnet_ids.append(first_subnet.subnet_id)
            for s in subnets:
                if s.availability_zone != first_subnet.availability_zone:
                    subnet_ids.append(s.subnet_id)
                    break
        else:
            subnet_ids = list(subnet_ids_list.split(","))

        return subnet_ids
