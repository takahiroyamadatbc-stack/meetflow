import json

from meetflow_common import now_iso_ms

SEASON = "2026-27"


def api_event(*, path_params=None, body=None, user_id=None):
    event = {
        "pathParameters": path_params or {},
        "body": json.dumps(body) if body is not None else None,
        "queryStringParameters": None,
    }
    if user_id is not None:
        event["requestContext"] = {"authorizer": {"claims": {"sub": user_id}}}
    return event


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


def put_profile(table, user_id, *, nickname=None):
    table.put_item(
        Item={
            "PK": f"USER#{user_id}",
            "SK": "PROFILE",
            "nickname": nickname or f"user-{user_id}",
        }
    )


def make_players(*, total=40, female=13, per_team=4):
    """テスト用の選手マスタ。

    本番と同じ「10チーム×4人・女性13人」の形をデフォルトにしている
    （DESIGN.md §2）。女性は先頭から順に割り当てるだけで、チームごとの
    内訳は本番と違うが、ルール上効くのは総数だけなので影響しない。
    """
    players = []
    for index in range(total):
        team_no = index // per_team + 1
        players.append(
            {
                "playerId": f"p{index + 1:02d}",
                "name": f"選手{index + 1:02d}",
                "kana": f"せんしゅ{index + 1:02d}",
                "teamId": f"team{team_no}",
                "teamName": f"チーム{team_no}",
                "isFemale": index < female,
            }
        )
    return players


def seed_players(draft_table, players=None, *, season=SEASON):
    # 空リストは「マスタ未シード」を意図した指定なので、Noneと区別する。
    if players is None:
        players = make_players()
    for player in players:
        draft_table.put_item(
            Item={
                "PK": f"MLPLAYER#{season}",
                "SK": f"PLAYER#{player['playerId']}",
                **player,
            }
        )


def setup_community(main_table, draft_table, *, community_id="c1", host="host", members=("u1", "u2"), players=None):
    """コミュニティ・メンバー・選手マスタをまとめて用意する。"""
    put_membership(main_table, community_id, host, role="OWNER")
    put_profile(main_table, host)
    for member in members:
        put_membership(main_table, community_id, member)
        put_profile(main_table, member)
    seed_players(draft_table, players)
    return community_id
