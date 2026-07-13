from unittest.mock import patch

import pytest
from boto3.dynamodb.conditions import Key

from meetflow_common import AVAILABILITY_REQUEST_CREATED, EVENT_CONFIRMED

from handlers import event_subscriber

from _factories import domain_event, put_membership


@pytest.fixture(autouse=True)
def _mock_push_sender():
    """These tests only cover in-app Notification record creation --
    Web Push sending itself is push_sender.py's own concern (see
    test_push_sender.py), and none of these tests register any
    PushSubscription anyway.

    Patches via the already-imported `event_subscriber` module object
    (captured above at collection time) rather than a string target: every
    domain Lambda has its own same-named `handlers` package, and a string
    target like "handlers.event_subscriber..." gets re-resolved by
    unittest.mock through sys.modules at the time this fixture runs (test
    *execution* phase, after pytest has already collected -- and imported --
    every other domain's tests too), which can land on a different domain's
    `handlers` package than the one this file actually imported from.
    """
    with patch.object(event_subscriber.push_sender, "send_push_to_user") as mock_send:
        yield mock_send


def _notifications_for(table, user_id):
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"USER#{user_id}") & Key("SK").begins_with("NOTIF#")
    )
    return resp.get("Items", [])


def test_availability_request_created_all_scope_notifies_every_member(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")

    event_subscriber.handle_domain_event(
        domain_event(
            AVAILABILITY_REQUEST_CREATED,
            {
                "communityId": "community-1",
                "requestId": "req-1",
                "targetScope": "ALL",
                "targetUserIds": [],
            },
        )
    )

    for user_id in ("user-1", "user-2"):
        notifications = _notifications_for(table, user_id)
        assert len(notifications) == 1
        assert notifications[0]["type"] == "AVAILABILITY_REQUEST"


def test_availability_request_created_specified_scope_notifies_targets_only(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")
    put_membership(table, "community-1", "user-3", role="MEMBER")

    event_subscriber.handle_domain_event(
        domain_event(
            AVAILABILITY_REQUEST_CREATED,
            {
                "communityId": "community-1",
                "requestId": "req-1",
                "targetScope": "SPECIFIED",
                "targetUserIds": ["user-2"],
            },
        )
    )

    assert len(_notifications_for(table, "user-2")) == 1
    assert _notifications_for(table, "user-1") == []
    assert _notifications_for(table, "user-3") == []


def test_event_confirmed_still_notifies_participants(table):
    """Regression check: adding the AvailabilityRequestCreated branch must
    not disturb the pre-existing dispatch for other detail-types."""
    event_subscriber.handle_domain_event(
        domain_event(
            EVENT_CONFIRMED,
            {
                "eventId": "event-1",
                "communityId": "community-1",
                "participantIds": ["user-1", "user-2"],
                "startTime": "2026-08-01T19:00:00.000Z",
                "endTime": "2026-08-01T23:00:00.000Z",
            },
        )
    )

    for user_id in ("user-1", "user-2"):
        notifications = _notifications_for(table, user_id)
        assert len(notifications) == 1
        assert notifications[0]["type"] == "CONFIRMED"
