import pytest
from meetflow_common import AuthError

from handlers import availability_requests

from _factories import (
    api_event,
    body_of,
    put_availability,
    put_community,
    put_membership,
    put_profile,
)

_TARGET_PERIOD = {
    "targetPeriodStart": "2026-08-01T00:00:00.000Z",
    "targetPeriodEnd": "2026-08-31T23:59:59.999Z",
    "deadline": "2026-07-25T23:59:59.999Z",
}


def _create_body(**overrides):
    body = {**_TARGET_PERIOD, "targetScope": "ALL", "message": "来月の空き予定を教えてください"}
    body.update(overrides)
    return body


def test_create_availability_request_all_scope_success(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = availability_requests.create_availability_request(
        "user-1",
        api_event(path_params={"communityId": "community-1"}, body=_create_body()),
    )

    assert response["statusCode"] == 201
    data = body_of(response)["data"]
    assert data["targetScope"] == "ALL"
    assert data["targetUserIds"] == []
    request_id = data["requestId"]
    stored = table.get_item(
        Key={"PK": "COMMUNITY#community-1", "SK": f"AVAILREQ#{request_id}"}
    )["Item"]
    assert stored["createdBy"] == "user-1"
    assert "targetUserIds" not in stored


def test_create_availability_request_specified_scope_success(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = availability_requests.create_availability_request(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"},
            body=_create_body(targetScope="SPECIFIED", targetUserIds=["user-2", "user-3"]),
        ),
    )

    assert response["statusCode"] == 201
    data = body_of(response)["data"]
    assert data["targetScope"] == "SPECIFIED"
    assert data["targetUserIds"] == ["user-2", "user-3"]


def test_create_availability_request_invalid_scope(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = availability_requests.create_availability_request(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"},
            body=_create_body(targetScope="EVERYONE"),
        ),
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "INVALID_PARAMETER"


def test_create_availability_request_invalid_time_range(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = availability_requests.create_availability_request(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"},
            body=_create_body(
                targetPeriodStart="2026-08-31T23:59:59.999Z",
                targetPeriodEnd="2026-08-01T00:00:00.000Z",
            ),
        ),
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "INVALID_PARAMETER"


def test_create_availability_request_forbidden_for_plain_member(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-2", role="MEMBER")

    with pytest.raises(AuthError) as exc_info:
        availability_requests.create_availability_request(
            "user-2",
            api_event(path_params={"communityId": "community-1"}, body=_create_body()),
        )
    assert exc_info.value.code == "FORBIDDEN"


def test_list_availability_requests_admin_sees_all(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    availability_requests.create_availability_request(
        "user-1",
        api_event(path_params={"communityId": "community-1"}, body=_create_body()),
    )
    availability_requests.create_availability_request(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"},
            body=_create_body(targetScope="SPECIFIED", targetUserIds=["user-2"]),
        ),
    )

    response = availability_requests.list_availability_requests(
        "user-1", api_event(path_params={"communityId": "community-1"})
    )

    assert response["statusCode"] == 200
    assert len(body_of(response)["data"]["requests"]) == 2


def test_list_availability_requests_target_member_sees_own_request_only(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")
    put_membership(table, "community-1", "user-3", role="MEMBER")
    availability_requests.create_availability_request(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"},
            body=_create_body(targetScope="SPECIFIED", targetUserIds=["user-2"]),
        ),
    )

    response_targeted = availability_requests.list_availability_requests(
        "user-2", api_event(path_params={"communityId": "community-1"})
    )
    response_not_targeted = availability_requests.list_availability_requests(
        "user-3", api_event(path_params={"communityId": "community-1"})
    )

    assert len(body_of(response_targeted)["data"]["requests"]) == 1
    assert body_of(response_not_targeted)["data"]["requests"] == []


def test_list_availability_requests_all_scope_visible_to_every_member(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")
    availability_requests.create_availability_request(
        "user-1",
        api_event(path_params={"communityId": "community-1"}, body=_create_body()),
    )

    response = availability_requests.list_availability_requests(
        "user-2", api_event(path_params={"communityId": "community-1"})
    )

    assert len(body_of(response)["data"]["requests"]) == 1


def test_list_pending_members_mixed_submission(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")
    put_membership(table, "community-1", "user-3", role="MEMBER")
    put_profile(table, "user-3", nickname="みっちゃん")
    # user-2 already submitted an availability inside the target period;
    # user-3 has not.
    put_availability(
        table,
        "community-1",
        "user-2",
        start_time="2026-08-05T10:00:00.000Z",
        end_time="2026-08-05T14:00:00.000Z",
    )

    create_response = availability_requests.create_availability_request(
        "user-1",
        api_event(path_params={"communityId": "community-1"}, body=_create_body()),
    )
    request_id = body_of(create_response)["data"]["requestId"]

    response = availability_requests.list_pending_members(
        "user-1",
        api_event(
            path_params={"communityId": "community-1", "requestId": request_id}
        ),
    )

    assert response["statusCode"] == 200
    pending = body_of(response)["data"]["pendingMembers"]
    pending_user_ids = {m["userId"] for m in pending}
    # user-1 (OWNER, creator) and user-2 (submitted) must not be pending;
    # user-3 has no availability in the target period.
    assert pending_user_ids == {"user-1", "user-3"}
    assert {"userId": "user-3", "nickname": "みっちゃん"} in pending


def test_list_pending_members_specified_scope(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")

    create_response = availability_requests.create_availability_request(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"},
            body=_create_body(targetScope="SPECIFIED", targetUserIds=["user-2"]),
        ),
    )
    request_id = body_of(create_response)["data"]["requestId"]

    response = availability_requests.list_pending_members(
        "user-1",
        api_event(
            path_params={"communityId": "community-1", "requestId": request_id}
        ),
    )

    pending = body_of(response)["data"]["pendingMembers"]
    assert [m["userId"] for m in pending] == ["user-2"]


def test_list_pending_members_request_not_found(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = availability_requests.list_pending_members(
        "user-1",
        api_event(
            path_params={"communityId": "community-1", "requestId": "does-not-exist"}
        ),
    )

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "AVAILABILITY_REQUEST_NOT_FOUND"
