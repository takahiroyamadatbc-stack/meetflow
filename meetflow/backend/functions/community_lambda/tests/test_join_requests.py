from handlers import join_requests

from _factories import (
    api_event,
    body_of,
    put_community,
    put_join_request,
    put_membership,
    put_profile,
)


def test_list_join_requests_success(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_profile(table, "user-2", nickname="じゃんたろう")
    put_join_request(table, "community-1", "user-2", message="お願いします")

    response = join_requests.list_join_requests(
        "user-1", api_event(path_params={"communityId": "community-1"})
    )

    assert response["statusCode"] == 200
    requests = body_of(response)["data"]["requests"]
    assert len(requests) == 1
    assert requests[0]["userId"] == "user-2"
    assert requests[0]["nickname"] == "じゃんたろう"
    assert requests[0]["status"] == "PENDING"


def test_approve_join_request_success(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_join_request(table, "community-1", "user-2")

    response = join_requests.approve_join_request(
        "user-1",
        api_event(path_params={"communityId": "community-1", "requestId": "user-2"}),
    )

    assert response["statusCode"] == 200
    data = body_of(response)["data"]
    assert data == {"communityId": "community-1", "userId": "user-2", "status": "ACTIVE"}

    join_request = table.get_item(
        Key={"PK": "COMMUNITY#community-1", "SK": "JOINREQ#user-2"}
    )["Item"]
    assert join_request["status"] == "APPROVED"
    membership = table.get_item(
        Key={"PK": "COMMUNITY#community-1", "SK": "MEMBER#user-2"}
    )["Item"]
    assert membership["role"] == "MEMBER"
    assert membership["status"] == "ACTIVE"


def test_approve_join_request_not_found(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = join_requests.approve_join_request(
        "user-1",
        api_event(path_params={"communityId": "community-1", "requestId": "user-2"}),
    )

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "JOIN_REQUEST_NOT_FOUND"


def test_approve_join_request_already_processed(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_join_request(table, "community-1", "user-2", status="REJECTED")

    response = join_requests.approve_join_request(
        "user-1",
        api_event(path_params={"communityId": "community-1", "requestId": "user-2"}),
    )

    assert response["statusCode"] == 409
    assert body_of(response)["error"]["code"] == "JOIN_REQUEST_ALREADY_PROCESSED"


def test_reject_join_request_success(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_join_request(table, "community-1", "user-2")

    response = join_requests.reject_join_request(
        "user-1",
        api_event(path_params={"communityId": "community-1", "requestId": "user-2"}),
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["status"] == "REJECTED"
    join_request = table.get_item(
        Key={"PK": "COMMUNITY#community-1", "SK": "JOINREQ#user-2"}
    )["Item"]
    assert join_request["status"] == "REJECTED"


def test_reject_join_request_not_found(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = join_requests.reject_join_request(
        "user-1",
        api_event(path_params={"communityId": "community-1", "requestId": "user-2"}),
    )

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "JOIN_REQUEST_NOT_FOUND"


def test_reject_join_request_already_processed(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_join_request(table, "community-1", "user-2", status="APPROVED")

    response = join_requests.reject_join_request(
        "user-1",
        api_event(path_params={"communityId": "community-1", "requestId": "user-2"}),
    )

    assert response["statusCode"] == 409
    assert body_of(response)["error"]["code"] == "JOIN_REQUEST_ALREADY_PROCESSED"
