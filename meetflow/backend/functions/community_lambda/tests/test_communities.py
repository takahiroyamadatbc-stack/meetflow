import pytest
from meetflow_common import AuthError

from handlers import communities

from _factories import api_event, body_of, put_community, put_membership


def test_create_community_success(table):
    event = api_event(
        body={
            "name": "火曜麻雀会",
            "description": "毎週火曜開催",
            "genre": "麻雀",
            "memberApprovalRequired": True,
        }
    )

    response = communities.create_community("user-1", event)

    assert response["statusCode"] == 201
    data = body_of(response)["data"]
    assert data["name"] == "火曜麻雀会"
    assert data["memberApprovalRequired"] is True
    community_id = data["communityId"]

    # コミュニティのメタデータとオーナーのmembershipの両方が書き込まれる。
    community = table.get_item(
        Key={"PK": f"COMMUNITY#{community_id}", "SK": "METADATA"}
    )["Item"]
    assert community["ownerId"] == "user-1"
    membership = table.get_item(
        Key={"PK": f"COMMUNITY#{community_id}", "SK": "MEMBER#user-1"}
    )["Item"]
    assert membership["role"] == "OWNER"


@pytest.mark.parametrize("name", ["", "a" * 51])
def test_create_community_invalid_name(table, name):
    response = communities.create_community("user-1", api_event(body={"name": name}))

    assert response["statusCode"] == 400
    error = body_of(response)["error"]
    assert error["code"] == "INVALID_PARAMETER"


def test_list_communities_success(table):
    put_community(table, "community-1", owner_id="user-1", name="コミュニティA")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = communities.list_communities("user-1", api_event())

    assert response["statusCode"] == 200
    communities_list = body_of(response)["data"]["communities"]
    assert communities_list == [
        {
            "communityId": "community-1",
            "name": "コミュニティA",
            "description": "",
            "genre": "麻雀",
            "role": "OWNER",
        }
    ]


def test_update_community_success(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = communities.update_community(
        "user-1",
        api_event(path_params={"communityId": "community-1"}, body={"name": "改名後"}),
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["name"] == "改名後"


def test_update_community_invalid_name(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = communities.update_community(
        "user-1",
        api_event(path_params={"communityId": "community-1"}, body={"name": ""}),
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "INVALID_PARAMETER"


def test_update_community_no_fields_to_update(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = communities.update_community(
        "user-1", api_event(path_params={"communityId": "community-1"}, body={})
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "INVALID_PARAMETER"


def test_update_community_forbidden_for_plain_member(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-2", role="MEMBER")

    with pytest.raises(AuthError) as exc_info:
        communities.update_community(
            "user-2",
            api_event(path_params={"communityId": "community-1"}, body={"name": "x"}),
        )
    assert exc_info.value.code == "FORBIDDEN"


def test_transfer_owner_success(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")

    response = communities.transfer_owner(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"newOwnerId": "user-2"}
        ),
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["ownerId"] == "user-2"
    new_owner = table.get_item(
        Key={"PK": "COMMUNITY#community-1", "SK": "MEMBER#user-2"}
    )["Item"]
    assert new_owner["role"] == "OWNER"
    old_owner = table.get_item(
        Key={"PK": "COMMUNITY#community-1", "SK": "MEMBER#user-1"}
    )["Item"]
    assert old_owner["role"] == "MEMBER"
    community = table.get_item(Key={"PK": "COMMUNITY#community-1", "SK": "METADATA"})[
        "Item"
    ]
    assert community["ownerId"] == "user-2"


def test_transfer_owner_to_self_is_invalid(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = communities.transfer_owner(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"newOwnerId": "user-1"}
        ),
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "INVALID_PARAMETER"


def test_transfer_owner_target_not_active_member(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER", status="SUSPENDED")

    response = communities.transfer_owner(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"newOwnerId": "user-2"}
        ),
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "INVALID_PARAMETER"
