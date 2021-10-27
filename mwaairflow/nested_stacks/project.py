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


class AirflowProjectStack(core.NestedStack):
    def __init__(
        self,
        scope: core.Construct,
        construct_id: str,
        mwaa_bucket: s3.Bucket,
        env=None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.package_name = "mwaaproject"

        code_path = os.path.realpath(
            os.path.abspath(os.path.join(__file__, "..", "..", "project"))
        )
        AirflowProjectStack.zip_directory(code_path)

        bucket = s3.Bucket(
            self,
            id=f"{self.package_name}MwaaProjectBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=core.RemovalPolicy.DESTROY,
        )

        assets = s3d.BucketDeployment(
            self,
            f"{self.package_name}MwaaProjectCodeAssets",
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
            id=f"{self.package_name}CodeCommit",
            repository_name=self.package_name,
        )
        codecommitrepo.node.add_dependency(assets)

        build_project_role = iam.Role(
            self,
            id=f"{self.package_name}CodeBuildRole",
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
                ],
                actions=["s3:*Object", "s3:ListBucket", "s3:GetBucketLocation"],
            )
        )

        deploy_project = codebuild.PipelineProject(
            scope=self,
            id=f"{self.package_name}DeployToMWAABucket",
            project_name=f"{self.package_name}-DeployToMWAABucket",
            environment=codebuild.BuildEnvironment(
                privileged=True, build_image=codebuild.LinuxBuildImage.AMAZON_LINUX_2_3
            ),
            environment_variables={
                "BUCKET_NAME": codebuild.BuildEnvironmentVariable(
                    value=mwaa_bucket.bucket_name
                ),
            },
            role=build_project_role,
            build_spec=codebuild.BuildSpec.from_object(
                dict(
                    version="0.2",
                    phases={
                        "pre_build": {"commands": ["aws --version"]},
                        "build": {"commands": ["make deploy bucket-name=$BUCKET_NAME"]},
                    },
                )
            ),
        )
        pipeline = codepipeline.Pipeline(
            scope=self,
            id=f"{self.package_name}Pipeline",
            pipeline_name=f"{self.package_name}-pipeline",
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
                        f"{self.package_name}SourceRepo",
                        repository_name=codecommitrepo.repository_name,
                    ),
                )
            ],
        )

        pipeline.add_stage(
            stage_name="Package",
            actions=[
                codepipeline_actions.CodeBuildAction(
                    action_name="Build",
                    input=source_artifact,
                    project=codebuild.PipelineProject(
                        scope=self,
                        id=f"{self.package_name}-build-project",
                        project_name=f"{self.package_name}-build-project",
                        environment=codebuild.BuildEnvironment(
                            privileged=True,
                            build_image=codebuild.LinuxBuildImage.AMAZON_LINUX_2_3,
                        ),
                        role=build_project_role,
                        build_spec=codebuild.BuildSpec.from_object(
                            dict(
                                version="0.2",
                                phases={
                                    "pre_build": {"commands": ["aws --version"]},
                                    "build": {
                                        "commands": [
                                            "pip install poetry",
                                            "make install",
                                        ]
                                    },
                                },
                            )
                        ),
                    ),
                    outputs=[codepipeline.Artifact()],
                ),
                codepipeline_actions.CodeBuildAction(
                    action_name="Lint",
                    input=source_artifact,
                    project=codebuild.PipelineProject(
                        scope=self,
                        id=f"{self.package_name}-lint-project",
                        project_name=f"{self.package_name}-lint-project",
                        environment=codebuild.BuildEnvironment(
                            privileged=True,
                            build_image=codebuild.LinuxBuildImage.AMAZON_LINUX_2_3,
                        ),
                        role=build_project_role,
                        build_spec=codebuild.BuildSpec.from_object(
                            dict(
                                version="0.2",
                                phases={
                                    "pre_build": {"commands": ["aws --version"]},
                                    "build": {
                                        "commands": [
                                            "pip install poetry",
                                            "make install",
                                            "make check-safety",
                                            "make check-style",
                                        ]
                                    },
                                },
                            )
                        ),
                    ),
                    outputs=[codepipeline.Artifact()],
                ),
                codepipeline_actions.CodeBuildAction(
                    action_name="Test",
                    input=source_artifact,
                    project=codebuild.PipelineProject(
                        scope=self,
                        id=f"{self.package_name}-test-project",
                        project_name=f"{self.package_name}-test-project",
                        environment=codebuild.BuildEnvironment(
                            privileged=True,
                            build_image=codebuild.LinuxBuildImage.AMAZON_LINUX_2_3,
                        ),
                        role=build_project_role,
                        build_spec=codebuild.BuildSpec.from_object(
                            dict(
                                version="0.2",
                                phases={
                                    "pre_build": {"commands": ["aws --version"]},
                                    "build": {
                                        "commands": [
                                            "pip install poetry",
                                            "make install",
                                            "make test",
                                        ]
                                    },
                                },
                            )
                        ),
                    ),
                    outputs=[codepipeline.Artifact()],
                ),
            ],
        )

        pipeline.add_stage(
            stage_name="DeployToAirflowBucket",
            actions=[
                codepipeline_actions.CodeBuildAction(
                    action_name="DeployToAirflowBucket",
                    input=source_artifact,
                    project=deploy_project,
                    outputs=[codepipeline.Artifact()],
                )
            ],
        )

    @staticmethod
    def zip_directory(path):
        try:
            shutil.make_archive(f"code", "zip", path)
            shutil.move("code.zip", f"{path}/code.zip")
        except Exception as e:
            print(f"Failed to zip repository due to: {e}")
