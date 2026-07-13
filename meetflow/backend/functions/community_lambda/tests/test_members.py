from handlers import members

from _factories import api_event, body_of, put_community, put_membership, put_profile


def test_list_members_success(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_profile(table, "user-1", nickname="オーナー太郎")

    response = members.list_members(
        "user-1", api_event(path_params={"communityId": "community-1"})
    )

    assert response["statusCode"] == 200
    members_list = body_of(response)["data"]["members"]
    assert len(members_list) == 1
    assert members_list[0]["userId"] == "user-1"
    assert members_list[0]["nickname"] == "オーナー太郎"
    assert members_list[0]["role"] == "OWNER"


def test_update_member_change_role_success(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")

    response = members.update_member(
        "user-1",
        api_event(
            path_params={"communityId": "community-1", "userId": "user-2"},
            body={"role": "ADMIN"},
        ),
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["role"] == "ADMIN"
    membership = table.get_item(
        Key={"PK": "COMMUNITY#community-1", "SK": "MEMBER#user-2"}
    )["Item"]
    assert membership["role"] == "ADMIN"


def test_update_member_remove_success(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")

    response = members.update_member(
        "user-1",
        api_event(
            path_params={"communityId": "community-1", "userId": "user-2"},
            body={"remove": True},
        ),
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["removed"] is True
    assert (
        table.get_item(Key={"PK": "COMMUNITY#community-1", "SK": "MEMBER#user-2"}).get(
            "Item"
        )
        is None
    )


def test_update_member_target_not_found(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = members.update_member(
        "user-1",
        api_event(
            path_params={"communityId": "community-1", "userId": "user-2"},
            body={"role": "ADMIN"},
        ),
    )

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "USER_NOT_FOUND"


def test_update_member_last_owner_cannot_leave(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = members.update_member(
        "user-1",
        api_event(
            path_params={"communityId": "community-1", "userId": "user-1"},
            body={"remove": True},
        ),
    )

    assert response["statusCode"] == 409
    assert body_of(response)["error"]["code"] == "LAST_OWNER_CANNOT_LEAVE"


def test_update_member_invalid_role(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")

    response = members.update_member(
        "user-1",
        api_event(
            path_params={"communityId": "community-1", "userId": "user-2"},
            body={"role": "OWNER"},
        ),
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "INVALID_PARAMETER"


def test_update_member_no_fields_to_update(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")

    response = members.update_member(
        "user-1",
        api_event(
            path_params={"communityId": "community-1", "userId": "user-2"}, body={}
        ),
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "INVALID_PARAMETER"
