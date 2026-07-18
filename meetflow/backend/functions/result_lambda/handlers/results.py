from decimal import Decimal

from boto3.dynamodb.conditions import Key

from meetflow_common import (
    error_response,
    get_table,
    now_iso_ms,
    parse_body,
    require_membership,
    success_response,
    transact_write,
    write_operation_log,
)


def create_session(user_id, event):
    """F-801〜F-803 (API設計書v1.4 §10.1)。

    成績登録前にCOMPLETEDステータスを必須とすべきか（`EVENT_NOT_COMPLETED`）
    は、エラーコード一覧v1.1 §7で明示的に未決事項とされている
    （「実装方針次第で許可する場合は不要。要検討」）-- ドキュメントが
    まだ確定していない方針を先に決め打ちするのではなく、イベント進行中の
    セッションごとのスコア入力がブロックされないよう、ここでは強制しない
    ことにしている（COMPLETED後の新規登録も引き続き許可する。管理者が
    「本日の対局を終了する」を押し忘れたまま次の対局が始まるケースを
    考慮し、書き込みを機械的にロックすることはしない）。

    登録（POST）はコミュニティのアクティブなメンバーであれば誰でも実行
    できる（当初はOWNER/ADMIN限定だったが、対局を打った本人・記録係が
    その場で確定できないのは不便という要望を受けて緩和した）。登録済み
    セッションの編集（update_session）は、確定済みの記録を後から書き換える
    操作のためOWNER/ADMIN限定のまま据え置く。
    """
    event_id = event["pathParameters"]["eventId"]
    table = get_table()
    event_item = table.get_item(Key={"PK": f"EVENT#{event_id}", "SK": "METADATA"}).get(
        "Item"
    )
    if event_item is None:
        return error_response("EVENT_NOT_FOUND", "指定したイベントが見つかりません")
    community_id = event_item["GSI1PK"].split("#", 1)[1]
    require_membership(table, community_id, user_id)

    body = parse_body(event)
    validation_error = _validate_session_body(body)
    if validation_error:
        return validation_error

    session_no = _next_session_no(table, event_id)
    session_item, computed, chips = _write_session_items(
        table, event_id, community_id, session_no, body
    )

    write_operation_log(
        action="CREATE_GAME_SESSION",
        user_id=user_id,
        community_id=community_id,
        target_type="GameSession",
        target_id=session_no,
    )
    return success_response(
        _build_session_response(session_no, session_item, computed, chips),
        status_code=201,
    )


def update_session(user_id, event):
    """登録済み対局セッションの編集（新規追加）。OWNER/ADMINのみ実行可能。

    参加者構成（userIdの集合）は登録時から変更できない -- 人数や顔ぶれが
    変わる場合は別の対局として新規登録してもらう方針とした。これにより
    DeleteItem権限を追加せず、既存のGetItem/PutItem/Query権限のまま
    put_itemによる上書きだけで編集を完結できる。
    """
    event_id = event["pathParameters"]["eventId"]
    session_no = event["pathParameters"]["sessionNo"]
    table = get_table()

    event_item = table.get_item(Key={"PK": f"EVENT#{event_id}", "SK": "METADATA"}).get(
        "Item"
    )
    if event_item is None:
        return error_response("EVENT_NOT_FOUND", "指定したイベントが見つかりません")
    community_id = event_item["GSI1PK"].split("#", 1)[1]
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    session_item = table.get_item(
        Key={"PK": f"EVENT#{event_id}", "SK": f"SESSION#{session_no}"}
    ).get("Item")
    if session_item is None:
        return error_response("GAME_SESSION_NOT_FOUND", "指定した対局が見つかりません")

    body = parse_body(event)
    validation_error = _validate_session_body(body)
    if validation_error:
        return validation_error

    existing_results = table.query(
        KeyConditionExpression=Key("PK").eq(f"EVENT#{event_id}")
        & Key("SK").begins_with(f"SESSION#{session_no}#RESULT#")
    ).get("Items", [])
    existing_user_ids = {item["SK"].rsplit("#", 1)[1] for item in existing_results}
    new_user_ids = {r["userId"] for r in body["results"]}
    if existing_user_ids != new_user_ids:
        return error_response(
            "RESULT_VALIDATION_ERROR",
            "参加者の構成は編集できません。人数や顔ぶれが変わる場合は新しい対局として登録してください",
        )

    new_session_item, computed, chips = _write_session_items(
        table, event_id, community_id, session_no, body
    )

    write_operation_log(
        action="UPDATE_GAME_SESSION",
        user_id=user_id,
        community_id=community_id,
        target_type="GameSession",
        target_id=session_no,
    )
    return success_response(
        _build_session_response(session_no, new_session_item, computed, chips)
    )


