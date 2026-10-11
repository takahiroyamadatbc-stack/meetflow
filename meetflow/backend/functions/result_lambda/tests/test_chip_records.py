"""チップ記録（Issue #116）のテスト。"""

import pytest

from meetflow_common import AuthError

from handlers import chip_records, results

from _factories import api_event, body_of, put_event, put_membership


def _chip_body(gameType="MAHJONG4", chips=None):
    return {
        "gameType": gameType,
        "chips": chips
        if chips is not None
        else [
            {"userId": "user-1", "chipCount": 5},
            {"userId": "user-2", "chipCount": -2},
            {"userId": "user-3", "chipCount": -3},
        ],
    }


def _create(table, user_id="user-1", body=None, event_id="event-1"):
    return chip_records.create_chip_record(
        user_id,
        api_event(path_params={"eventId": event_id}, body=body or _chip_body()),
    )


def _setup(table, role="OWNER"):
    put_membership(table, "community-1", "user-1", role=role)
    put_event(table, "event-1", "community-1")


def test_create_chip_record_by_plain_member(table):
    _setup(table, role="MEMBER")

    response = _create(table)

    assert response["statusCode"] == 201
    data = body_of(response)["data"]
    assert data["eventId"] == "event-1"
    assert data["recordNo"] == "0001"
    assert data["gameType"] == "MAHJONG4"
    assert data["chipTotal"] == 0
    assert data["chips"] == [
        {"userId": "user-1", "chipCount": 5},
        {"userId": "user-2", "chipCount": -2},
        {"userId": "user-3", "chipCount": -3},
    ]
    item = table.get_item(
        Key={"PK": "EVENT#event-1", "SK": "CHIPREC#0001#CHIP#user-2"}
    )["Item"]
    assert item["GSI1PK"] == "USER#user-2"
    assert item["GSI2PK"] == "COMMUNITY#community-1#MAHJONG4"
    assert item["gameType"] == "MAHJONG4"


def test_create_chip_record_allows_non_zero_total(table):
    """合計が±0でなくても登録できる（警告はフロントで表示する）。"""
    _setup(table)

    response = _create(
        table,
        body=_chip_body(
            chips=[
                {"userId": "user-1", "chipCount": 5},
                {"userId": "user-2", "chipCount": -2},
            ]
        ),
    )

    assert response["statusCode"] == 201
    assert body_of(response)["data"]["chipTotal"] == 3


def test_create_chip_record_multiple_times_increments_record_no(table):
    _setup(table)
    _create(table)

    response = _create(table)

    assert body_of(response)["data"]["recordNo"] == "0002"


@pytest.mark.parametrize(
    "body",
    [
        {"gameType": "POKER", "chips": [{"userId": "user-1", "chipCount": 1}]},
        {"gameType": "MAHJONG4", "chips": []},
        {"gameType": "MAHJONG4", "chips": [{"userId": "user-1", "chipCount": 1.5}]},
        {"gameType": "MAHJONG4", "chips": [{"userId": "user-1", "chipCount": True}]},
        {
            "gameType": "MAHJONG4",
            "chips": [
                {"userId": "user-1", "chipCount": 1},
                {"userId": "user-1", "chipCount": -1},
            ],
        },
    ],
)
def test_create_chip_record_validation_error(table, body):
    _setup(table)

    response = _create(table, body=body)

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "RESULT_VALIDATION_ERROR"


def test_create_chip_record_event_not_found(table):
    _setup(table)

    response = _create(table, event_id="event-missing")

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "EVENT_NOT_FOUND"


def test_list_chip_records_in_record_order(table):
    _setup(table)
    _create(table)
    _create(table, body=_chip_body(gameType="MAHJONG3"))
    # 半荘（SESSION#）の行は一覧に混ざらない
    results.create_session(
        "user-1",
        api_event(
            path_params={"eventId": "event-1"},
            body={
                "gameType": "MAHJONG4",
                "calcMode": "MANUAL",
                "results": [
                    {"userId": "user-1", "score": 30000},
                    {"userId": "user-2", "score": 20000},
                ],
            },
        ),
    )

    response = chip_records.list_chip_records(
        "user-1", api_event(path_params={"eventId": "event-1"})
    )

    assert response["statusCode"] == 200
    records = body_of(response)["data"]["records"]
    assert [r["recordNo"] for r in records] == ["0001", "0002"]
    assert [r["gameType"] for r in records] == ["MAHJONG4", "MAHJONG3"]
    assert len(records[0]["chips"]) == 3


