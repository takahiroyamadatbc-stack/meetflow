from boto3.dynamodb.types import TypeSerializer

from .dynamodb import get_table

_serializer = TypeSerializer()


def _serialize_item(item: dict) -> dict:
    return {k: _serializer.serialize(v) for k, v in item.items()}


def transact_write(operations: list) -> None:
    """Run a list of Put/Update/ConditionCheck/Delete operations as a single
    DynamoDB TransactWriteItems call.

    DynamoDB物理設計書v1.3 §5 reserves TransactWriteItems for operations
    that must not partially apply: join request approval, OWNER transfer,
    event confirmation.

    Each operation dict uses the same shape as the low-level
    `transact_write_items` API (e.g. `{"Put": {"Item": {...}, ...}}`,
    `{"Update": {"Key": {...}, "UpdateExpression": ..., ...}}`), except
    `Item`/`Key`/`ExpressionAttributeValues` may be given as plain Python
    values (str/int/bool/dict/set/etc.) rather than hand-written
    `{"S": ...}`-style DynamoDB JSON -- this serializes them automatically,
    the same way the higher-level Table resource does for GetItem/PutItem.
    """
    table = get_table()
    table_name = table.table_name
    transact_items = []
    for op in operations:
        op_type, body = next(iter(op.items()))
        body = dict(body)
        body["TableName"] = table_name
        if "Item" in body:
            body["Item"] = _serialize_item(body["Item"])
        if "Key" in body:
            body["Key"] = _serialize_item(body["Key"])
        if "ExpressionAttributeValues" in body:
            body["ExpressionAttributeValues"] = _serialize_item(
                body["ExpressionAttributeValues"]
            )
        transact_items.append({op_type: body})
    table.meta.client.transact_write_items(TransactItems=transact_items)
