import os

import boto3

# Lambda設計書v1.1 §12.1: shared DynamoDB client/table helper for every
# domain Lambda. All entities live in the single table named by the
# TABLE_NAME env var (DynamoDB物理設計書v1.3 §1), so one cached Table
# resource is enough regardless of which entity a handler is working with.
_table = None


def get_table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
    return _table
