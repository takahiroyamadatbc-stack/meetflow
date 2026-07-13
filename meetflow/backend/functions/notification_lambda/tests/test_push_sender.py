from unittest.mock import MagicMock, patch

import pytest
from boto3.dynamodb.conditions import Key
from pywebpush import WebPushException

from handlers import push_sender


@pytest.fixture(autouse=True)
def _mock_vapid_key():
    with patch.object(push_sender, "_get_vapid_private_key", return_value="test-vapid-key"):
        yield


def _put_subscription(table, user_id, *, endpoint="https://push.example/ep1"):
    table.put_item(
        Item={
            "PK": f"USER#{user_id}",
            "SK": f"PUSHSUB#{abs(hash(endpoint))}",
            "endpoint": endpoint,
            "p256dh": "p256dh-value",
            "auth": "auth-value",
        }
    )


def test_send_push_to_user_no_subscriptions_does_nothing(table):
    with patch.object(push_sender, "webpush") as mock_webpush:
        push_sender.send_push_to_user(
            table, "user-1", title="MeetFlow", body="hello", notif_type="CONFIRMED"
        )
    mock_webpush.assert_not_called()


def test_send_push_to_user_success_calls_webpush_per_subscription(table):
    _put_subscription(table, "user-1", endpoint="https://push.example/ep1")
    _put_subscription(table, "user-1", endpoint="https://push.example/ep2")

    with patch.object(push_sender, "webpush") as mock_webpush:
        push_sender.send_push_to_user(
            table, "user-1", title="MeetFlow", body="hello", notif_type="CONFIRMED"
        )

    assert mock_webpush.call_count == 2
    for call in mock_webpush.call_args_list:
        kwargs = call.kwargs
        assert kwargs["subscription_info"]["keys"] == {
            "p256dh": "p256dh-value",
            "auth": "auth-value",
        }
        assert kwargs["vapid_private_key"] == "test-vapid-key"
        assert kwargs["vapid_claims"]["sub"].startswith("mailto:")


def test_send_push_to_user_deletes_subscription_on_410_gone(table):
    _put_subscription(table, "user-1", endpoint="https://push.example/ep1")
    response = MagicMock()
    response.status_code = 410

    with patch.object(
        push_sender, "webpush", side_effect=WebPushException("gone", response=response)
    ):
        push_sender.send_push_to_user(
            table, "user-1", title="MeetFlow", body="hello", notif_type="CONFIRMED"
        )

    resp = table.query(KeyConditionExpression=Key("PK").eq("USER#user-1"))
    assert resp["Items"] == []


def test_send_push_to_user_keeps_subscription_on_other_errors(table):
    _put_subscription(table, "user-1", endpoint="https://push.example/ep1")
    response = MagicMock()
    response.status_code = 500

    with patch.object(
        push_sender, "webpush", side_effect=WebPushException("server error", response=response)
    ):
        # must not raise -- a transient push failure can't fail notification creation.
        push_sender.send_push_to_user(
            table, "user-1", title="MeetFlow", body="hello", notif_type="CONFIRMED"
        )

    resp = table.query(KeyConditionExpression=Key("PK").eq("USER#user-1"))
    assert len(resp["Items"]) == 1
