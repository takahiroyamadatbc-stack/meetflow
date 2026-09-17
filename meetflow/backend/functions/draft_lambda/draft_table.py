"""DraftTable（ドラフト専用DynamoDBテーブル）へのアクセサ。

DESIGN.md §4.11に従い、ドラフト企画はMeetFlow本体とは別のテーブルを使う。
本体の`meetflow_common.get_table()`はTABLE_NAME環境変数を見て本体テーブルを
返すため、ここではそれとは別にDRAFT_TABLE_NAMEを見る専用のアクセサを置く。

DraftLambdaは2つのテーブルを使い分ける:
    get_draft_table() … ドラフトのデータ（このモジュール）
    get_table()       … 本体テーブル。Membership確認のための読み取りのみ
"""

import os

import boto3

_draft_table = None


def get_draft_table():
    global _draft_table
    if _draft_table is None:
        _draft_table = boto3.resource("dynamodb").Table(os.environ["DRAFT_TABLE_NAME"])
    return _draft_table