def delete_session(user_id, event):
    """登録済み対局セッションの削除（Issue #42）。OWNER/ADMINのみ実行可能
    （update_sessionと同じ権限方針）。GameSession本体・全参加者分の
    GameResult・GameResultChipを1回のTransactWriteItemsでまとめて削除する
    （途中で一部だけ消えた状態が残らないようにするため）。
    """
    event_id = event["pathParameters"]["eventId"]
    session_no = event["pathParameters"]["sessionNo"]
    table = get_table()

    event_item = table.get_item(Key={"PK": f"EVENT#{event_id}", "SK": "METADATA"}).get(
        "Item"
    )
    if event_item is None:
        return error_response("EVENT_NOT_FOUND", "指定したイベントが見つかりません")
    community_id = event_item["GSI1PK"].split("#", 1)[1]
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"EVENT#{event_id}")
        & Key("SK").begins_with(f"SESSION#{session_no}")
    )
    items = resp.get("Items", [])
    session_item = next(
        (item for item in items if item["SK"] == f"SESSION#{session_no}"), None
    )
    if session_item is None:
        return error_response("GAME_SESSION_NOT_FOUND", "指定した対局が見つかりません")

    transact_write(
        [
            {"Delete": {"Key": {"PK": item["PK"], "SK": item["SK"]}}}
            for item in items
        ]
    )

    write_operation_log(
        action="DELETE_GAME_SESSION",
        user_id=user_id,
        community_id=community_id,
        target_type="GameSession",
        target_id=session_no,
    )
    return success_response({"eventId": event_id, "sessionNo": session_no})


def list_event_sessions(user_id, event):
    """イベント内の登録済み対局セッション一覧（新規追加）。コミュニティ
    メンバーであれば誰でも閲覧可能（役割は問わない）。
    """
    event_id = event["pathParameters"]["eventId"]
    table = get_table()
    event_item = table.get_item(Key={"PK": f"EVENT#{event_id}", "SK": "METADATA"}).get(
        "Item"
    )
    if event_item is None:
        return error_response("EVENT_NOT_FOUND", "指定したイベントが見つかりません")
    community_id = event_item["GSI1PK"].split("#", 1)[1]
    require_membership(table, community_id, user_id)

    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"EVENT#{event_id}")
        & Key("SK").begins_with("SESSION#")
    )
    sessions = _group_sessions(event_id, resp.get("Items", []))
    return success_response({"sessions": sessions})


def get_last_game_settings(user_id, event):
    """コミュニティ内で呼び出しユーザー自身が直近に記録した対局の計算設定
    （配給原点・返し点・ウマ・計算モード）を返す（新規追加）。「次回開催時は
    デフォルトとして使いたい」という要望への対応。

    コミュニティ側エンティティに書き込む案（例えばCOMMUNITY#{id}/METADATAに
    ResultLambdaから最終設定を保存する）も検討したが、Lambda設計書v1.1 §5.3
    「案C」のドメインLambdaごとのIAM最小権限方針（各ドメインは自分の
    エンティティのPK/SKプレフィックスのみ書き込む）に反するため採用しない。
    ここではResultLambda自身のGSI1（既存のGetItem/Query権限のみで完結）を
    使って、呼び出しユーザー自身の直近のGameResultから遡ってGameSessionの
    設定を引く方式にした。
    """
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    require_membership(table, community_id, user_id)

    resp = table.query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq(f"USER#{user_id}")
        & Key("GSI1SK").begins_with(f"COMMUNITY#{community_id}"),
        ScanIndexForward=False,
        Limit=25,
    )
    last_result = next(
        (
            item
            for item in resp.get("Items", [])
            if item["PK"].startswith("EVENT#") and "#RESULT#" in item["SK"]
        ),
        None,
    )
    if last_result is None:
        return success_response({"found": False})

    event_id = last_result["PK"].split("#", 1)[1]
    session_no = last_result["SK"].split("#")[1]
    session_item = table.get_item(
        Key={"PK": f"EVENT#{event_id}", "SK": f"SESSION#{session_no}"}
    ).get("Item")
    if session_item is None:
        return success_response({"found": False})

    response = {
        "found": True,
        "gameType": session_item.get("gameType"),
        "calcMode": session_item.get("calcMode", "MANUAL"),
    }
    if session_item.get("calcMode") == "AUTO":
        response["startingPoints"] = session_item.get("startingPoints")
        response["returnPoints"] = session_item.get("returnPoints")
        response["umaByRank"] = session_item.get("umaByRank", [])
    return success_response(response)


