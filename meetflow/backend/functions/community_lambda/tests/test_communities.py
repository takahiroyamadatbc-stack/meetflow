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


def test_get_community_success(table):
    put_community(
        table, "community-1", owner_id="user-1", name="コミュニティA", member_approval_required=True
    )
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = communities.get_community(
        "user-1", api_event(path_params={"communityId": "community-1"})
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"] == {
        "communityId": "community-1",
        "name": "コミュニティA",
        "description": "",
        "genre": "麻雀",
        "memberApprovalRequired": True,
        "themeColor": None,
        "role": "OWNER",
    }


def test_get_community_forbidden_for_non_member(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    with pytest.raises(AuthError) as exc_info:
        communities.get_community(
            "user-2", api_event(path_params={"communityId": "community-1"})
        )
    assert exc_info.value.code == "FORBIDDEN"


def test_list_communities_success(table):
    put_community(table, "community-1", owner_id="user-1", name="コミュニティA", theme_color="#6366F1")
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
            "themeColor": "#6366F1",
        }
    ]


def test_list_communities_sorted_by_sort_order(table):
    """#16: sortOrderが設定されていれば昇順に並び、未設定のものは末尾に回る。"""
    put_community(table, "community-1", owner_id="user-1", name="コミュニティA")
    put_community(table, "community-2", owner_id="user-1", name="コミュニティB")
    put_community(table, "community-3", owner_id="user-1", name="コミュニティC")
    put_membership(table, "community-1", "user-1", role="OWNER", sort_order=1)
    put_membership(table, "community-2", "user-1", role="OWNER", sort_order=0)
    put_membership(table, "community-3", "user-1", role="OWNER")  # sortOrder未設定

    response = communities.list_communities("user-1", api_event())

    ids = [c["communityId"] for c in body_of(response)["data"]["communities"]]
    assert ids == ["community-2", "community-1", "community-3"]


def test_reorder_communities_success(table):
    put_community(table, "community-1", owner_id="user-1")
    put_community(table, "community-2", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-2", "user-1", role="OWNER")

    response = communities.reorder_communities(
        "user-1", api_event(body={"communityIds": ["community-2", "community-1"]})
    )

    assert response["statusCode"] == 200
    list_response = communities.list_communities("user-1", api_event())
    ids = [c["communityId"] for c in body_of(list_response)["data"]["communities"]]
    assert ids == ["community-2", "community-1"]


def test_reorder_communities_forbidden_for_non_member(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    with pytest.raises(AuthError) as exc_info:
        communities.reorder_communities(
            "user-2", api_event(body={"communityIds": ["community-1"]})
        )
    assert exc_info.value.code == "FORBIDDEN"


def test_reorder_communities_invalid_parameter(table):
    response = communities.reorder_communities("user-1", api_event(body={"communityIds": []}))

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "INVALID_PARAMETER"


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


def test_create_community_with_theme_color(table):
    event = api_event(body={"name": "火曜麻雀会", "themeColor": "#6366F1"})

    response = communities.create_community("user-1", event)

    assert response["statusCode"] == 201
    data = body_of(response)["data"]
    assert data["themeColor"] == "#6366F1"
    community = table.get_item(
        Key={"PK": f"COMMUNITY#{data['communityId']}", "SK": "METADATA"}
    )["Item"]
    assert community["themeColor"] == "#6366F1"


@pytest.mark.parametrize("theme_color", ["red", "#FFF", "#GGGGGG", "6366F1"])
def test_create_community_invalid_theme_color(table, theme_color):
    event = api_event(body={"name": "火曜麻雀会", "themeColor": theme_color})

    response = communities.create_community("user-1", event)

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "INVALID_PARAMETER"


def test_update_theme_color_success(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = communities.update_theme_color(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"themeColor": "#22C55E"}
        ),
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"] == {
        "communityId": "community-1",
        "themeColor": "#22C55E",
    }
    community = table.get_item(
        Key={"PK": "COMMUNITY#community-1", "SK": "METADATA"}
    )["Item"]
    assert community["themeColor"] == "#22C55E"


def test_update_theme_color_clear(table):
    put_community(table, "community-1", owner_id="user-1", theme_color="#22C55E")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = communities.update_theme_color(
        "user-1",
        api_event(path_params={"communityId": "community-1"}, body={"themeColor": ""}),
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"] == {"communityId": "community-1", "themeColor": None}
    community = table.get_item(
        Key={"PK": "COMMUNITY#community-1", "SK": "METADATA"}
    )["Item"]
    assert "themeColor" not in community


def test_update_theme_color_invalid_format(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = communities.update_theme_color(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"themeColor": "not-a-color"}
        ),
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "INVALID_PARAMETER"


def test_update_theme_color_forbidden_for_plain_member(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-2", role="MEMBER")

    with pytest.raises(AuthError) as exc_info:
        communities.update_theme_color(
            "user-2",
            api_event(
                path_params={"communityId": "community-1"}, body={"themeColor": "#22C55E"}
            ),
        )
    assert exc_info.value.code == "FORBIDDEN"


def test_delete_community_success(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = communities.delete_community(
        "user-1", api_event(path_params={"communityId": "community-1"})
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"] == {"communityId": "community-1", "deleted": True}
    assert (
        table.get_item(Key={"PK": "COMMUNITY#community-1", "SK": "METADATA"}).get("Item")
        is None
    )
    assert (
        table.get_item(
            Key={"PK": "COMMUNITY#community-1", "SK": "MEMBER#user-1"}
        ).get("Item")
        is None
    )


def test_delete_community_rejected_when_other_members_exist(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")

    response = communities.delete_community(
        "user-1", api_event(path_params={"communityId": "community-1"})
    )

    assert response["statusCode"] == 409
    assert body_of(response)["error"]["code"] == "COMMUNITY_NOT_EMPTY"
    # 拒否された場合はコミュニティ・メンバーシップともに残ったまま。
    assert (
        table.get_item(Key={"PK": "COMMUNITY#community-1", "SK": "METADATA"}).get("Item")
        is not None
    )


def test_delete_community_forbidden_for_plain_member(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")

    with pytest.raises(AuthError) as exc_info:
        communities.delete_community(
            "user-2", api_event(path_params={"communityId": "community-1"})
        )
    assert exc_info.value.code == "FORBIDDEN"


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
