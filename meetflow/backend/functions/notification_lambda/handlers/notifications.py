from boto3.dynamodb.conditions import Key

from meetflow_common import error_response, get_table, success_response


def list_notifications(user_id, event):
    """F-702 (API設計書v1.4 §11.1)."""
    table = get_table()
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"USER#{user_id}")
        & Key("SK").begins_with("NOTIF#"),
        ScanIndexForward=False,
    )
    notifications = [_to_api_notification(item) for item in resp.get("Items", [])]
    return success_response({"notifications": notifications})


def mark_read(user_id, event):
    """F-702 (API設計書v1.4 §11.2)."""
    notification_id = event["pathParameters"]["notificationId"]
    table = get_table()

    # pathにはnotificationIdのみが含まれ、SKに埋め込まれたcreatedAtは
    # 含まれない -- 呼び出し元自身のパーティション内でアイテムを探す
    # （AvailabilityLambdaの`_find_own_availability`と同じアプローチ。
    # `USER#{user_id}`でスコープすることが所有権チェックも兼ねる）。
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"USER#{user_id}")
        & Key("SK").begins_with("NOTIF#")
    )
    target = None
    for item in resp.get("Items", []):
        if item["SK"].split("#", 2)[2] == notification_id:
            target = item
            break
    if target is None:
        return error_response("NOTIFICATION_NOT_FOUND", "指定した通知が見つかりません")

    table.update_item(
        Key={"PK": target["PK"], "SK": target["SK"]},
        UpdateExpression="SET #read = :true",
        ExpressionAttributeNames={"#read": "read"},
        ExpressionAttributeValues={":true": True},
    )
    return success_response({"notificationId": notification_id, "read": True})


def _to_api_notification(item):
    _, created_at, notification_id = item["SK"].split("#", 2)
    return {
        "notificationId": notification_id,
        "type": item.get("type"),
        "message": item.get("message"),
        "read": item.get("read", False),
        "relatedEventId": item.get("relatedEventId"),
        "relatedCommunityId": item.get("relatedCommunityId"),
        "createdAt": created_at,
    }
