import os

import boto3

# Lambda設計書v1.1 §12.1: 全ドメインLambda共通のDynamoDBクライアント/
# テーブルヘルパー。全エンティティはTABLE_NAME環境変数で指定される単一
# テーブルに格納されている（DynamoDB物理設計書v1.3 §1）ため、ハンドラーが
# どのエンティティを扱っていてもキャッシュされたTableリソース1つで足りる。
_table = None


def get_table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
    return _table
