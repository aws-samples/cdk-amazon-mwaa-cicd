#
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#

import os
import shutil
from aws_cdk import (
    core,
    aws_s3 as s3,
    aws_s3_deployment as s3d,
    aws_iam as iam,
    aws_codepipeline as codepipeline,
    aws_codepipeline_actions as codepipeline_actions,
    aws_codecommit as codecommit,
    aws_codebuild as codebuild,
)


class AirflowProvisioningStack(core.NestedStack):
    def __init__(
        self,
        scope: core.Construct,
        construct_id: str,
        vpc_id: str,
        cidr: str,
        mwaa_bucket: s3.Bucket,
        env=None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        code_path = os.path.realpath(
            os.path.abspath(os.path.join(__file__, "..", "..", ".."))
        )

        AirflowProvisioningStack.zip_directory(code_path)

        bucket = s3.Bucket(
            self,
            id=f"MwaaProvisioningBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=core.RemovalPolicy.DESTROY,
        )

        code_path = os.path.realpath(
            os.path.abspath(os.path.join(__file__, "..", "..", "..", "dist",))
        )

        assets = s3d.BucketDeployment(
            self,
            f"MwaaProvisioningCodeAssets",
            destination_bucket=bucket,
            cache_control=[
                s3d.CacheControl.from_string(
                    "max-age=0,no-cache,no-store,must-revalidate"
                )
            ],
            sources=[s3d.Source.asset(code_path)],
            retain_on_delete=False,
        )

        codecommitrepo = codecommit.CfnRepository(
            scope=self,
            code={
                "branch_name": "main",
                "s3": {"bucket": bucket.bucket_name, "key": "code.zip"},
            },
            id=f"MwaaProvisioningCodeCommit",
            repository_name="mwaa-provisioning",
        )
        codecommitrepo.node.add_dependency(assets)

        build_project_role = iam.Role(
            self,
            id=f"MwaaProvisioningCodeBuildRole",
            assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),
        )

        build_project_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                resources=[
                    mwaa_bucket.bucket_arn,
                    f"{mwaa_bucket.bucket_arn}/*",
                    bucket.bucket_arn,
                    f"{bucket.bucket_arn}/*",
                    "arn:aws:s3:::cdktoolkit-stagingbucket-*",
                ],
                actions=["s3:*Object", "s3:ListBucket", "s3:GetBucketLocation"],
            )
        )

        build_project_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                resources=["*"],
                actions=[
                    "iam:*Policy*",
                    "iam:ListPolicies",
                    "iam:UpdateRole*",
                    "iam:ListRole*",
                    "iam:GetRole*",
                ],
            )
        )

        build_project_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                resources=["*"],
                actions=[
                    "cloudformation:*",
                    "airflow:*",
                    "kms:*",
                    "ec2:Describe*",
                    "lambda:*",
                ],
            )
        )

        cdk_command = "cdk deploy"
        if vpc_id:
            cdk_command += f" -c vpcId={vpc_id}"
        if cidr:
            cdk_command += f" -c cidr={cidr}"

        deploy_project = codebuild.PipelineProject(
            scope=self,
            id=f"DeployMWAAStack",
            project_name=f"DeployMWAAStack",
            environment=codebuild.BuildEnvironment(
                privileged=True, build_image=codebuild.LinuxBuildImage.AMAZON_LINUX_2_3
            ),
            role=build_project_role,
            build_spec=codebuild.BuildSpec.from_object(
                dict(
                    version="0.2",
                    phases={
                        "pre_build": {
                            "commands": ["aws --version", "npm install -g aws-cdk"]
                        },
                        "build": {"commands": ["pip install .", cdk_command]},
                    },
                )
            ),
        )
        pipeline = codepipeline.Pipeline(
            scope=self,
            id=f"MWAAPipeline",
            pipeline_name="mwaa-provisioning",
            restart_execution_on_update=True,
        )
        source_artifact = codepipeline.Artifact()

        pipeline.add_stage(
            stage_name="Source",
            actions=[
                codepipeline_actions.CodeCommitSourceAction(
                    action_name="CodeCommit",
                    branch="main",
                    output=source_artifact,
                    trigger=codepipeline_actions.CodeCommitTrigger.POLL,
                    repository=codecommit.Repository.from_repository_name(
                        self,
                        f"MwaaSourceRepo",
                        repository_name=codecommitrepo.repository_name,
                    ),
                )
            ],
        )

        pipeline.add_stage(
            stage_name="UpdateMWAAEnvironment",
            actions=[
                codepipeline_actions.CodeBuildAction(
                    action_name="UpdateMWAAEnvironment",
                    input=source_artifact,
                    project=deploy_project,
                    outputs=[codepipeline.Artifact()],
                )
            ],
        )

    @staticmethod
    def zip_directory(path):
        try:

            dist_dir = os.path.join(path, "dist")
            shutil.copytree(
                path,
                dist_dir,
                ignore=shutil.ignore_patterns(".*", "__pycache__", "cdk.out", "dist"),
            )
            shutil.make_archive(f"code", "zip", dist_dir)
            shutil.move("code.zip", f"{dist_dir}/code.zip")
        except Exception as e:
            print(f"Failed to zip repository due to: {e}")
