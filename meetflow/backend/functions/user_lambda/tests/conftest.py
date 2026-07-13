import os
import sys
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

# 実際のLambdaランタイムのレイアウトを再現している: 関数コード
# （user_lambda/）と共有Layer（layers/common/python）は、どちらも
# sys.pathにマウントされる（それぞれ/var/taskと/opt/pythonに相当）。
# UserLambdaにはhandlers/パッケージが無く（handler.pyが
# _get_profile/_update_profile/_handle_post_confirmationを直接実装している）、
# そのためテストは`from handlers import X`ではなく`handler`モジュール
# 自体をimportする。
_USER_LAMBDA_DIR = Path(__file__).resolve().parent.parent
_COMMON_LAYER_DIR = _USER_LAMBDA_DIR.parent.parent / "layers" / "common" / "python"
for _path in (_USER_LAMBDA_DIR, _COMMON_LAYER_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# 各ドメインLambdaはそれぞれ独自のトップレベル`handler`/`handlers`モジュールを
# 持ち、各ドメインのtests/ディレクトリもそれぞれ同名の`_factories`ヘルパー
# モジュールを持つ。複数ドメインのテストを1つのpytestセッションで実行すると、
# 最初にimportされたドメインのものがsys.modulesにキャッシュされ、他の全
# ドメインの同名モジュールを覆い隠してしまう。そのため各ドメインのconftestは、
# 自分自身のテストモジュールがこれらをimportする前に、これらを退避
# （sys.modulesから削除）しておく必要がある。
for _name in list(sys.modules):
    if _name in ("handler", "handlers", "_factories") or _name.startswith("handlers."):
        del sys.modules[_name]

os.environ.setdefault("AWS_DEFAULT_REGION", "ap-northeast-1")
os.environ.setdefault("TABLE_NAME", "test-MeetFlowTable")


@pytest.fixture
def table():
    """MeetFlowTableのキースキーマ（infra/meetflow_infra/
    meetflow_data_stack.py）に一致する、moto上のDynamoDBテーブル: PK/SK +
    GSI1（ByUser）+ GSI2（ByAltId）。各テストが前のテストの古いTable
    リソースではなく、自分自身のmock_awsコンテキストに紐づいたTable
    リソースを得られるよう、meetflow_common.dynamodbのモジュールレベルの
    テーブルキャッシュをリセットする。
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
