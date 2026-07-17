import os
import sys
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

# 実際のLambdaランタイムのレイアウトを再現している: 関数コード
# (feedback_lambda/)と共有Layer(layers/common/python)は両方ともsys.pathに
# マウントされる(それぞれ/var/taskと/opt/python) -- handler.pyの
# `from handlers import announcements, attachments, feedback`や
# meetflow_common自身のimportを参照。
_FEEDBACK_LAMBDA_DIR = Path(__file__).resolve().parent.parent
_COMMON_LAYER_DIR = _FEEDBACK_LAMBDA_DIR.parent.parent / "layers" / "common" / "python"
for _path in (_FEEDBACK_LAMBDA_DIR, _COMMON_LAYER_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# 各ドメインLambdaはそれぞれ独自のトップレベル`handlers`パッケージを持つ
# (実際のLambdaのレイアウトを反映しており、そこでは常に1つの関数のコード
# ディレクトリのみがsys.path上に存在する)。また各ドメインのtests/
# ディレクトリも同名の`_factories`ヘルパーモジュールを持つ。複数ドメインの
# テストを1つのpytestセッションで実行すると、最初にimportされたドメインが
# sys.modulesにキャッシュされ、他の全ドメインの同名モジュールを覆い隠して
# しまう。そのため各ドメインのconftestは、自分のテストモジュールがこれらを
# importする前に退避させておく必要がある。
for _name in list(sys.modules):
    if _name in ("handlers", "_factories") or _name.startswith("handlers."):
        del sys.modules[_name]

os.environ.setdefault("AWS_DEFAULT_REGION", "ap-northeast-1")
os.environ.setdefault("TABLE_NAME", "test-MeetFlowTable")
os.environ.setdefault(
    "FEEDBACK_ATTACHMENTS_BUCKET_NAME", "test-meetflow-feedback-attachments"
)


@pytest.fixture
def table():
    """MeetFlowTableのキースキーマ(infra/meetflow_infra/
    meetflow_data_stack.py)に合わせたmoto製DynamoDBテーブル: PK/SK +
    GSI1(ByUser) + GSI2(ByAltId)。meetflow_common.dynamodbのモジュール
    レベルのtableキャッシュをリセットすることで、各テストが前のテストの
    古いものではなく、自分のmock_awsコンテキストに紐づいたTable resourceを
    取得できるようにする。
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
