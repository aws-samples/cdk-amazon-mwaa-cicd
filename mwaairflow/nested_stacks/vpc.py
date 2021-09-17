#
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#

from aws_cdk import core, aws_ec2 as ec2


class VpcStack(core.NestedStack):
    def __init__(
        self, scope: core.Construct, construct_id: str, cidr=None, env=None, **kwargs
    ):
        super().__init__(scope, construct_id, **kwargs)
        self.vpc = ec2.Vpc(
            self,
            "VPC",
            max_azs=2,
            cidr=cidr or "172.31.0.0/16",
            # configuration will create 3 groups in 2 AZs = 6 subnets.
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    subnet_type=ec2.SubnetType.PUBLIC, name="Public", cidr_mask=20
                ),
                ec2.SubnetConfiguration(
                    subnet_type=ec2.SubnetType.PRIVATE, name="Private", cidr_mask=24
                ),
            ],
            nat_gateways=1,
        )
