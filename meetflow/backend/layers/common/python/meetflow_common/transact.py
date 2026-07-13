from .dynamodb import get_table


def transact_write(operations: list) -> None:
    """Run a list of Put/Update/ConditionCheck/Delete operations as a single
    DynamoDB TransactWriteItems call.

    DynamoDB物理設計書v1.3 §5 reserves TransactWriteItems for operations
    that must not partially apply: join request approval, OWNER transfer,
    event confirmation.

    Each operation dict uses the same shape as the low-level
    `transact_write_items` API (e.g. `{"Put": {"Item": {...}, ...}}`,
    `{"Update": {"Key": {...}, "UpdateExpression": ..., ...}}`), with
    `Item`/`Key`/`ExpressionAttributeValues` given as plain Python values
    (str/int/bool/dict/set/etc.) rather than hand-written `{"S": ...}`-style
    DynamoDB JSON. No manual serialization is needed here: `get_table()`
    returns a resource-level Table, so `table.meta.client` already has
    boto3's `before-parameter-build.dynamodb` attribute-value injector
    registered (boto3.dynamodb.transform.DynamoDBHighLevelResource) and
    converts plain Python values on every call made through it, including
    TransactWriteItems -- serializing them again here would double-encode
    them into invalid DynamoDB JSON.
    """
    table = get_table()
    table_name = table.table_name
    transact_items = []
    for op in operations:
        op_type, body = next(iter(op.items()))
        body = dict(body)
        body["TableName"] = table_name
        transact_items.append({op_type: body})
    table.meta.client.transact_write_items(TransactItems=transact_items)
