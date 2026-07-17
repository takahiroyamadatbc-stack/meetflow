import pytest
from meetflow_common import AuthError

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


def test_list_members_uses_display_name_when_set(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER", display_name="たか")
    put_profile(table, "user-1", nickname="オーナー太郎")

    response = members.list_members(
        "user-1", api_event(path_params={"communityId": "community-1"})
    )

    members_list = body_of(response)["data"]["members"]
    assert members_list[0]["nickname"] == "たか"


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


def test_update_my_display_name_success(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = members.update_my_display_name(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"displayName": "たか"}
        ),
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["displayName"] == "たか"
    membership = table.get_item(
        Key={"PK": "COMMUNITY#community-1", "SK": "MEMBER#user-1"}
    )["Item"]
    assert membership["displayName"] == "たか"


def test_update_my_display_name_clear_reverts_to_fallback(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER", display_name="たか")

    response = members.update_my_display_name(
        "user-1",
        api_event(path_params={"communityId": "community-1"}, body={"displayName": ""}),
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["displayName"] is None
    membership = table.get_item(
        Key={"PK": "COMMUNITY#community-1", "SK": "MEMBER#user-1"}
    )["Item"]
    assert "displayName" not in membership


def test_update_my_display_name_duplicate_with_other_display_name(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER", display_name="けん")

    response = members.update_my_display_name(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"displayName": "けん"}
        ),
    )

    assert response["statusCode"] == 409
    assert body_of(response)["error"]["code"] == "DISPLAY_NAME_ALREADY_TAKEN"


def test_update_my_display_name_duplicate_with_other_fallback_nickname(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")
    put_profile(table, "user-2", nickname="けん")

    response = members.update_my_display_name(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"displayName": "けん"}
        ),
    )

    assert response["statusCode"] == 409
    assert body_of(response)["error"]["code"] == "DISPLAY_NAME_ALREADY_TAKEN"


def test_update_my_display_name_own_previous_value_not_treated_as_duplicate(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER", display_name="たか")

    response = members.update_my_display_name(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"displayName": "たか"}
        ),
    )

    assert response["statusCode"] == 200


def test_update_my_display_name_too_long(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = members.update_my_display_name(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"displayName": "あ" * 31}
        ),
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "PROFILE_VALIDATION_ERROR"


def test_update_my_display_name_not_a_member(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    with pytest.raises(AuthError) as exc_info:
        members.update_my_display_name(
            "user-2",
            api_event(
                path_params={"communityId": "community-1"}, body={"displayName": "たか"}
            ),
        )
    assert exc_info.value.code == "FORBIDDEN"


def test_update_my_auto_approve_set(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = members.update_my_auto_approve(
        "user-1",
        api_event(path_params={"communityId": "community-1"}, body={"autoApprove": True}),
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["autoApprove"] is True
    membership = table.get_item(
        Key={"PK": "COMMUNITY#community-1", "SK": "MEMBER#user-1"}
    )["Item"]
    assert membership["autoApprove"] is True


def test_update_my_auto_approve_clear_reverts_to_fallback(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    members.update_my_auto_approve(
        "user-1",
        api_event(path_params={"communityId": "community-1"}, body={"autoApprove": True}),
    )

    response = members.update_my_auto_approve(
        "user-1",
        api_event(path_params={"communityId": "community-1"}, body={"autoApprove": None}),
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["autoApprove"] is None
    membership = table.get_item(
        Key={"PK": "COMMUNITY#community-1", "SK": "MEMBER#user-1"}
    )["Item"]
    assert "autoApprove" not in membership


def test_update_my_auto_approve_invalid_type(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = members.update_my_auto_approve(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"autoApprove": "yes"}
        ),
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "INVALID_PARAMETER"


def test_update_my_auto_approve_missing_field(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = members.update_my_auto_approve(
        "user-1", api_event(path_params={"communityId": "community-1"}, body={})
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "INVALID_PARAMETER"


def test_update_my_auto_approve_not_a_member(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    with pytest.raises(AuthError) as exc_info:
        members.update_my_auto_approve(
            "user-2",
            api_event(
                path_params={"communityId": "community-1"}, body={"autoApprove": True}
            ),
        )
    assert exc_info.value.code == "FORBIDDEN"