def test_update_chip_record_replaces_chips_and_keeps_recorded_at(table):
    _setup(table)
    created = body_of(_create(table))["data"]

    response = chip_records.update_chip_record(
        "user-1",
        api_event(
            path_params={"eventId": "event-1", "recordNo": "0001"},
            body=_chip_body(
                gameType="MAHJONG3",
                chips=[
                    {"userId": "user-1", "chipCount": 4},
                    {"userId": "user-2", "chipCount": -4},
                ],
            ),
        ),
    )

    assert response["statusCode"] == 200
    data = body_of(response)["data"]
    assert data["recordedAt"] == created["recordedAt"]
    assert data["gameType"] == "MAHJONG3"
    assert data["chipTotal"] == 0
    # 外された参加者（user-3）の行は削除される
    assert (
        table.get_item(Key={"PK": "EVENT#event-1", "SK": "CHIPREC#0001#CHIP#user-3"}).get(
            "Item"
        )
        is None
    )
    item = table.get_item(
        Key={"PK": "EVENT#event-1", "SK": "CHIPREC#0001#CHIP#user-1"}
    )["Item"]
    assert item["chipCount"] == 4
    assert item["GSI2PK"] == "COMMUNITY#community-1#MAHJONG3"


def test_update_chip_record_forbidden_for_plain_member(table):
    _setup(table)
    put_membership(table, "community-1", "user-2", role="MEMBER")
    _create(table)

    with pytest.raises(AuthError) as exc_info:
        chip_records.update_chip_record(
            "user-2",
            api_event(
                path_params={"eventId": "event-1", "recordNo": "0001"},
                body=_chip_body(),
            ),
        )
    assert exc_info.value.code == "FORBIDDEN"


def test_update_chip_record_not_found(table):
    _setup(table)

    response = chip_records.update_chip_record(
        "user-1",
        api_event(
            path_params={"eventId": "event-1", "recordNo": "0009"},
            body=_chip_body(),
        ),
    )

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "CHIP_RECORD_NOT_FOUND"


def test_delete_chip_record_removes_all_items(table):
    _setup(table)
    _create(table)
    _create(table)

    response = chip_records.delete_chip_record(
        "user-1", api_event(path_params={"eventId": "event-1", "recordNo": "0001"})
    )

    assert response["statusCode"] == 200
    records = body_of(
        chip_records.list_chip_records(
            "user-1", api_event(path_params={"eventId": "event-1"})
        )
    )["data"]["records"]
    assert [r["recordNo"] for r in records] == ["0002"]


def test_delete_chip_record_not_found(table):
    _setup(table)

    response = chip_records.delete_chip_record(
        "user-1", api_event(path_params={"eventId": "event-1", "recordNo": "0001"})
    )

    assert response["statusCode"] == 404


def test_chip_records_are_counted_in_user_results_and_ranking(table):
    """チップ記録は、既存の半荘ごとのチップと同じく個人成績・ランキングの
    totalChipsに集計される（種目ごと）。"""
    _setup(table)
    put_membership(table, "community-1", "user-2")
    results.create_session(
        "user-1",
        api_event(
            path_params={"eventId": "event-1"},
            body={
                "gameType": "MAHJONG4",
                "calcMode": "MANUAL",
                "results": [
                    {"userId": "user-1", "score": 30000},
                    {"userId": "user-2", "score": 20000},
                ],
                "chips": [
                    {"userId": "user-1", "chipCount": 1},
                    {"userId": "user-2", "chipCount": -1},
                ],
            },
        ),
    )
    _create(
        table,
        body=_chip_body(
            chips=[
                {"userId": "user-1", "chipCount": 5},
                {"userId": "user-2", "chipCount": -5},
            ]
        ),
    )
    _create(
        table,
        body=_chip_body(
            gameType="MAHJONG3",
            chips=[
                {"userId": "user-1", "chipCount": 2},
                {"userId": "user-2", "chipCount": -2},
            ],
        ),
    )

    user_results = body_of(
        results.get_user_results(
            "user-1",
            api_event(
                path_params={"userId": "user-1"}, query={"communityId": "community-1"}
            ),
        )
    )["data"]["byGameType"]
    assert user_results["MAHJONG4"]["totalChips"] == 6
    assert user_results["MAHJONG4"]["totalGames"] == 1
    assert user_results["MAHJONG3"]["totalChips"] == 2

    ranking = body_of(
        results.get_community_ranking(
            "user-1",
            api_event(
                path_params={"communityId": "community-1"},
                query={"gameType": "MAHJONG4", "periodType": "ALL_TIME"},
            ),
        )
    )["data"]
    members_by_id = {m["userId"]: m for m in ranking["members"]}
    assert members_by_id["user-1"]["totalChips"] == 6
    assert members_by_id["user-2"]["totalChips"] == -6
