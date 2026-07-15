import pytest
from meetflow_common import AuthError, write_operation_log

from handlers import logs

from _factories import api_event, body_of, put_community, put_membership, put_profile


def test_list_community_logs_success(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_profile(table, "user-1", nickname="オーナー太郎")
    write_operation_log(
        action="CREATE_COMMUNITY",
        user_id="user-1",
        community_id="community-1",
        target_type="Community",
        target_id="community-1",
    )

    response = logs.list_community_logs(
        "user-1", api_event(path_params={"communityId": "community-1"})
    )

    assert response["statusCode"] == 200
    entries = body_of(response)["data"]["logs"]
    assert len(entries) == 1
    assert entries[0]["action"] == "CREATE_COMMUNITY"
    assert entries[0]["communityId"] == "community-1"
    assert entries[0]["userId"] == "user-1"
    assert entries[0]["displayName"] == "オーナー太郎"


def test_list_community_logs_uses_display_name_when_set(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER", display_name="たか")
    put_profile(table, "user-1", nickname="オーナー太郎")
    write_operation_log(
        action="UPDATE_COMMUNITY",
        user_id="user-1",
        community_id="community-1",
    )

    response = logs.list_community_logs(
        "user-1", api_event(path_params={"communityId": "community-1"})
    )

    assert body_of(response)["data"]["logs"][0]["displayName"] == "たか"


def test_list_community_logs_forbidden_for_non_admin(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")

    with pytest.raises(AuthError) as exc_info:
        logs.list_community_logs(
            "user-2", api_event(path_params={"communityId": "community-1"})
        )
    assert exc_info.value.code == "FORBIDDEN"


def test_list_community_logs_forbidden_for_non_member(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    with pytest.raises(AuthError) as exc_info:
        logs.list_community_logs(
            "user-2", api_event(path_params={"communityId": "community-1"})
        )
    assert exc_info.value.code == "FORBIDDEN"


def test_get_user_logs_self_sees_own_logs_including_global(table):
    put_profile(table, "user-1", nickname="たかし")
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    write_operation_log(
        action="CREATE_COMMUNITY",
        user_id="user-1",
        community_id="community-1",
    )
    write_operation_log(action="UPDATE_PROFILE", user_id="user-1")

    response = logs.get_user_logs(
        "user-1", api_event(path_params={"userId": "user-1"})
    )

    assert response["statusCode"] == 200
    entries = body_of(response)["data"]["logs"]
    assert len(entries) == 2
    actions = {entry["action"] for entry in entries}
    assert actions == {"CREATE_COMMUNITY", "UPDATE_PROFILE"}
    global_entry = next(e for e in entries if e["action"] == "UPDATE_PROFILE")
    assert global_entry["communityId"] is None
    assert global_entry["displayName"] == "たかし"


def test_get_user_logs_admin_of_shared_community_sees_scoped_logs_only(table):
    put_profile(table, "user-2", nickname="めんばー")
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")
    write_operation_log(
        action="ADD_MEMBER",
        user_id="user-2",
        community_id="community-1",
        target_type="Membership",
        target_id="user-2",
    )
    # user-2の他コミュニティでの操作（user-1は非メンバー・非権限）は見えない。
    write_operation_log(
        action="CREATE_COMMUNITY", user_id="user-2", community_id="community-2"
    )
    write_operation_log(action="UPDATE_PROFILE", user_id="user-2")

    response = logs.get_user_logs(
        "user-1", api_event(path_params={"userId": "user-2"})
    )

    assert response["statusCode"] == 200
    entries = body_of(response)["data"]["logs"]
    assert len(entries) == 1
    assert entries[0]["action"] == "ADD_MEMBER"
    assert entries[0]["communityId"] == "community-1"


def test_get_user_logs_forbidden_when_viewer_has_no_shared_admin_community(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")

    response = logs.get_user_logs(
        "user-2", api_event(path_params={"userId": "user-1"})
    )

    assert response["statusCode"] == 403
    assert body_of(response)["error"]["code"] == "FORBIDDEN"


def test_get_user_logs_member_role_not_sufficient(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")
    write_operation_log(
        action="CREATE_COMMUNITY", user_id="user-1", community_id="community-1"
    )

    response = logs.get_user_logs(
        "user-2", api_event(path_params={"userId": "user-1"})
    )

    assert response["statusCode"] == 403
    assert body_of(response)["error"]["code"] == "FORBIDDEN"
