import json

from meetflow_common import now_iso_ms


def api_event(*, path_params=None, body=None, query=None):
    return {
        "pathParameters": path_params or {},
        "body": json.dumps(body) if body is not None else None,
        "queryStringParameters": query,
    }


def put_membership(table, community_id, user_id, *, role="MEMBER", status="ACTIVE"):
    table.put_item(
        Item={
            "PK": f"COMMUNITY#{community_id}",
            "SK": f"MEMBER#{user_id}",
            "GSI1PK": f"USER#{user_id}",
            "GSI1SK": f"COMMUNITY#{community_id}",
            "role": role,
            "status": status,
            "joinedAt": now_iso_ms(),
        }
    )


def put_event(table, event_id, community_id, *, status="COMPLETED"):
    table.put_item(
        Item={
            "PK": f"EVENT#{event_id}",
            "SK": "METADATA",
            "GSI1PK": f"COMMUNITY#{community_id}",
            "GSI1SK": f"EVENT#2026-08-05T19:00:00.000Z#{event_id}",
            "status": status,
            "startTime": "2026-08-05T19:00:00.000Z",
            "endTime": "2026-08-05T23:00:00.000Z",
            "createdAt": now_iso_ms(),
        }
    )


def put_profile(table, user_id, *, nickname="ぷれいやー"):
    table.put_item(
        Item={"PK": f"USER#{user_id}", "SK": "PROFILE", "nickname": nickname}
    )


def put_game_result(
    table,
    event_id,
    community_id,
    session_no,
    user_id,
    *,
    game_type="MAHJONG4",
    rank,
    score=0,
    rank_points=0,
    played_at,
    chip_count=None,
):
    """コミュニティ内ランキングのテスト用に、GameResult（および任意で
    GameResultChip）をplayedAt指定で直接書き込む。create_sessionは常に
    now_iso_ms()でplayedAtを決めるため、期間フィルタ（GSI2SK between）の
    境界値テストにはこちらを使う。
    """
    table.put_item(
        Item={
            "PK": f"EVENT#{event_id}",
            "SK": f"SESSION#{session_no}#RESULT#{user_id}",
            "GSI1PK": f"USER#{user_id}",
            "GSI1SK": f"COMMUNITY#{community_id}#{played_at}",
            "GSI2PK": f"COMMUNITY#{community_id}#{game_type}",
            "GSI2SK": played_at,
            "rank": rank,
            "score": score,
            "rankPoints": rank_points,
            "playedAt": played_at,
            "gameType": game_type,
        }
    )
    if chip_count is not None:
        table.put_item(
            Item={
                "PK": f"EVENT#{event_id}",
                "SK": f"SESSION#{session_no}#CHIP#{user_id}",
                "GSI1PK": f"USER#{user_id}",
                "GSI1SK": f"COMMUNITY#{community_id}#{played_at}",
                "GSI2PK": f"COMMUNITY#{community_id}#{game_type}",
                "GSI2SK": played_at,
                "chipCount": chip_count,
                "playedAt": played_at,
                "gameType": game_type,
            }
        )


def body_of(response):
    return json.loads(response["body"])
