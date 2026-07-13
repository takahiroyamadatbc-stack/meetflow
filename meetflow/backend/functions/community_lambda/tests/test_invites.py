from handlers import invites

from _factories import (
    api_event,
    body_of,
    put_community,
    put_invite,
    put_join_request,
    put_membership,
)


def test_create_invite_success(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = invites.create_invite(
        "user-1", api_event(path_params={"communityId": "community-1"})
    )

    assert response["statusCode"] == 201
    url = body_of(response)["data"]["url"]
    token = url.rsplit("/", 1)[1]
    invite = table.get_item(Key={"PK": f"INVITE#{token}", "SK": "METADATA"})["Item"]
    assert invite["communityId"] == "community-1"
    assert invite["revoked"] is False


def test_join_via_invite_immediate_join_success(table):
    put_community(table, "community-1", owner_id="user-1", member_approval_required=False)
    put_invite(table, "tok123", community_id="community-1", created_by="user-1")

    response = invites.join_via_invite(
        "user-2", api_event(path_params={"token": "tok123"})
    )

    assert response["statusCode"] == 201
    data = body_of(response)["data"]
    assert data == {"communityId": "community-1", "status": "ACTIVE"}
    membership = table.get_item(
        Key={"PK": "COMMUNITY#community-1", "SK": "MEMBER#user-2"}
    )["Item"]
    assert membership["role"] == "MEMBER"
    assert membership["status"] == "ACTIVE"


def test_join_via_invite_creates_pending_join_request_when_approval_required(table):
    put_community(table, "community-1", owner_id="user-1", member_approval_required=True)
    put_invite(table, "tok123", community_id="community-1", created_by="user-1")

    response = invites.join_via_invite(
        "user-2",
        api_event(path_params={"token": "tok123"}, body={"message": "よろしくお願いします"}),
    )

    assert response["statusCode"] == 201
    data = body_of(response)["data"]
    assert data == {"communityId": "community-1", "status": "PENDING"}
    join_request = table.get_item(
        Key={"PK": "COMMUNITY#community-1", "SK": "JOINREQ#user-2"}
    )["Item"]
    assert join_request["status"] == "PENDING"
    assert join_request["message"] == "よろしくお願いします"
    # リクエストがpendingの間はメンバーとして追加されない。
    assert (
        table.get_item(Key={"PK": "COMMUNITY#community-1", "SK": "MEMBER#user-2"}).get(
            "Item"
        )
        is None
    )


def test_join_via_invite_invite_not_found(table):
    response = invites.join_via_invite(
        "user-2", api_event(path_params={"token": "does-not-exist"})
    )

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "INVITE_NOT_FOUND"


def test_join_via_invite_invite_revoked(table):
    put_community(table, "community-1", owner_id="user-1")
    put_invite(table, "tok123", community_id="community-1", created_by="user-1", revoked=True)

    response = invites.join_via_invite(
        "user-2", api_event(path_params={"token": "tok123"})
    )

    assert response["statusCode"] == 410
    assert body_of(response)["error"]["code"] == "INVITE_REVOKED"


def test_join_via_invite_already_member(table):
    put_community(table, "community-1", owner_id="user-1")
    put_invite(table, "tok123", community_id="community-1", created_by="user-1")
    put_membership(table, "community-1", "user-2", role="MEMBER")

    response = invites.join_via_invite(
        "user-2", api_event(path_params={"token": "tok123"})
    )

    assert response["statusCode"] == 409
    assert body_of(response)["error"]["code"] == "ALREADY_MEMBER"


def test_join_via_invite_join_request_already_pending(table):
    put_community(table, "community-1", owner_id="user-1", member_approval_required=True)
    put_invite(table, "tok123", community_id="community-1", created_by="user-1")
    put_join_request(table, "community-1", "user-2", status="PENDING")

    response = invites.join_via_invite(
        "user-2", api_event(path_params={"token": "tok123"})
    )

    assert response["statusCode"] == 409
    assert body_of(response)["error"]["code"] == "JOIN_REQUEST_ALREADY_PENDING"
