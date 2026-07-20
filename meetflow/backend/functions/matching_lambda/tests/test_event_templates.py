from handlers import event_templates

from _factories import api_event, body_of, put_membership, put_template


def test_create_template_success(table):
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = event_templates.create_template(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"},
            body={"gameType": "MAHJONG4", "minPlayers": 4, "maxPlayers": 4, "priority": 60},
        ),
    )

    assert response["statusCode"] == 201
    data = body_of(response)["data"]
    assert data["gameType"] == "MAHJONG4"
    assert data["minPlayers"] == 4
    assert data["priority"] == 60


def test_create_template_invalid_player_range(table):
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = event_templates.create_template(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"},
            body={"gameType": "MAHJONG4", "minPlayers": 5, "maxPlayers": 4},
        ),
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "INVALID_PLAYER_RANGE"


def test_create_template_rejects_min_players_below_2(table):
    """Issue #57: minPlayers=1だと1人だけの空き区間が候補化され、相互
    非公開型マッチングの前提が管理者側から破れてしまうため、下限は2人。"""
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = event_templates.create_template(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"},
            body={"gameType": "MAHJONG4", "minPlayers": 1, "maxPlayers": 4},
        ),
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "INVALID_PLAYER_RANGE"


def test_create_template_invalid_game_type(table):
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = event_templates.create_template(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"},
            body={"gameType": "", "minPlayers": 4, "maxPlayers": 4},
        ),
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "INVALID_PARAMETER"


def test_list_templates_success(table):
    put_membership(table, "community-1", "user-1", role="MEMBER")
    put_template(table, "community-1", "template-1", game_type="MAHJONG4")
    put_template(table, "community-1", "template-2", game_type="MAHJONG3")

    response = event_templates.list_templates(
        "user-1", api_event(path_params={"communityId": "community-1"})
    )

    assert response["statusCode"] == 200
    assert len(body_of(response)["data"]["templates"]) == 2


def test_update_template_success(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_template(table, "community-1", "template-1", priority=10)

    response = event_templates.update_template(
        "user-1",
        api_event(
            path_params={"communityId": "community-1", "templateId": "template-1"},
            body={"priority": 90},
        ),
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["priority"] == 90


def test_update_template_not_found(table):
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = event_templates.update_template(
        "user-1",
        api_event(
            path_params={"communityId": "community-1", "templateId": "no-such"},
            body={"priority": 90},
        ),
    )

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "EVENT_TEMPLATE_NOT_FOUND"


def test_delete_template_success(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_template(table, "community-1", "template-1")

    response = event_templates.delete_template(
        "user-1",
        api_event(path_params={"communityId": "community-1", "templateId": "template-1"}),
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["deleted"] is True
    assert (
        table.get_item(
            Key={"PK": "COMMUNITY#community-1", "SK": "TEMPLATE#template-1"}
        ).get("Item")
        is None
    )


def test_delete_template_not_found(table):
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = event_templates.delete_template(
        "user-1",
        api_event(path_params={"communityId": "community-1", "templateId": "no-such"}),
    )

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "EVENT_TEMPLATE_NOT_FOUND"
