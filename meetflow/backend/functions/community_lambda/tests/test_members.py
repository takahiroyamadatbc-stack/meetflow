import pytest
from meetflow_common import AuthError, add_days_iso, now_iso_ms

from handlers import members

from _factories import api_event, body_of, put_community, put_membership, put_profile


def _put_event(table, event_id, *, community_id, start_time, end_time=None, status="CONFIRMED"):
    table.put_item(
        Item={
            "PK": f"EVENT#{event_id}",
            "SK": "METADATA",
            "GSI1PK": f"COMMUNITY#{community_id}",
            "GSI1SK": f"EVENT#{start_time}#{event_id}",
            "status": status,
            "startTime": start_time,
            "endTime": end_time or start_time,
            "createdAt": now_iso_ms(),
        }
    )


def _put_participant(table, event_id, user_id, *, start_time, status="CONFIRMED"):
    table.put_item(
        Item={
            "PK": f"EVENT#{event_id}",
            "SK": f"PARTICIPANT#{user_id}",
            "GSI1PK": f"USER#{user_id}",
            "GSI1SK": f"PARTICIPANT#{start_time}#{event_id}",
            "status": status,
            "startTime": start_time,
            "joinedAt": now_iso_ms(),
        }
    )


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


def test_list_members_includes_icon_bio_and_game_types(table):
    """Issue #48: メンバー一覧の簡易表示(アイコン)・詳細表示(自己紹介等)の
    両方に使うプロフィール項目を返すこと。
    """
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_profile(
        table,
        "user-1",
        nickname="オーナー太郎",
        icon="https://avatars.example.com/user-1.webp",
        bio="麻雀が好きです",
        game_types=["MAHJONG4"],
    )

    response = members.list_members(
        "user-1", api_event(path_params={"communityId": "community-1"})
    )

    member = body_of(response)["data"]["members"][0]
    assert member["icon"] == "https://avatars.example.com/user-1.webp"
    assert member["bio"] == "麻雀が好きです"
    assert member["gameTypes"] == ["MAHJONG4"]


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


def test_update_my_frequency_limit_set(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = members.update_my_frequency_limit(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"},
            body={"frequencyLimitCount": 2, "frequencyLimitPeriod": "MONTH"},
        ),
    )

    assert response["statusCode"] == 200
    data = body_of(response)["data"]
    assert data["frequencyLimitCount"] == 2
    assert data["frequencyLimitPeriod"] == "MONTH"
    membership = table.get_item(
        Key={"PK": "COMMUNITY#community-1", "SK": "MEMBER#user-1"}
    )["Item"]
    assert membership["frequencyLimitCount"] == 2
    assert membership["frequencyLimitPeriod"] == "MONTH"


def test_update_my_frequency_limit_clear_reverts_to_fallback(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    members.update_my_frequency_limit(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"},
            body={"frequencyLimitCount": 1, "frequencyLimitPeriod": "WEEK"},
        ),
    )

    response = members.update_my_frequency_limit(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"},
            body={"frequencyLimitCount": None, "frequencyLimitPeriod": None},
        ),
    )

    assert response["statusCode"] == 200
    membership = table.get_item(
        Key={"PK": "COMMUNITY#community-1", "SK": "MEMBER#user-1"}
    )["Item"]
    assert "frequencyLimitCount" not in membership
    assert "frequencyLimitPeriod" not in membership


def test_update_my_frequency_limit_partial_only_count_error(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = members.update_my_frequency_limit(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"frequencyLimitCount": 2}
        ),
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "FREQUENCY_LIMIT_VALIDATION_ERROR"


