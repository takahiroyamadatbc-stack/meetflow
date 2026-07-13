import os
import sys
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

# Mirrors the real Lambda runtime layout: function code (result_lambda/) and
# the shared Layer (layers/common/python) are both mounted on sys.path
# (/var/task and /opt/python respectively) -- see handler.py's
# `from handlers import results` and meetflow_common's own imports.
_RESULT_LAMBDA_DIR = Path(__file__).resolve().parent.parent
_COMMON_LAYER_DIR = _RESULT_LAMBDA_DIR.parent.parent / "layers" / "common" / "python"
for _path in (_RESULT_LAMBDA_DIR, _COMMON_LAYER_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# Every domain Lambda ships its own top-level `handler`/`handlers` module(s)
# and every domain's tests/ directory has its own same-named `_factories`
# helper module. Running multiple domains' tests in one pytest session means
# whichever domain imports first gets cached in sys.modules and shadows
# every other domain's same-named module, so each domain's conftest must
# evict these before its own test modules import them.
for _name in list(sys.modules):
    if _name in ("handler", "handlers", "_factories") or _name.startswith("handlers."):
        del sys.modules[_name]

os.environ.setdefault("AWS_DEFAULT_REGION", "ap-northeast-1")
os.environ.setdefault("TABLE_NAME", "test-MeetFlowTable")


@pytest.fixture
def table():
    """Moto-backed DynamoDB table matching MeetFlowTable's key schema
    (infra/meetflow_infra/meetflow_data_stack.py): PK/SK + GSI1 (ByUser) +
    GSI2 (ByAltId). Resets meetflow_common.dynamodb's module-level table
    cache so each test gets a Table resource bound to its own mock_aws
    context instead of a stale one from a previous test.
    """
    import meetflow_common.dynamodb as dynamodb_module

    dynamodb_module._table = None
    with mock_aws():
        client = boto3.client("dynamodb", region_name=os.environ["AWS_DEFAULT_REGION"])
        client.create_table(
            TableName=os.environ["TABLE_NAME"],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
                {"AttributeName": "GSI1PK", "AttributeType": "S"},
                {"AttributeName": "GSI1SK", "AttributeType": "S"},
                {"AttributeName": "GSI2PK", "AttributeType": "S"},
                {"AttributeName": "GSI2SK", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "GSI1",
                    "KeySchema": [
                        {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                        {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "GSI2",
                    "KeySchema": [
                        {"AttributeName": "GSI2PK", "KeyType": "HASH"},
                        {"AttributeName": "GSI2SK", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield dynamodb_module.get_table()
    dynamodb_module._table = None
