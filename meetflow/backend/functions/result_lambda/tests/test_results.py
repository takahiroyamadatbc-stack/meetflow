from handlers import results

from _factories import api_event, body_of, put_event, put_membership


def test_create_session_success(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_event(table, "event-1", "community-1")

    response = results.create_session(
        "user-1",
        api_event(
            path_params={"eventId": "event-1"},
            body={
                "gameType": "MAHJONG4",
                "results": [
                    {"userId": "user-1", "rank": 1, "score": 45000, "rankPoints": 30},
                    {"userId": "user-2", "rank": 2, "score": 20000, "rankPoints": 10},
                    {"userId": "user-3", "rank": 3, "score": 15000, "rankPoints": -10},
                    {"userId": "user-4", "rank": 4, "score": 20000, "rankPoints": -30},
                ],
            },
        ),
    )

    assert response["statusCode"] == 201
    data = body_of(response)["data"]
    assert data["sessionNo"] == "0001"
    assert [r["userId"] for r in data["results"]] == [
        "user-1",
        "user-2",
        "user-3",
        "user-4",
    ]
    stored = table.get_item(
        Key={"PK": "EVENT#event-1", "SK": "SESSION#0001#RESULT#user-1"}
    )["Item"]
    assert stored["rank"] == 1


def test_create_session_increments_session_no(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_event(table, "event-1", "community-1")
    body = {
        "gameType": "MAHJONG4",
        "results": [{"userId": "user-1", "rank": 1, "score": 100}],
    }
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
            body={"gameType": "MAHJONG4", "results": [{"userId": "user-1", "rank": 1, "score": 1}]},
        ),
    )

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "EVENT_NOT_FOUND"


def test_create_session_duplicate_ranks(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_event(table, "event-1", "community-1")

    response = results.create_session(
        "user-1",
        api_event(
            path_params={"eventId": "event-1"},
            body={
                "gameType": "MAHJONG4",
                "results": [
                    {"userId": "user-1", "rank": 1, "score": 100},
                    {"userId": "user-2", "rank": 1, "score": 90},
                ],
            },
        ),
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "RESULT_VALIDATION_ERROR"


def test_create_session_non_sequential_ranks(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_event(table, "event-1", "community-1")

    response = results.create_session(
        "user-1",
        api_event(
            path_params={"eventId": "event-1"},
            body={
                "gameType": "MAHJONG4",
                "results": [
                    {"userId": "user-1", "rank": 1, "score": 100},
                    {"userId": "user-2", "rank": 3, "score": 90},
                ],
            },
        ),
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "RESULT_VALIDATION_ERROR"


def test_get_user_results_success(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")
    put_event(table, "event-1", "community-1")
    results.create_session(
        "user-1",
        api_event(
            path_params={"eventId": "event-1"},
            body={
                "gameType": "MAHJONG4",
                "results": [
                    {"userId": "user-2", "rank": 1, "score": 45000, "rankPoints": 30},
                ],
            },
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
    assert data["totalGames"] == 1
    assert data["averageRank"] == 1
    assert data["firstPlaceRate"] == 1
    assert data["totalPoints"] == 30


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
    assert body_of(response)["data"]["totalGames"] == 0