def get_user_results(user_id, event):
    """F-804 (API設計書v1.4 §10.2): 対象ユーザーと同じコミュニティに所属
    する人のみ閲覧可能で、そのコミュニティにスコープされる。

    統計情報は、保存された累計値ではなくGameResult行（GSI1）から読み取り
    時に集計する。Lambda設計書v1.1 §8.3は「登録時にその場で累計を更新
    する」と記載しているが、DynamoDB物理設計書v1.3 §3.13にはそのような
    累計値を保持する集計/統計エンティティが定義されていない -- 物理設計の
    外側に属性を作るのではなく、読み取り時に計算することで整合を取って
    いる。

    レスポンスはゲーム種別（四麻/三麻）ごとに分けて返す（`byGameType`）。
    四麻と三麻では着順のスケール（1〜4位 / 1〜3位）が異なり、合算した
    averageRank等は指標として意味を持たなくなるため（DynamoDB物理設計書
    v1.13 §3.13）。
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
    items = resp.get("Items", [])
    # Membership行（GSI1SKが`COMMUNITY#{communityId}`のみ）に加え、今回追加
    # したGameResultChip行もGameResultと同じGSI1PK/GSI1SKプレフィックスを
    # 共有している（DynamoDB物理設計書§3.13の子エンティティ方針の延長）。
    # PKだけのフィルタ（`EVENT#`始まり）ではChipとResultを区別できず、
    # Chipの`chipCount`が幻の`rank`/`score`としてstats計算に混入してしまう
    # ため、SKの内容（`#RESULT#` vs `#CHIP#`）で明示的に判別する。
    game_results = [
        item
        for item in items
        if item["PK"].startswith("EVENT#") and "#RESULT#" in item["SK"]
    ]
    chip_results = [
        item
        for item in items
        if item["PK"].startswith("EVENT#") and "#CHIP#" in item["SK"]
    ]
    # コミュニティの通算成績（＝実質的なランキングの原資）に反映されるのは、
    # 管理者/OWNERが「本日の対局を終了する」（events.complete_event、
    # CONFIRMED→COMPLETED）を実行してイベントを終了させた対局のみ。
    # 終了前（進行中）のセッションはEventResultsPage上の「当日の累計成績」
    # では見えるが、ここでは確定した記録として扱わない。
    completed_event_ids = _completed_event_ids(
        table, {item["PK"].split("#", 1)[1] for item in game_results + chip_results}
    )
    game_results = [
        r for r in game_results if r["PK"].split("#", 1)[1] in completed_event_ids
    ]
    chip_results = [
        c for c in chip_results if c["PK"].split("#", 1)[1] in completed_event_ids
    ]

    by_game_type = {}
    for game_type in ("MAHJONG4", "MAHJONG3"):
        gt_game_results = [r for r in game_results if r.get("gameType") == game_type]
        gt_chip_results = [c for c in chip_results if c.get("gameType") == game_type]
        stats = _aggregate(gt_game_results)
        stats["totalChips"] = sum(_as_int(c.get("chipCount", 0)) for c in gt_chip_results)
        by_game_type[game_type] = stats

    return success_response(
        {
            "userId": target_user_id,
            "communityId": community_id,
            "byGameType": by_game_type,
        }
    )


def _completed_event_ids(table, event_ids):
    """引数のイベントIDのうち、既にCOMPLETED（本日の対局終了済み）になって
    いるものだけを返す。GameResult/GameResultChipにはイベントの状態が
    非正規化されていないため、都度Eventメタデータを引いて判定する。
    """
    completed = set()
    for event_id in event_ids:
        item = table.get_item(Key={"PK": f"EVENT#{event_id}", "SK": "METADATA"}).get(
            "Item"
        )
        if item is not None and item.get("status") == "COMPLETED":
            completed.add(event_id)
    return completed


def _next_session_no(table, event_id):
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"EVENT#{event_id}")
        & Key("SK").begins_with("SESSION#")
    )
    existing_nos = set()
    for item in resp.get("Items", []):
        # SESSION#{sessionNo}（セッションアイテム、"#"区切りで2パーツ） vs.
        # SESSION#{sessionNo}#RESULT#{userId} / SESSION#{sessionNo}#CHIP#{userId}
        # （結果/チップアイテム、4パーツ）。
        parts = item["SK"].split("#")
        if len(parts) == 2:
            existing_nos.add(int(parts[1]))
    return f"{max(existing_nos, default=0) + 1:04d}"


def _validate_session_body(body):
    if not isinstance(body, dict):
        return error_response("RESULT_VALIDATION_ERROR", "リクエスト内容が不正です")

    game_type = body.get("gameType")
    if not isinstance(game_type, str) or not game_type:
        return error_response("RESULT_VALIDATION_ERROR", "gameTypeが不正です")

    calc_mode = body.get("calcMode", "MANUAL")
    if calc_mode not in ("AUTO", "MANUAL"):
        return error_response(
            "RESULT_VALIDATION_ERROR", "calcModeはAUTOかMANUALで指定してください"
        )

    results = body.get("results")
    if not isinstance(results, list) or not results:
        return error_response("RESULT_VALIDATION_ERROR", "resultsが不正です")

    user_ids = []
    for r in results:
        if not isinstance(r, dict) or not isinstance(r.get("userId"), str):
            return error_response("RESULT_VALIDATION_ERROR", "resultsの形式が不正です")
        score = r.get("score")
        if not isinstance(score, int) or isinstance(score, bool):
            return error_response("RESULT_VALIDATION_ERROR", "scoreが不正です")
        user_ids.append(r["userId"])
    if len(user_ids) != len(set(user_ids)):
        return error_response("RESULT_VALIDATION_ERROR", "参加者が重複しています")

    if calc_mode == "AUTO":
        starting_points = body.get("startingPoints")
        return_points = body.get("returnPoints")
        uma_by_rank = body.get("umaByRank")
        if not _is_number(starting_points) or not _is_number(return_points):
            return error_response(
                "RESULT_VALIDATION_ERROR", "配給原点・返し点が不正です"
            )
        if (
            not isinstance(uma_by_rank, list)
            or len(uma_by_rank) != len(results)
            or not all(_is_number(v) for v in uma_by_rank)
        ):
            return error_response("RESULT_VALIDATION_ERROR", "ウマの指定が不正です")

    chips = body.get("chips", [])
    if not isinstance(chips, list):
        return error_response("RESULT_VALIDATION_ERROR", "chipsが不正です")
    result_user_id_set = set(user_ids)
    for c in chips:
        if (
            not isinstance(c, dict)
            or not isinstance(c.get("userId"), str)
            or c["userId"] not in result_user_id_set
            or not isinstance(c.get("chipCount"), int)
            or isinstance(c.get("chipCount"), bool)
        ):
            return error_response("RESULT_VALIDATION_ERROR", "chipsの形式が不正です")

    return None


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _compute_results(results, calc_mode, starting_points, return_points, uma_by_rank):
    """score降順でrankを機械的に決める（同点はPythonのsortedの安定性を
    利用し、入力順でタイブレークする）。AUTO時のみ配給原点・返し点・ウマを
    使った一般的な麻雀のウマオカ計算式で最終ポイントを算出する：

        base   = (score - returnPoints) / 1000
        oka    = (returnPoints - startingPoints) * 人数 / 1000  # 1位のみ加算
        final  = base + umaByRank[着順-1] + oka

    MANUAL時はこの計算を一切行わず、rankPointsは常に0とする。
    """
    ordered = sorted(results, key=lambda r: -r["score"])
    player_count = len(results)
    computed = []
    for index, r in enumerate(ordered):
        rank = index + 1
        if calc_mode == "AUTO":
            base = (r["score"] - return_points) / 1000
            oka = (
                (return_points - starting_points) * player_count / 1000
                if rank == 1
                else 0
            )
            rank_points = round(base + uma_by_rank[rank - 1] + oka, 1)
        else:
            rank_points = 0
        computed.append(
            {
                "userId": r["userId"],
                "rank": rank,
                "score": r["score"],
                "rankPoints": rank_points,
            }
        )
    return computed


def _write_session_items(table, event_id, community_id, session_no, body):
    game_type = body["gameType"]
    calc_mode = body.get("calcMode", "MANUAL")
    played_at = now_iso_ms()
    results = body["results"]
    chips = body.get("chips", [])
    starting_points = body.get("startingPoints")
    return_points = body.get("returnPoints")
    uma_by_rank = body.get("umaByRank")

    computed = _compute_results(
        results, calc_mode, starting_points, return_points, uma_by_rank
    )

    session_item = {
        "PK": f"EVENT#{event_id}",
        "SK": f"SESSION#{session_no}",
        "gameType": game_type,
        "playedAt": played_at,
        "calcMode": calc_mode,
    }
    if calc_mode == "AUTO":
        session_item["startingPoints"] = _to_decimal(starting_points)
        session_item["returnPoints"] = _to_decimal(return_points)
        session_item["umaByRank"] = [_to_decimal(v) for v in uma_by_rank]
    table.put_item(Item=session_item)

    for r in computed:
        table.put_item(
            Item={
                "PK": f"EVENT#{event_id}",
                "SK": f"SESSION#{session_no}#RESULT#{r['userId']}",
                "GSI1PK": f"USER#{r['userId']}",
                "GSI1SK": f"COMMUNITY#{community_id}#{played_at}",
                "rank": r["rank"],
                "score": r["score"],
                "rankPoints": _to_decimal(r["rankPoints"]),
                "playedAt": played_at,
                # GameSessionから非正規化（DynamoDB物理設計書v1.13 §3.13）。
                # 四麻/三麻を分けて集計するため（_aggregate参照）。
                "gameType": game_type,
            }
        )

    for c in chips:
        table.put_item(
            Item={
                "PK": f"EVENT#{event_id}",
                "SK": f"SESSION#{session_no}#CHIP#{c['userId']}",
                "GSI1PK": f"USER#{c['userId']}",
                "GSI1SK": f"COMMUNITY#{community_id}#{played_at}",
                "chipCount": c["chipCount"],
                "playedAt": played_at,
                "gameType": game_type,
            }
        )

    return session_item, computed, chips


def _to_decimal(value):
    return Decimal(str(value))


def _build_session_response(session_no, session_item, computed, chips):
    response = {
        "eventId": session_item["PK"].split("#", 1)[1],
        "sessionNo": session_no,
        "gameType": session_item["gameType"],
        "calcMode": session_item["calcMode"],
        "results": computed,
        "chips": chips,
    }
    if session_item["calcMode"] == "AUTO":
        response["startingPoints"] = session_item["startingPoints"]
        response["returnPoints"] = session_item["returnPoints"]
        response["umaByRank"] = session_item["umaByRank"]
    return response


def _group_sessions(event_id, items):
    sessions = {}
    for item in items:
        parts = item["SK"].split("#")
        session_no = parts[1]
        bucket = sessions.setdefault(
            session_no, {"meta": None, "results": [], "chips": []}
        )
        if len(parts) == 2:
            bucket["meta"] = item
        elif len(parts) == 4 and parts[2] == "RESULT":
            bucket["results"].append(item)
        elif len(parts) == 4 and parts[2] == "CHIP":
            bucket["chips"].append(item)

    out = []
    for session_no in sorted(sessions):
        bucket = sessions[session_no]
        meta = bucket["meta"] or {}
        results = sorted(bucket["results"], key=lambda r: _as_int(r.get("rank", 0)))
        entry = {
            "eventId": event_id,
            "sessionNo": session_no,
            "gameType": meta.get("gameType"),
            "playedAt": meta.get("playedAt"),
            "calcMode": meta.get("calcMode", "MANUAL"),
            "results": [
                {
                    "userId": r["SK"].rsplit("#", 1)[1],
                    "rank": _as_int(r.get("rank")),
                    "score": _as_int(r.get("score")),
                    "rankPoints": r.get("rankPoints", 0),
                }
                for r in results
            ],
            "chips": [
                {
                    "userId": c["SK"].rsplit("#", 1)[1],
                    "chipCount": _as_int(c.get("chipCount", 0)),
                }
                for c in bucket["chips"]
            ],
        }
        if entry["calcMode"] == "AUTO":
            entry["startingPoints"] = meta.get("startingPoints")
            entry["returnPoints"] = meta.get("returnPoints")
            entry["umaByRank"] = meta.get("umaByRank", [])
        out.append(entry)
    return out


def _as_int(value):
    return int(value) if value is not None else 0


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
