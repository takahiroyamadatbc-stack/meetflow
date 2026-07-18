import pytest

from meetflow_common import AuthError

from handlers import results

from _factories import api_event, body_of, put_event, put_membership


def _manual_body(gameType="MAHJONG4", results_list=None):
    return {
        "gameType": gameType,
        "calcMode": "MANUAL",
        "results": results_list
        or [
            {"userId": "user-1", "score": 45000},
            {"userId": "user-2", "score": 25000},
            {"userId": "user-3", "score": 20000},
            {"userId": "user-4", "score": 10000},
        ],
    }


def _auto_body():
    return {
        "gameType": "MAHJONG4",
        "calcMode": "AUTO",
        "startingPoints": 25000,
        "returnPoints": 30000,
        "umaByRank": [20, 10, -10, -20],
        "results": [
            {"userId": "user-1", "score": 45000},
            {"userId": "user-2", "score": 25000},
            {"userId": "user-3", "score": 20000},
            {"userId": "user-4", "score": 10000},
        ],
    }


def test_create_session_manual_derives_rank_from_score(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_event(table, "event-1", "community-1")

    response = results.create_session(
        "user-1",
        api_event(path_params={"eventId": "event-1"}, body=_manual_body()),
    )

    assert response["statusCode"] == 201
    data = body_of(response)["data"]
    assert data["sessionNo"] == "0001"
    assert [(r["userId"], r["rank"]) for r in data["results"]] == [
        ("user-1", 1),
        ("user-2", 2),
        ("user-3", 3),
        ("user-4", 4),
    ]
    # MANUAL時はrankPointsを一切計算せず常に0
    assert all(r["rankPoints"] == 0 for r in data["results"])
    stored = table.get_item(
        Key={"PK": "EVENT#event-1", "SK": "SESSION#0001#RESULT#user-1"}
    )["Item"]
    assert stored["rank"] == 1


def test_create_session_auto_calculates_uma_oka(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_event(table, "event-1", "community-1")

    response = results.create_session(
        "user-1",
        api_event(path_params={"eventId": "event-1"}, body=_auto_body()),
    )

    assert response["statusCode"] == 201
    data = body_of(response)["data"]
    points_by_user = {r["userId"]: float(r["rankPoints"]) for r in data["results"]}
    # 配給原点25000・返し点30000・ウマ[20,10,-10,-20]、
    # 合計点=100000（=25000*4、オカは(30000-25000)*4/1000=20を1位に加算）
    assert points_by_user["user-1"] == 55.0  # (45000-30000)/1000 + 20 + 20
    assert points_by_user["user-2"] == 5.0  # (25000-30000)/1000 + 10
    assert points_by_user["user-3"] == -20.0  # (20000-30000)/1000 - 10
    assert points_by_user["user-4"] == -40.0  # (10000-30000)/1000 - 20


def test_create_session_increments_session_no(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_event(table, "event-1", "community-1")
    body = _manual_body(results_list=[{"userId": "user-1", "score": 100}])
    results.create_session(
        "user-1", api_event(path_params={"eventId": "event-1"}, body=body)
    )

    response = results.create_session(
        "user-1", api_event(path_params={"eventId": "event-1"}, body=body)
    )

    assert body_of(response)["data"]["sessionNo"] == "0002"


def test_create_session_event_not_found(table):
    response = results.create_session(
        "user-1",
        api_event(
            path_params={"eventId": "does-not-exist"},
            body=_manual_body(results_list=[{"userId": "user-1", "score": 1}]),
        ),
    )

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "EVENT_NOT_FOUND"


def test_create_session_allows_member_role(table):
    """OWNER/ADMINに限らず、アクティブなMEMBERも半荘の登録（確定）ができる。"""
    put_membership(table, "community-1", "user-1", role="MEMBER")
    put_event(table, "event-1", "community-1")

    response = results.create_session(
        "user-1",
        api_event(path_params={"eventId": "event-1"}, body=_manual_body()),
    )

    assert response["statusCode"] == 201


def test_create_session_requires_membership(table):
    put_event(table, "event-1", "community-1")

    with pytest.raises(AuthError) as exc_info:
        results.create_session(
            "user-1",
            api_event(path_params={"eventId": "event-1"}, body=_manual_body()),
        )
    assert exc_info.value.code == "FORBIDDEN"


def test_create_session_duplicate_user_ids(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_event(table, "event-1", "community-1")

    response = results.create_session(
        "user-1",
        api_event(
            path_params={"eventId": "event-1"},
            body=_manual_body(
                results_list=[
                    {"userId": "user-1", "score": 100},
                    {"userId": "user-1", "score": 90},
                ]
            ),
        ),
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "RESULT_VALIDATION_ERROR"


def test_create_session_auto_requires_uma_length_match(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_event(table, "event-1", "community-1")

    body = _auto_body()
    body["umaByRank"] = [20, 10, -10]  # 4人分のはずが3件しかない

    response = results.create_session(
        "user-1", api_event(path_params={"eventId": "event-1"}, body=body)
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "RESULT_VALIDATION_ERROR"


def test_create_session_with_chips(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_event(table, "event-1", "community-1")

    body = _manual_body()
    body["chips"] = [
        {"userId": "user-1", "chipCount": 3},
        {"userId": "user-2", "chipCount": -1},
    ]

    response = results.create_session(
        "user-1", api_event(path_params={"eventId": "event-1"}, body=body)
    )

    assert response["statusCode"] == 201
    data = body_of(response)["data"]
    chips_by_user = {c["userId"]: c["chipCount"] for c in data["chips"]}
    assert chips_by_user == {"user-1": 3, "user-2": -1}


def test_create_session_chip_for_unknown_user_rejected(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_event(table, "event-1", "community-1")

    body = _manual_body()
    body["chips"] = [{"userId": "not-a-participant", "chipCount": 1}]

    response = results.create_session(
        "user-1", api_event(path_params={"eventId": "event-1"}, body=body)
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "RESULT_VALIDATION_ERROR"


def test_update_session_overwrites_values(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_event(table, "event-1", "community-1")
    results.create_session(
        "user-1",
        api_event(path_params={"eventId": "event-1"}, body=_manual_body()),
    )

    new_body = _manual_body(
        results_list=[
            {"userId": "user-1", "score": 10000},
            {"userId": "user-2", "score": 45000},
            {"userId": "user-3", "score": 25000},
            {"userId": "user-4", "score": 20000},
        ]
    )
    response = results.update_session(
        "user-1",
        api_event(
            path_params={"eventId": "event-1", "sessionNo": "0001"}, body=new_body
        ),
    )

    assert response["statusCode"] == 200
    data = body_of(response)["data"]
    ranks_by_user = {r["userId"]: r["rank"] for r in data["results"]}
    assert ranks_by_user["user-2"] == 1
    assert ranks_by_user["user-1"] == 4


def test_update_session_not_found(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_event(table, "event-1", "community-1")

    response = results.update_session(
        "user-1",
        api_event(
            path_params={"eventId": "event-1", "sessionNo": "9999"},
            body=_manual_body(),
        ),
    )

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "GAME_SESSION_NOT_FOUND"


def test_update_session_rejects_different_participants(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_event(table, "event-1", "community-1")
    results.create_session(
        "user-1",
        api_event(path_params={"eventId": "event-1"}, body=_manual_body()),
    )

    response = results.update_session(
        "user-1",
        api_event(
            path_params={"eventId": "event-1", "sessionNo": "0001"},
            body=_manual_body(
                results_list=[
                    {"userId": "user-1", "score": 100},
                    {"userId": "user-5", "score": 50},
                ]
            ),
        ),
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "RESULT_VALIDATION_ERROR"


def test_update_session_requires_admin_role(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")
    put_event(table, "event-1", "community-1")
    results.create_session(
        "user-1",
        api_event(path_params={"eventId": "event-1"}, body=_manual_body()),
    )

    with pytest.raises(AuthError) as exc_info:
        results.update_session(
            "user-2",
            api_event(
                path_params={"eventId": "event-1", "sessionNo": "0001"},
                body=_manual_body(),
            ),
        )
    assert exc_info.value.code == "FORBIDDEN"


def test_delete_session_removes_session_result_and_chip_items(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_event(table, "event-1", "community-1")
    body = _manual_body()
    body["chips"] = [{"userId": "user-1", "chipCount": 2}]
    results.create_session(
        "user-1", api_event(path_params={"eventId": "event-1"}, body=body)
    )

    response = results.delete_session(
        "user-1",
        api_event(path_params={"eventId": "event-1", "sessionNo": "0001"}),
    )

    assert response["statusCode"] == 200
    data = body_of(response)["data"]
    assert data == {"eventId": "event-1", "sessionNo": "0001"}
    assert (
        table.get_item(Key={"PK": "EVENT#event-1", "SK": "SESSION#0001"}).get("Item")
        is None
    )
    assert (
        table.get_item(
            Key={"PK": "EVENT#event-1", "SK": "SESSION#0001#RESULT#user-1"}
        ).get("Item")
        is None
    )
    assert (
        table.get_item(
            Key={"PK": "EVENT#event-1", "SK": "SESSION#0001#CHIP#user-1"}
        ).get("Item")
        is None
    )
    remaining = results.list_event_sessions(
        "user-1", api_event(path_params={"eventId": "event-1"})
    )
    assert body_of(remaining)["data"]["sessions"] == []


def test_delete_session_not_found(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_event(table, "event-1", "community-1")

    response = results.delete_session(
        "user-1",
        api_event(path_params={"eventId": "event-1", "sessionNo": "9999"}),
    )

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "GAME_SESSION_NOT_FOUND"


def test_delete_session_requires_admin_role(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")
    put_event(table, "event-1", "community-1")
    results.create_session(
        "user-1",
        api_event(path_params={"eventId": "event-1"}, body=_manual_body()),
    )

    with pytest.raises(AuthError) as exc_info:
        results.delete_session(
            "user-2",
            api_event(path_params={"eventId": "event-1", "sessionNo": "0001"}),
        )
    assert exc_info.value.code == "FORBIDDEN"


def test_delete_session_leaves_other_sessions_intact(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_event(table, "event-1", "community-1")
    results.create_session(
        "user-1",
        api_event(path_params={"eventId": "event-1"}, body=_manual_body()),
    )
    results.create_session(
        "user-1",
        api_event(path_params={"eventId": "event-1"}, body=_manual_body()),
    )

    response = results.delete_session(
        "user-1",
        api_event(path_params={"eventId": "event-1", "sessionNo": "0001"}),
    )

    assert response["statusCode"] == 200
    remaining = results.list_event_sessions(
        "user-1", api_event(path_params={"eventId": "event-1"})
    )
    sessions = body_of(remaining)["data"]["sessions"]
    assert [s["sessionNo"] for s in sessions] == ["0002"]


def test_list_event_sessions_returns_grouped_data(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")
    put_event(table, "event-1", "community-1")
    body = _manual_body()
    body["chips"] = [{"userId": "user-1", "chipCount": 2}]
    results.create_session(
        "user-1", api_event(path_params={"eventId": "event-1"}, body=body)
    )

    # 参加者（非管理者）でも閲覧できる
    response = results.list_event_sessions(
        "user-2", api_event(path_params={"eventId": "event-1"})
    )

    assert response["statusCode"] == 200
    sessions = body_of(response)["data"]["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["sessionNo"] == "0001"
    assert len(sessions[0]["results"]) == 4
    assert sessions[0]["chips"] == [{"userId": "user-1", "chipCount": 2}]


def test_get_last_game_settings_found(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_event(table, "event-1", "community-1")
    results.create_session(
        "user-1",
        api_event(path_params={"eventId": "event-1"}, body=_auto_body()),
    )

    response = results.get_last_game_settings(
        "user-1", api_event(path_params={"communityId": "community-1"})
    )

    assert response["statusCode"] == 200
    data = body_of(response)["data"]
    assert data["found"] is True
    assert data["calcMode"] == "AUTO"
    assert int(data["startingPoints"]) == 25000
    assert [int(v) for v in data["umaByRank"]] == [20, 10, -10, -20]


def test_get_last_game_settings_not_found(table):
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = results.get_last_game_settings(
        "user-1", api_event(path_params={"communityId": "community-1"})
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["found"] is False


def test_get_user_results_success(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")
    put_event(table, "event-1", "community-1")
    results.create_session(
        "user-1",
        api_event(
            path_params={"eventId": "event-1"},
            body=_manual_body(results_list=[{"userId": "user-2", "score": 45000}]),
        ),
    )

    response = results.get_user_results(
        "user-1",
        api_event(
            path_params={"userId": "user-2"}, query={"communityId": "community-1"}
        ),
    )

    assert response["statusCode"] == 200
    data = body_of(response)["data"]
    mahjong4 = data["byGameType"]["MAHJONG4"]
    assert mahjong4["totalGames"] == 1
    assert mahjong4["averageRank"] == 1
    assert mahjong4["firstPlaceRate"] == 1
    assert data["byGameType"]["MAHJONG3"]["totalGames"] == 0


def test_get_user_results_excludes_chip_rows_from_stats(table):
    """GameResultChipがGameResultと同じGSI1プレフィックスを共有するため、
    誤ってstats集計に混入しないことの回帰テスト。"""
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")
    put_event(table, "event-1", "community-1")
    body = _manual_body(results_list=[{"userId": "user-2", "score": 45000}])
    body["chips"] = [{"userId": "user-2", "chipCount": 7}]
    results.create_session(
        "user-1", api_event(path_params={"eventId": "event-1"}, body=body)
    )

    response = results.get_user_results(
        "user-1",
        api_event(
            path_params={"userId": "user-2"}, query={"communityId": "community-1"}
        ),
    )

    data = body_of(response)["data"]["byGameType"]["MAHJONG4"]
    # Chip行が幻の対局としてtotalGamesに混入していないこと
    assert data["totalGames"] == 1
    assert data["totalChips"] == 7


def test_get_user_results_excludes_not_yet_completed_events(table):
    """管理者が「本日の対局を終了する」（Event.status→COMPLETED）を押すまでは、
    その対局の成績はコミュニティの通算成績（＝ランキングの原資）に反映されない。
    """
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")
    put_event(table, "event-completed", "community-1", status="COMPLETED")
    put_event(table, "event-confirmed", "community-1", status="CONFIRMED")
    results.create_session(
        "user-1",
        api_event(
            path_params={"eventId": "event-completed"},
            body=_manual_body(results_list=[{"userId": "user-2", "score": 45000}]),
        ),
    )
    body = _manual_body(results_list=[{"userId": "user-2", "score": 10000}])
    body["chips"] = [{"userId": "user-2", "chipCount": 3}]
    results.create_session(
        "user-1", api_event(path_params={"eventId": "event-confirmed"}, body=body)
    )

    response = results.get_user_results(
        "user-1",
        api_event(
            path_params={"userId": "user-2"}, query={"communityId": "community-1"}
        ),
    )

    data = body_of(response)["data"]["byGameType"]["MAHJONG4"]
    # CONFIRMEDのまま終了していないevent-confirmedの1半荘・チップは集計対象外
    assert data["totalGames"] == 1
    assert data["totalChips"] == 0


def test_get_user_results_separates_by_game_type(table):
    """四麻と三麻は着順のスケールが異なるため、averageRank等を混ぜて集計しない。"""
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")
    put_event(table, "event-1", "community-1")
    results.create_session(
        "user-1",
        api_event(
            path_params={"eventId": "event-1"},
            body=_manual_body(
                gameType="MAHJONG4",
                results_list=[
                    {"userId": "user-2", "score": 10000},
                    {"userId": "user-3", "score": 45000},
                    {"userId": "user-4", "score": 25000},
                    {"userId": "user-5", "score": 20000},
                ],
            ),
        ),
    )
    results.create_session(
        "user-1",
        api_event(
            path_params={"eventId": "event-1"},
            body=_manual_body(
                gameType="MAHJONG3",
                results_list=[
                    {"userId": "user-2", "score": 45000},
                    {"userId": "user-3", "score": 30000},
                    {"userId": "user-4", "score": 25000},
                ],
            ),
        ),
    )

    response = results.get_user_results(
        "user-1",
        api_event(
            path_params={"userId": "user-2"}, query={"communityId": "community-1"}
        ),
    )

    data = body_of(response)["data"]["byGameType"]
    assert data["MAHJONG4"]["totalGames"] == 1
    assert data["MAHJONG4"]["averageRank"] == 4
    assert data["MAHJONG3"]["totalGames"] == 1
    assert data["MAHJONG3"]["averageRank"] == 1


def test_get_user_results_missing_community_id(table):
    response = results.get_user_results(
        "user-1", api_event(path_params={"userId": "user-2"})
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "INVALID_PARAMETER"


def test_get_user_results_access_denied_when_not_shared_community(table):
    put_membership(table, "community-1", "user-2", role="MEMBER")

    response = results.get_user_results(
        "user-1",
        api_event(
            path_params={"userId": "user-2"}, query={"communityId": "community-1"}
        ),
    )

    assert response["statusCode"] == 403
    assert body_of(response)["error"]["code"] == "RESULT_ACCESS_DENIED"


def test_get_user_results_no_games_returns_zeroed_stats(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")

    response = results.get_user_results(
        "user-1",
        api_event(
            path_params={"userId": "user-2"}, query={"communityId": "community-1"}
        ),
    )

    assert response["statusCode"] == 200
    data = body_of(response)["data"]
    assert data["byGameType"]["MAHJONG4"]["totalGames"] == 0
    assert data["byGameType"]["MAHJONG3"]["totalGames"] == 0