def test_update_my_frequency_limit_partial_only_period_error(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = members.update_my_frequency_limit(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"},
            body={"frequencyLimitPeriod": "WEEK"},
        ),
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "FREQUENCY_LIMIT_VALIDATION_ERROR"


def test_update_my_frequency_limit_non_positive_count(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = members.update_my_frequency_limit(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"},
            body={"frequencyLimitCount": 0, "frequencyLimitPeriod": "WEEK"},
        ),
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "FREQUENCY_LIMIT_VALIDATION_ERROR"


def test_update_my_frequency_limit_invalid_period(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = members.update_my_frequency_limit(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"},
            body={"frequencyLimitCount": 2, "frequencyLimitPeriod": "YEAR"},
        ),
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "FREQUENCY_LIMIT_VALIDATION_ERROR"


def test_leave_community_success(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")

    response = members.leave_community(
        "user-2", api_event(path_params={"communityId": "community-1"})
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["left"] is True
    assert (
        table.get_item(Key={"PK": "COMMUNITY#community-1", "SK": "MEMBER#user-2"}).get(
            "Item"
        )
        is None
    )


def test_leave_community_last_owner_cannot_leave(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = members.leave_community(
        "user-1", api_event(path_params={"communityId": "community-1"})
    )

    assert response["statusCode"] == 409
    assert body_of(response)["error"]["code"] == "LAST_OWNER_CANNOT_LEAVE"


def test_leave_community_blocked_by_upcoming_confirmed_event(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")
    future = add_days_iso(now_iso_ms(), 7)
    _put_event(table, "event-1", community_id="community-1", start_time=future)
    _put_participant(table, "event-1", "user-2", start_time=future, status="CONFIRMED")

    response = members.leave_community(
        "user-2", api_event(path_params={"communityId": "community-1"})
    )

    assert response["statusCode"] == 409
    assert body_of(response)["error"]["code"] == "MEMBER_HAS_UPCOMING_EVENTS"
    assert (
        table.get_item(Key={"PK": "COMMUNITY#community-1", "SK": "MEMBER#user-2"}).get(
            "Item"
        )
        is not None
    )


def test_leave_community_blocked_by_upcoming_awaiting_approval_event(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")
    future = add_days_iso(now_iso_ms(), 7)
    _put_event(table, "event-1", community_id="community-1", start_time=future)
    _put_participant(
        table, "event-1", "user-2", start_time=future, status="AWAITING_APPROVAL"
    )

    response = members.leave_community(
        "user-2", api_event(path_params={"communityId": "community-1"})
    )

    assert response["statusCode"] == 409
    assert body_of(response)["error"]["code"] == "MEMBER_HAS_UPCOMING_EVENTS"


def test_leave_community_not_blocked_by_past_event(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")
    past = add_days_iso(now_iso_ms(), -7)
    _put_event(table, "event-1", community_id="community-1", start_time=past)
    _put_participant(table, "event-1", "user-2", start_time=past, status="CONFIRMED")

    response = members.leave_community(
        "user-2", api_event(path_params={"communityId": "community-1"})
    )

    assert response["statusCode"] == 200


def test_leave_community_not_blocked_by_cancelled_event(table):
    """Issue #63: イベント全体が中止（CANCELLED）された場合、残留した
    Participant.status（CONFIRMED/AWAITING_APPROVAL）だけを見て予約済みと
    誤判定しないこと（親Event.statusも併せて確認する）。
    """
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")
    future = add_days_iso(now_iso_ms(), 7)
    _put_event(table, "event-1", community_id="community-1", start_time=future, status="CANCELLED")
    _put_participant(table, "event-1", "user-2", start_time=future, status="CONFIRMED")

    response = members.leave_community(
        "user-2", api_event(path_params={"communityId": "community-1"})
    )

    assert response["statusCode"] == 200


def test_leave_community_not_blocked_by_other_community_event(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")
    future = add_days_iso(now_iso_ms(), 7)
    _put_event(table, "event-1", community_id="community-other", start_time=future)
    _put_participant(table, "event-1", "user-2", start_time=future, status="CONFIRMED")

    response = members.leave_community(
        "user-2", api_event(path_params={"communityId": "community-1"})
    )

    assert response["statusCode"] == 200


def test_leave_community_not_a_member(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    with pytest.raises(AuthError) as exc_info:
        members.leave_community(
            "user-2", api_event(path_params={"communityId": "community-1"})
        )
    assert exc_info.value.code == "FORBIDDEN"


def test_update_member_remove_blocked_by_upcoming_event(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")
    future = add_days_iso(now_iso_ms(), 7)
    _put_event(table, "event-1", community_id="community-1", start_time=future)
    _put_participant(table, "event-1", "user-2", start_time=future, status="CONFIRMED")

    response = members.update_member(
        "user-1",
        api_event(
            path_params={"communityId": "community-1", "userId": "user-2"},
            body={"remove": True},
        ),
    )

    assert response["statusCode"] == 409
    assert body_of(response)["error"]["code"] == "MEMBER_HAS_UPCOMING_EVENTS"
    assert (
        table.get_item(Key={"PK": "COMMUNITY#community-1", "SK": "MEMBER#user-2"}).get(
            "Item"
        )
        is not None
    )


def test_update_my_frequency_limit_not_a_member(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    with pytest.raises(AuthError) as exc_info:
        members.update_my_frequency_limit(
            "user-2",
            api_event(
                path_params={"communityId": "community-1"},
                body={"frequencyLimitCount": 2, "frequencyLimitPeriod": "WEEK"},
            ),
        )
    assert exc_info.value.code == "FORBIDDEN"
