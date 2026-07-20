import pytest
from meetflow_common import AuthError

from handlers import invites

from _factories import (
    api_event,
    body_of,
    put_community,
    put_invite,
    put_join_request,
    put_membership,
    put_profile,
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


def test_create_invite_records_created_by_role_owner(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = invites.create_invite(
        "user-1", api_event(path_params={"communityId": "community-1"})
    )

    url = body_of(response)["data"]["url"]
    token = url.rsplit("/", 1)[1]
    invite = table.get_item(Key={"PK": f"INVITE#{token}", "SK": "METADATA"})["Item"]
    assert invite["createdByRole"] == "OWNER"


def test_create_invite_allowed_for_plain_member(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")

    response = invites.create_invite(
        "user-2", api_event(path_params={"communityId": "community-1"})
    )

    assert response["statusCode"] == 201
    url = body_of(response)["data"]["url"]
    token = url.rsplit("/", 1)[1]
    invite = table.get_item(Key={"PK": f"INVITE#{token}", "SK": "METADATA"})["Item"]
    assert invite["createdByRole"] == "MEMBER"


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


def test_join_via_invite_requires_approval_when_invite_created_by_member(table):
    put_community(table, "community-1", owner_id="user-1", member_approval_required=False)
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_invite(
        table,
        "tok123",
        community_id="community-1",
        created_by="user-1",
        created_by_role="MEMBER",
    )

    response = invites.join_via_invite(
        "user-2", api_event(path_params={"token": "tok123"})
    )

    assert response["statusCode"] == 201
    data = body_of(response)["data"]
    assert data == {"communityId": "community-1", "status": "PENDING"}
    join_request = table.get_item(
        Key={"PK": "COMMUNITY#community-1", "SK": "JOINREQ#user-2"}
    )["Item"]
    assert join_request["status"] == "PENDING"


def test_join_via_invite_join_request_already_pending(table):
    put_community(table, "community-1", owner_id="user-1", member_approval_required=True)
    put_invite(table, "tok123", community_id="community-1", created_by="user-1")
    put_join_request(table, "community-1", "user-2", status="PENDING")

    response = invites.join_via_invite(
        "user-2", api_event(path_params={"token": "tok123"})
    )

    assert response["statusCode"] == 409
    assert body_of(response)["error"]["code"] == "JOIN_REQUEST_ALREADY_PENDING"


def test_get_invite_preview_no_approval_required(table):
    put_community(table, "community-1", owner_id="user-1", member_approval_required=False)
    put_invite(table, "tok123", community_id="community-1", created_by="user-1")

    response = invites.get_invite_preview(
        "user-2", api_event(path_params={"token": "tok123"})
    )

    assert response["statusCode"] == 200
    data = body_of(response)["data"]
    assert data == {
        "communityId": "community-1",
        "communityName": "テストコミュニティ",
        "communityDescription": "",
        "communityGenre": "麻雀",
        "communityIcon": None,
        "approvalRequired": False,
        # user-1はput_membershipされていない（put_communityはMembershipを
        # 作らない）ため、招待者のMembershipが無いケースとして
        # invitedByDisplayNameはNoneになる。
        "invitedByDisplayName": None,
        "alreadyMember": False,
        "joinRequestPending": False,
    }


def test_get_invite_preview_invited_by_display_name_prefers_membership(table):
    put_community(table, "community-1", owner_id="user-1", member_approval_required=False)
    put_membership(table, "community-1", "user-1", role="OWNER", display_name="オーナー太郎")
    put_profile(table, "user-1", nickname="グローバル太郎")
    put_invite(table, "tok123", community_id="community-1", created_by="user-1")

    response = invites.get_invite_preview(
        "user-2", api_event(path_params={"token": "tok123"})
    )

    assert body_of(response)["data"]["invitedByDisplayName"] == "オーナー太郎"


def test_get_invite_preview_invited_by_display_name_falls_back_to_nickname(table):
    put_community(table, "community-1", owner_id="user-1", member_approval_required=False)
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_profile(table, "user-1", nickname="グローバル太郎")
    put_invite(table, "tok123", community_id="community-1", created_by="user-1")

    response = invites.get_invite_preview(
        "user-2", api_event(path_params={"token": "tok123"})
    )

    assert body_of(response)["data"]["invitedByDisplayName"] == "グローバル太郎"


def test_get_invite_preview_invited_by_display_name_omitted_when_inviter_left(table):
    put_community(table, "community-1", owner_id="user-1", member_approval_required=False)
    # 招待者user-1のMembershipは無い（既に退会した想定）。
    put_invite(table, "tok123", community_id="community-1", created_by="user-1")

    response = invites.get_invite_preview(
        "user-2", api_event(path_params={"token": "tok123"})
    )

    assert body_of(response)["data"]["invitedByDisplayName"] is None


def test_get_invite_preview_already_member(table):
    put_community(table, "community-1", owner_id="user-1", member_approval_required=False)
    put_membership(table, "community-1", "user-2", role="MEMBER")
    put_invite(table, "tok123", community_id="community-1", created_by="user-1")

    response = invites.get_invite_preview(
        "user-2", api_event(path_params={"token": "tok123"})
    )

    assert body_of(response)["data"]["alreadyMember"] is True


def test_get_invite_preview_join_request_pending(table):
    put_community(table, "community-1", owner_id="user-1", member_approval_required=True)
    put_join_request(table, "community-1", "user-2", status="PENDING")
    put_invite(table, "tok123", community_id="community-1", created_by="user-1")

    response = invites.get_invite_preview(
        "user-2", api_event(path_params={"token": "tok123"})
    )

    assert body_of(response)["data"]["joinRequestPending"] is True


def test_get_invite_preview_approval_required_due_to_community_setting(table):
    put_community(table, "community-1", owner_id="user-1", member_approval_required=True)
    put_invite(table, "tok123", community_id="community-1", created_by="user-1")

    response = invites.get_invite_preview(
        "user-2", api_event(path_params={"token": "tok123"})
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["approvalRequired"] is True


def test_get_invite_preview_approval_required_due_to_member_issuer(table):
    put_community(table, "community-1", owner_id="user-1", member_approval_required=False)
    put_invite(
        table,
        "tok123",
        community_id="community-1",
        created_by="user-2",
        created_by_role="MEMBER",
    )

    response = invites.get_invite_preview(
        "user-3", api_event(path_params={"token": "tok123"})
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["approvalRequired"] is True


def test_get_invite_preview_not_found(table):
    response = invites.get_invite_preview(
        "user-2", api_event(path_params={"token": "does-not-exist"})
    )

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "INVITE_NOT_FOUND"


def test_get_invite_preview_revoked(table):
    put_community(table, "community-1", owner_id="user-1")
    put_invite(table, "tok123", community_id="community-1", created_by="user-1", revoked=True)

    response = invites.get_invite_preview(
        "user-2", api_event(path_params={"token": "tok123"})
    )

    assert response["statusCode"] == 410
    assert body_of(response)["error"]["code"] == "INVITE_REVOKED"


def test_revoke_invite_success(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_invite(table, "tok123", community_id="community-1", created_by="user-1")

    response = invites.revoke_invite(
        "user-1", api_event(path_params={"token": "tok123"})
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"] == {
        "token": "tok123",
        "communityId": "community-1",
        "revoked": True,
    }
    invite = table.get_item(Key={"PK": "INVITE#tok123", "SK": "METADATA"})["Item"]
    assert invite["revoked"] is True


def test_revoke_invite_idempotent_when_already_revoked(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_invite(table, "tok123", community_id="community-1", created_by="user-1", revoked=True)

    response = invites.revoke_invite(
        "user-1", api_event(path_params={"token": "tok123"})
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["revoked"] is True


def test_revoke_invite_not_found(table):
    response = invites.revoke_invite(
        "user-1", api_event(path_params={"token": "does-not-exist"})
    )

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "INVITE_NOT_FOUND"


def test_revoke_invite_forbidden_for_non_admin(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")
    put_invite(table, "tok123", community_id="community-1", created_by="user-1")

    with pytest.raises(AuthError) as exc_info:
        invites.revoke_invite("user-2", api_event(path_params={"token": "tok123"}))
    assert exc_info.value.code == "FORBIDDEN"


def test_revoke_invite_allowed_for_creator_even_if_plain_member(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")
    put_invite(
        table,
        "tok123",
        community_id="community-1",
        created_by="user-2",
        created_by_role="MEMBER",
    )

    response = invites.revoke_invite(
        "user-2", api_event(path_params={"token": "tok123"})
    )

    assert response["statusCode"] == 200
    invite = table.get_item(Key={"PK": "INVITE#tok123", "SK": "METADATA"})["Item"]
    assert invite["revoked"] is True
