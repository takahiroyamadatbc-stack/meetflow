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
    """F-801〜F-803 (API設計書v1.4 §10.1)。

    成績登録前にCOMPLETEDステータスを必須とすべきか（`EVENT_NOT_COMPLETED`）
    は、エラーコード一覧v1.1 §7で明示的に未決事項とされている
    （「実装方針次第で許可する場合は不要。要検討」）-- ドキュメントが
    まだ確定していない方針を先に決め打ちするのではなく、イベント進行中の
    セッションごとのスコア入力がブロックされないよう、ここでは強制しない
    ことにしている。
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
    """F-804 (API設計書v1.4 §10.2): 対象ユーザーと同じコミュニティに所属
    する人のみ閲覧可能で、そのコミュニティにスコープされる。

    統計情報は、保存された累計値ではなくGameResult行（GSI1）から読み取り
    時に集計する。Lambda設計書v1.1 §8.3は「登録時にその場で累計を更新
    する」と記載しているが、DynamoDB物理設計書v1.3 §3.13にはそのような
    累計値を保持する集計/統計エンティティが定義されていない -- 物理設計の
    外側に属性を作るのではなく、読み取り時に計算することで整合を取って
    いる。
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
    # Membership行もこれと同じGSI1プレフィックスを共有している（GSI1SKが
    # ちょうど`COMMUNITY#{communityId}`、DynamoDB物理設計書v1.3 §3.3）。
    # これはGameResultの`COMMUNITY#{communityId}#{playedAt}`（§3.13）の
    # プレフィックスでもあるため、`begins_with`は両方にマッチしてしまい、
    # このフィルタが無いとユーザー自身のMembershipレコードが幻の0位ゲーム
    # としてカウントされてしまう。PKで綺麗に判別できる: GameResultは常に
    # `EVENT#...`配下に存在する。
    game_results = [
        item for item in resp.get("Items", []) if item["PK"].startswith("EVENT#")
    ]
    stats = _aggregate(game_results)
    return success_response({"userId": target_user_id, "communityId": community_id, **stats})


def _next_session_no(table, event_id):
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"EVENT#{event_id}")
        & Key("SK").begins_with("SESSION#")
    )
    existing_nos = set()
    for item in resp.get("Items", []):
        # SESSION#{sessionNo}（セッションアイテム、"#"区切りで2パーツ） vs.
        # SESSION#{sessionNo}#RESULT#{userId}（結果アイテム、4パーツ）。
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
    # 近似値: 「最下位」は各セッションの実際のプレイヤー数（GameResultには
    # 保存されていない）ではなく、このユーザーが実際に記録した最も悪い
    # 着順から推測する -- コミュニティがほぼ固定のゲーム種別のみをプレイ
    # している限りは問題ないが、例えば3人打ちと4人打ちが混在するユーザー
    # では精度が落ちる。
    worst_rank = max(ranks)

    return {
        "totalGames": total_games,
        "averageRank": round(sum(ranks) / total_games, 2),
        "firstPlaceRate": round(sum(1 for r in ranks if r == 1) / total_games, 3),
        "lastPlaceRate": round(sum(1 for r in ranks if r == worst_rank) / total_games, 3),
        "totalPoints": points,
    }
