import json
import pytest

from aws_cdk import core
from mwaairflow.mwaairflow_stack import MwaairflowStack


def get_template():
    app = core.App()
    MwaairflowStack(app, "mwaairflow")
    return json.dumps(app.synth().get_stack("mwaairflow").template)


def test_sqs_queue_created():
    assert "AWS::SQS::Queue" in get_template()


def test_sns_topic_created():
    assert "AWS::SNS::Topic" in get_template()
