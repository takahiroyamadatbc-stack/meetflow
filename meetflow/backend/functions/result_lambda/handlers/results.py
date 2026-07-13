from boto3.dynamodb.conditions import Key

from meetflow_common import (
    error_response,
    get_table,
    now_iso_ms,
    parse_body,
    require_membership,
    success_response,
    write_operation_log,
)


def create_session(user_id, event):
    """F-801〜F-803 (API設計書v1.4 §10.1).

    Whether COMPLETED status should be required before results can be
    registered (`EVENT_NOT_COMPLETED`) is explicitly left open in
    エラーコード一覧v1.1 §7 ("実装方針次第で許可する場合は不要。要検討") --
    left unenforced here so mid-event/session-by-session score entry isn't
    blocked, rather than locking in a policy the docs haven't settled on.
    """
    event_id = event["pathParameters"]["eventId"]
    table = get_table()
    event_item = table.get_item(Key={"PK": f"EVENT#{event_id}", "SK": "METADATA"}).get(
        "Item"
    )
    if event_item is None:
        return error_response("EVENT_NOT_FOUND", "指定したイベントが見つかりません")
    community_id = event_item["GSI1PK"].split("#", 1)[1]
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    body = parse_body(event)
    game_type = body.get("gameType")
    results = body.get("results")
    validation_error = _validate_results(game_type, results)
    if validation_error:
        return validation_error

    session_no = _next_session_no(table, event_id)
    played_at = now_iso_ms()

    table.put_item(
        Item={
            "PK": f"EVENT#{event_id}",
            "SK": f"SESSION#{session_no}",
            "gameType": game_type,
            "playedAt": played_at,
        }
    )

    ranked_results = sorted(results, key=lambda r: r["rank"])
    for r in ranked_results:
        table.put_item(
            Item={
                "PK": f"EVENT#{event_id}",
                "SK": f"SESSION#{session_no}#RESULT#{r['userId']}",
                "GSI1PK": f"USER#{r['userId']}",
                "GSI1SK": f"COMMUNITY#{community_id}#{played_at}",
                "rank": r["rank"],
                "score": r["score"],
                "rankPoints": r.get("rankPoints", 0),
                "playedAt": played_at,
            }
        )

    write_operation_log(
        action="CREATE_GAME_SESSION",
        user_id=user_id,
        community_id=community_id,
        target_type="GameSession",
        target_id=session_no,
    )
    return success_response(
        {
            "eventId": event_id,
            "sessionNo": session_no,
            "gameType": game_type,
            "results": ranked_results,
        },
        status_code=201,
    )


def get_user_results(user_id, event):
    """F-804 (API設計書v1.4 §10.2): only viewable by someone who shares a
    community with the target user, scoped to that community.

    Stats are aggregated on read from GameResult rows (GSI1) rather than a
    stored running total. Lambda設計書v1.1 §8.3 describes updating totals
    "in place at registration time", but DynamoDB物理設計書v1.3 §3.13
    defines no aggregate/stats entity to hold such a running total --
    reconciled here by computing it at read time instead of inventing an
    attribute outside the physical design.
    """
    target_user_id = event["pathParameters"]["userId"]
    table = get_table()

    community_id = (event.get("queryStringParameters") or {}).get("communityId")
    if not community_id:
        return error_response(
            "INVALID_PARAMETER", "communityIdをクエリパラメータで指定してください"
        )

    if (
        table.get_item(
            Key={"PK": f"COMMUNITY#{community_id}", "SK": f"MEMBER#{user_id}"}
        ).get("Item")
        is None
        or table.get_item(
            Key={"PK": f"COMMUNITY#{community_id}", "SK": f"MEMBER#{target_user_id}"}
        ).get("Item")
        is None
    ):
        return error_response(
            "RESULT_ACCESS_DENIED", "この成績を閲覧する権限がありません", status_code=403
        )

    resp = table.query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq(f"USER#{target_user_id}")
        & Key("GSI1SK").begins_with(f"COMMUNITY#{community_id}"),
    )
    stats = _aggregate(resp.get("Items", []))
    return success_response({"userId": target_user_id, "communityId": community_id, **stats})


def _next_session_no(table, event_id):
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"EVENT#{event_id}")
        & Key("SK").begins_with("SESSION#")
    )
    existing_nos = set()
    for item in resp.get("Items", []):
        # SESSION#{sessionNo} (session item, 2 "#"-parts) vs.
        # SESSION#{sessionNo}#RESULT#{userId} (result item, 4 parts).
        parts = item["SK"].split("#")
        if len(parts) == 2:
            existing_nos.add(int(parts[1]))
    return f"{max(existing_nos, default=0) + 1:04d}"


def _validate_results(game_type, results):
    if not isinstance(game_type, str) or not game_type:
        return error_response("RESULT_VALIDATION_ERROR", "gameTypeが不正です")
    if not isinstance(results, list) or not results:
        return error_response("RESULT_VALIDATION_ERROR", "resultsが不正です")

    ranks = []
    for r in results:
        if not isinstance(r, dict) or not isinstance(r.get("userId"), str):
            return error_response("RESULT_VALIDATION_ERROR", "resultsの形式が不正です")
        rank = r.get("rank")
        score = r.get("score")
        if not isinstance(rank, int) or isinstance(rank, bool) or rank < 1:
            return error_response("RESULT_VALIDATION_ERROR", "rankが不正です")
        if not isinstance(score, int) or isinstance(score, bool):
            return error_response("RESULT_VALIDATION_ERROR", "scoreが不正です")
        ranks.append(rank)

    if len(ranks) != len(set(ranks)):
        return error_response("RESULT_VALIDATION_ERROR", "着順が重複しています")
    if sorted(ranks) != list(range(1, len(ranks) + 1)):
        return error_response("RESULT_VALIDATION_ERROR", "着順は1から連番で指定してください")

    return None


def _aggregate(results):
    total_games = len(results)
    if total_games == 0:
        return {
            "totalGames": 0,
            "averageRank": 0,
            "firstPlaceRate": 0,
            "lastPlaceRate": 0,
            "totalPoints": 0,
        }

    ranks = [r.get("rank", 0) for r in results]
    points = sum(r.get("rankPoints", 0) for r in results)
    # Approximation: "last place" is inferred from the worst rank this user
    # has actually recorded, rather than each session's true player count
    # (not stored on GameResult) -- fine as long as a community mostly
    # plays one fixed game type, less accurate if a user mixes e.g.
    # 3-player and 4-player sessions.
    worst_rank = max(ranks)

    return {
        "totalGames": total_games,
        "averageRank": round(sum(ranks) / total_games, 2),
        "firstPlaceRate": round(sum(1 for r in ranks if r == 1) / total_games, 3),
        "lastPlaceRate": round(sum(1 for r in ranks if r == worst_rank) / total_games, 3),
        "totalPoints": points,
    }
