import time

from boto3.dynamodb.conditions import Key

from meetflow_common import now_iso_ms

from handlers import notifications

from _factories import api_event, body_of


def _put_notification(table, user_id, notification_id, *, read=False, ttl=None):
    created_at = now_iso_ms()
    item = {
        "PK": f"USER#{user_id}",
        "SK": f"NOTIF#{created_at}#{notification_id}",
        "type": "CONFIRMED",
        "message": "参加予定のイベントが確定しました。",
        "read": read,
        "createdAt": created_at,
    }
    if ttl is not None:
        item["ttl"] = ttl
    table.put_item(Item=item)
    return item


def test_list_notifications_success(table):
    _put_notification(table, "user-1", "notif-1")
    _put_notification(table, "user-1", "notif-2")
    _put_notification(table, "user-2", "notif-3")

    response = notifications.list_notifications("user-1", api_event())

    assert response["statusCode"] == 200
    data = body_of(response)["data"]["notifications"]
    assert {n["notificationId"] for n in data} == {"notif-1", "notif-2"}


def test_mark_read_success(table):
    _put_notification(table, "user-1", "notif-1", ttl=int(time.time()) + 90 * 86400)

    response = notifications.mark_read(
        "user-1", api_event(path_params={"notificationId": "notif-1"})
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["read"] is True


def test_mark_read_shortens_ttl_to_24_hours(table):
    """Issue #91: 既読化すると、未読時の90日後の仮TTLよりも短い
    24時間後の値に上書きされる。"""
    unread_ttl = int(time.time()) + 90 * 86400
    _put_notification(table, "user-1", "notif-1", ttl=unread_ttl)
    before = int(time.time())

    notifications.mark_read("user-1", api_event(path_params={"notificationId": "notif-1"}))

    resp = table.query(KeyConditionExpression=Key("PK").eq("USER#user-1"))
    stored = resp["Items"][0]
    assert stored["ttl"] < unread_ttl
    assert abs(stored["ttl"] - (before + 24 * 3600)) <= 5


def test_mark_read_not_found(table):
    response = notifications.mark_read(
        "user-1", api_event(path_params={"notificationId": "does-not-exist"})
    )

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "NOTIFICATION_NOT_FOUND"


def test_mark_read_scoped_to_own_notifications(table):
    """USER#{user_id}でスコープすることが所有権チェックを兼ねるため、
    他人の通知IDを指定してもNOTIFICATION_NOT_FOUNDになる。"""
    _put_notification(table, "user-2", "notif-1")

    response = notifications.mark_read(
        "user-1", api_event(path_params={"notificationId": "notif-1"})
    )

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "NOTIFICATION_NOT_FOUND"
