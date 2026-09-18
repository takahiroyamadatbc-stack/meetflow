import os
import sys
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

# 実際のLambdaランタイムのレイアウトを再現している: 関数コード
# （draft_lambda/）と共有Layer（layers/common/python）は両方とも
# sys.pathにマウントされる（それぞれ/var/taskと/opt/python）。
#
# **handlers/ 自体はsys.pathに入れない。** 入れるとhandlers配下のモジュールが
# トップレベル名としても見えてしまい、Lambdaでは解決できない相互import
# （`import repository`のような形）がテストでだけ通ってしまう。
# handlers内の相互参照は他ドメインと同じく相対import（`from . import ...`）にする。
_DRAFT_LAMBDA_DIR = Path(__file__).resolve().parent.parent
_COMMON_LAYER_DIR = _DRAFT_LAMBDA_DIR.parent.parent / "layers" / "common" / "python"
for _path in (_DRAFT_LAMBDA_DIR, _COMMON_LAYER_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# 各ドメインLambdaは同名のトップレベル`handler`/`handlers`/`_factories`
# モジュールを持つため、複数ドメインを1セッションで実行すると最初にimport
# されたものがsys.modulesに居座って他を覆い隠す（他ドメインのconftestと同じ対策）。
for _name in list(sys.modules):
    if _name in (
        "handler",
        "handlers",
        "_factories",
        # draft_lambdaのルート直下にある固有モジュール。他ドメインには
        # 同名が無いが、退避しておかないとテスト間で古いものが残る。
        "errors",
        "draft_table",
    ) or _name.startswith("handlers."):
        del sys.modules[_name]

os.environ.setdefault("AWS_DEFAULT_REGION", "ap-northeast-1")
os.environ.setdefault("TABLE_NAME", "test-MeetFlowTable")
os.environ.setdefault("DRAFT_TABLE_NAME", "test-MeetFlowDraftTable")

_KEY_SCHEMA = [
    {"AttributeName": "PK", "KeyType": "HASH"},
    {"AttributeName": "SK", "KeyType": "RANGE"},
]
_ATTRS = [
    {"AttributeName": "PK", "AttributeType": "S"},
    {"AttributeName": "SK", "AttributeType": "S"},
    {"AttributeName": "GSI1PK", "AttributeType": "S"},
    {"AttributeName": "GSI1SK", "AttributeType": "S"},
]
_GSI1 = {
    "IndexName": "GSI1",
    "KeySchema": [
        {"AttributeName": "GSI1PK", "KeyType": "HASH"},
        {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
    ],
    "Projection": {"ProjectionType": "ALL"},
}


@pytest.fixture
def tables():
    """本体テーブルとDraftTableの2つを立てる。

    DraftLambdaはドラフトのデータをDraftTable（専用）に書き、本体テーブルは
    Membership/User参照のために読むだけ（DESIGN.md §4.11 / §4.13）。
    テストでもその2本立てをそのまま再現する。
    """
    import meetflow_common.dynamodb as main_dynamodb

    import draft_table as draft_dynamodb

    main_dynamodb._table = None
    draft_dynamodb._draft_table = None
    with mock_aws():
        client = boto3.client("dynamodb", region_name=os.environ["AWS_DEFAULT_REGION"])
        client.create_table(
            TableName=os.environ["TABLE_NAME"],
            AttributeDefinitions=_ATTRS
            + [
                {"AttributeName": "GSI2PK", "AttributeType": "S"},
                {"AttributeName": "GSI2SK", "AttributeType": "S"},
            ],
            KeySchema=_KEY_SCHEMA,
            GlobalSecondaryIndexes=[
                _GSI1,
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
        client.create_table(
            TableName=os.environ["DRAFT_TABLE_NAME"],
            AttributeDefinitions=_ATTRS,
            KeySchema=_KEY_SCHEMA,
            GlobalSecondaryIndexes=[_GSI1],
            BillingMode="PAY_PER_REQUEST",
        )
        yield main_dynamodb.get_table(), draft_dynamodb.get_draft_table()
    main_dynamodb._table = None
    draft_dynamodb._draft_table = None


@pytest.fixture
def main_table(tables):
    return tables[0]


@pytest.fixture
def draft_table(tables):
    return tables[1]
