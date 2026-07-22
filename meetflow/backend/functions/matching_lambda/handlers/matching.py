from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key

from meetflow_common import (
    add_days_iso,
    count_confirmed_events_in_period,
    error_response,
    generate_id,
    get_display_name,
    get_frequency_limit,
    get_table,
    now_iso_ms,
    parse_body,
    period_bounds,
    require_membership,
    success_response,
    transact_write,
    write_operation_log,
)

from .scoring import calculate_score

_MATCHING_WINDOW_DAYS = 30  # ドキュメントに明記なし。F-401のMVP検索範囲
_FAIRNESS_WINDOW_DAYS = 45  # ドキュメント: "直近30〜60日"; MVPでは中間値を採用


def generate_candidates(user_id, event):
    """F-401 (API設計書v1.4 §6.1)。MVPでは管理者による手動実行のみ
    （Lambda設計書v1.1 §6.6）-- 呼び出され方に依存しないよう実装しており、
    将来的に定期実行/自動トリガーが追加されても、新たなAPI面を増やすこと
    なく同じロジックを呼び出せる。
    """
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    body = parse_body(event)
    template_id = body.get("templateId")
    if not isinstance(template_id, str) or not template_id:
        return error_response("INVALID_PARAMETER", "templateIdが不正です")

    template = table.get_item(
        Key={"PK": f"COMMUNITY#{community_id}", "SK": f"TEMPLATE#{template_id}"}
    ).get("Item")
    if template is None:
        return error_response(
            "EVENT_TEMPLATE_NOT_FOUND", "指定した開催条件が見つかりません"
        )

    # NO_CANDIDATES_FOUND（エラーコード一覧v1.1 §5）はエラーではなく正常な
    # 200の空結果である -- ここでは空の`candidates`リストで対応する。
    # 再生成時に内容が完全一致する既存候補があれば新規レコードは作らず
    # 再利用する（Issue #84）。それ以外の既存PENDINGはDISCARDEDにする
    # （Issue #27）。いずれも_run_matching内部で行う。
    candidate_items = _run_matching(table, community_id, template_id, template)
    candidates = [_to_api_candidate(table, community_id, item) for item in candidate_items]
    return success_response({"candidates": candidates}, status_code=201)


def create_manual_candidate(user_id, event):
    """POST /communities/{communityId}/matching/candidates/manual（Issue #56）。

    「急遽今から麻雀やろう」等、通常のマッチングフロー（開催条件登録→空き
    予定収集→候補生成）を経ずに、管理者がメンバー・日時を直接指定して
    MatchCandidateを作成する。スコアリング（scoring.calculate_score）は
    通さず、開催条件（EventTemplate）にも紐付けない
    -- `templateId`を省略する（＝取得時None）ことがこの候補が手動作成で
    あることの目印になり、`event_lambda`の`confirm_event`はこれを見て
    承認フローを完全スキップする分岐に入る。以降は既存の
    `create_event`（候補ベース作成）にそのまま乗せるため、Event/
    MatchCandidateの物理設計（キー構造）は変更しない。

    ゲーム種別は開催条件を経由しないためテンプレートには存在せず、
    その場の自由入力をMatchCandidate自体に`gameType`属性として直接
    保存する（DynamoDB物理設計書には無い新規のオプショナル属性。通常の
    候補生成では書き込まない）。ダブルブッキングの同期ハードチェック
    （PARTICIPANT_SCHEDULE_CONFLICT）は候補作成時点ではなくconfirm_event
    側にあるため、ここでは通常の候補生成同様に行わない。
    """
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    body = parse_body(event)
    member_ids = body.get("memberIds")
    if (
        not isinstance(member_ids, list)
        or not member_ids
        or not all(isinstance(m, str) for m in member_ids)
    ):
        return error_response("INVALID_PARAMETER", "memberIdsが不正です")
    member_ids = sorted(set(member_ids))

    start_time = body.get("startTime")
    end_time = body.get("endTime")
    if (
        not isinstance(start_time, str)
        or not isinstance(end_time, str)
        or not start_time
        or end_time <= start_time
    ):
        return error_response("INVALID_TIME_RANGE", "開始・終了日時が不正です")

    game_type = body.get("gameType")
    if game_type is not None and not isinstance(game_type, str):
        return error_response("INVALID_PARAMETER", "gameTypeが不正です")

    for uid in member_ids:
        membership = table.get_item(
            Key={"PK": f"COMMUNITY#{community_id}", "SK": f"MEMBER#{uid}"}
        ).get("Item")
        if membership is None or membership.get("status") != "ACTIVE":
            return error_response(
                "INVALID_PARAMETER",
                "メンバーの中にアクティブでないユーザーが含まれています",
            )

    candidate_id = generate_id()
    created_at = now_iso_ms()
    candidate_item = {
        "PK": f"COMMUNITY#{community_id}",
        "SK": f"CANDIDATE#{created_at}#{candidate_id}",
        "GSI2PK": f"CANDIDATE#{candidate_id}",
        "GSI2SK": "METADATA",
        "members": set(member_ids),
        # DynamoDBの文字列セット(SS)は空集合を許容しないため、必ず1件以上
        # 入る固定文言にする（通常の候補生成のスコア理由と役割を揃える）。
        "reasons": {"手動作成"},
        "status": "PENDING",
        "createdAt": created_at,
    }
    if game_type:
        candidate_item["gameType"] = game_type
    table.put_item(Item=candidate_item)

    for uid in member_ids:
        table.put_item(
            Item={
                "PK": f"COMMUNITY#{community_id}",
                "SK": f"CANDIDATE#{candidate_id}#MEMBER#{uid}",
                "GSI1PK": f"USER#{uid}",
                "GSI1SK": f"CANDIDATE#{start_time}#{candidate_id}",
                "candidateId": candidate_id,
                "startTime": start_time,
                "endTime": end_time,
                "status": "PENDING",
                "conflictWarning": False,
                "createdAt": created_at,
            }
        )

    write_operation_log(
        action="CREATE_MANUAL_CANDIDATE",
        user_id=user_id,
        community_id=community_id,
        target_type="MatchCandidate",
        target_id=candidate_id,
    )
    return success_response(
        _to_api_candidate(table, community_id, candidate_item), status_code=201
    )


def list_candidates(user_id, event):
    """F-404 list (API設計書v1.4 §6.2)."""
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"COMMUNITY#{community_id}")
        & Key("SK").begins_with("CANDIDATE#")
    )
    # DynamoDB物理設計書v1.3 §3.8（MatchCandidate、SK=CANDIDATE#{createdAt}#
    # {id}）と§3.11b（CandidateMember、SK=CANDIDATE#{id}#MEMBER#{userId}）は
    # 同じコミュニティPKの下で"CANDIDATE#"というSKプレフィックスを共有して
    # いるため、このクエリはCandidateMember行も返してしまう -- MatchCandidate
    # のSKには"#MEMBER#"が含まれることは無いため、それを判別材料にする。
    candidate_items = [
        item for item in resp.get("Items", []) if "#MEMBER#" not in item["SK"]
    ]
    candidates = [_to_api_candidate(table, community_id, item) for item in candidate_items]
    return success_response({"candidates": candidates})


def get_candidate_detail(user_id, event):
    """F-404 detail（API設計書v1.4 §6.3）。pathにcommunityIdを含めずGSI2経由
    で解決する（DynamoDB物理設計書v1.3 §3.8）。"""
    candidate_id = event["pathParameters"]["candidateId"]
    table = get_table()

    resp = table.query(
        IndexName="GSI2",
        KeyConditionExpression=Key("GSI2PK").eq(f"CANDIDATE#{candidate_id}"),
        Limit=1,
    )
    items = resp.get("Items", [])
    if not items:
        return error_response("CANDIDATE_NOT_FOUND", "指定した候補が見つかりません")

    community_id = items[0]["PK"].split("#", 1)[1]
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))
    return success_response(_to_api_candidate(table, community_id, items[0]))


def list_near_miss_windows(user_id, event):
    """Issue #96: 「あと〇人で成立」の集計。CandidateMemberは管理者が候補
    生成（F-401）を手動実行した後にしか存在しないため使えない -- 全メンバーの
    提出済みAvailabilityを起点に、_run_matchingと同じオーバーラップ計算
    （_overlapping_member_windows）をその場で走らせるリアルタイム集計として
    実装する。

    相互非公開型マッチング（要件定義書v1.9 §19/§29.4）の原則により、まだ
    このコミュニティで（今日以降の日時の）空き予定を1件も提出していない
    呼び出し元には空リストしか返さない -- 後出しの傍観者に「どこに滑り込め
    ば決定打になれるか」を教えないための唯一の防波堤（Issue #96のNote：
    表示対象の限定が後出し防止の肝）。一度自分の空きを提出したメンバーは
    既に自分の手の内を晒しており、以降は駆け引きの対象にならないため、
    この関門さえ通れば「自分がまだ入っていない窓（＝自分が1枠足せば成立
    させられる窓）」も含めて全件返す（Issue #96 設計方針：「彼らは自分が
    枠を1つ足せば成立させられる場合、その導線から即コミットできる」）。
    レスポンスは「あと何人必要か」という集計値のみで、member_ids（誰が
    空きを出しているか）は一切含めない。
    """
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    require_membership(table, community_id, user_id)

    query_params = event.get("queryStringParameters") or {}
    template_id = query_params.get("templateId")
    if not isinstance(template_id, str) or not template_id:
        return error_response("INVALID_PARAMETER", "templateIdが不正です")

    template = table.get_item(
        Key={"PK": f"COMMUNITY#{community_id}", "SK": f"TEMPLATE#{template_id}"}
    ).get("Item")
    if template is None:
        return error_response(
            "EVENT_TEMPLATE_NOT_FOUND", "指定した開催条件が見つかりません"
        )

    from_time = now_iso_ms()
    to_time = add_days_iso(from_time, _MATCHING_WINDOW_DAYS)
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"COMMUNITY#{community_id}")
        & Key("SK").between(f"AVAIL#{from_time}", f"AVAIL#{to_time}")
    )
    availability_items = resp.get("Items", [])

    # ゲーム種別を問わない「提出済みか」の判定（#95のホーム/成績入力後導線と
    # 同じ基準）。このテンプレートのgameTypeに絞る前の全件で見る -- 傍観者
    # 判定はこのコミュニティに対するコミット有無の話であり、テンプレート単位
    # の話ではないため。
    if not any(item["userId"] == user_id for item in availability_items):
        return success_response({"windows": []})

    game_type = template.get("gameType")
    filtered_items = [
        item
        for item in availability_items
        if not item.get("gameTypes") or game_type in item["gameTypes"]
    ]

    # _run_matching（408行目）と同じ下限処理・必須メンバー判定。必須メンバーが
    # 不在の窓を「あとN人で成立」と誤って見せないための二重チェック。
    min_players = max(template.get("minPlayers", 2), 2)
    required_members = set(
        (template.get("conditions") or {}).get("requiredMembers", []) or []
    )

    windows = []
    for start_time, end_time, member_ids in _overlapping_member_windows(filtered_items):
        if required_members and not required_members.issubset(member_ids):
            continue
        if len(member_ids) >= min_players:
            continue
        windows.append(
            {
                "startTime": start_time,
                "endTime": end_time,
                "neededCount": min_players - len(member_ids),
            }
        )
    return success_response({"windows": windows})


def _existing_candidates_for_template(table, community_id, template_id):
    """同一community内の既存CANDIDATE系アイテムを1回のQueryでまとめて取得し、
    (1) 完全一致判定用の署名(startTime, endTime, memberIds)→アイテムの
    マップ（CONFIRMED＝イベント化済みは対象外）と、(2) 今回の生成結果で
    再利用されなければDISCARDEDにすべき既存PENDING候補一覧、の2つを
    組み立てる（Issue #84）。

    MatchCandidate自体にはstartTime/endTimeが無く、ミラーされている
    CandidateMember側にしか無いため、同じQuery結果からCandidateMember
    行も拾ってcandidateId→(startTime, endTime)の対応表を作る。
    """
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"COMMUNITY#{community_id}")
        & Key("SK").begins_with("CANDIDATE#")
    )
    all_items = resp.get("Items", [])

    time_by_candidate_id = {}
    for item in all_items:
        if "#MEMBER#" not in item["SK"]:
            continue
        candidate_id = item.get("candidateId")
        if candidate_id and candidate_id not in time_by_candidate_id:
            time_by_candidate_id[candidate_id] = (item.get("startTime"), item.get("endTime"))

    reusable_by_signature = {}
    stale_pending = []
    for item in all_items:
        if "#MEMBER#" in item["SK"] or item.get("templateId") != template_id:
            continue
        status = item.get("status")
        if status == "PENDING":
            stale_pending.append(item)
        if status == "CONFIRMED":
            continue
        candidate_id = item["GSI2PK"].split("#", 1)[1]
        start_time, end_time = time_by_candidate_id.get(candidate_id, (None, None))
        if not start_time or not end_time:
            continue
        signature = (start_time, end_time, tuple(sorted(item.get("members", []))))
        reusable_by_signature[signature] = item

    return reusable_by_signature, stale_pending


def _discard_unmatched_candidates(table, community_id, stale_pending, matched_candidate_ids):
    """今回の生成で再利用されなかった既存PENDING候補のみをDISCARDEDにする
    （Issue #84）。以前は同一templateIdのPENDING候補を問答無用に全部
    DISCARDEDしていたが、内容が完全一致する候補は_revive_candidateで
    使い回すため、ここで対象になるのは本当に不要になったものだけ。
    CONFIRMED（イベント化済み）の候補には触れない。

    管理者による単発の手動実行が前提でMVP規模では競合リスクが低いため、
    ConditionExpressionは付けない（他の単純なupdate_itemと同様の簡潔さを
    優先）。TransactWriteItemsの100件上限は100件単位のチャンクに分けて
    吸収する。
    """
    operations = []
    for item in stale_pending:
        candidate_id = item["GSI2PK"].split("#", 1)[1]
        if candidate_id in matched_candidate_ids:
            continue
        operations.append(_discard_update(item["PK"], item["SK"]))
        for uid in item.get("members", []):
            operations.append(
                _discard_update(
                    f"COMMUNITY#{community_id}",
                    f"CANDIDATE#{candidate_id}#MEMBER#{uid}",
                )
            )

    for i in range(0, len(operations), 100):
        transact_write(operations[i : i + 100])


def _discard_update(pk, sk):
    return {
        "Update": {
            "Key": {"PK": pk, "SK": sk},
            "UpdateExpression": "SET #status = :discarded",
            "ExpressionAttributeNames": {"#status": "status"},
            "ExpressionAttributeValues": {":discarded": "DISCARDED"},
        }
    }


def _revive_candidate(
    table,
    community_id,
    existing_item,
    template_id,
    template,
    start_time,
    end_time,
    member_ids,
    community_genre,
):
    """既存候補と内容（開始/終了時刻・メンバー構成）が完全一致する場合に、
    新規レコードを作らずこの既存候補を再利用する（Issue #84）。
    MatchCandidateのSKはcreatedAtを含む（DynamoDB物理設計書 §3.8）ため、
    createdAtを今回の再生成時刻に更新するには旧SKの削除＋新SKでのPutが
    必要になる -- candidateId自体は使い回すため、CandidateMember側の
    紐付け（SK=CANDIDATE#{candidateId}#MEMBER#{userId}）は変わらない。
    """
    candidate_id = existing_item["GSI2PK"].split("#", 1)[1]
    profiles = [
        table.get_item(Key={"PK": f"USER#{uid}", "SK": "PROFILE"}).get("Item") or {}
        for uid in member_ids
    ]
    days_since_last_played = [
        _days_since_last_participation(table, uid) for uid in member_ids
    ]
    frequency_status = [
        _frequency_limit_status(table, community_id, uid, community_genre, start_time)
        for uid in member_ids
    ]
    score, reasons = calculate_score(
        template=template,
        members_profiles=profiles,
        members_days_since_last_played=days_since_last_played,
        members_frequency_status=frequency_status,
    )

    created_at = now_iso_ms()
    candidate_item = {
        "PK": f"COMMUNITY#{community_id}",
        "SK": f"CANDIDATE#{created_at}#{candidate_id}",
        "GSI2PK": f"CANDIDATE#{candidate_id}",
        "GSI2SK": "METADATA",
        "templateId": template_id,
        "score": score,
        "members": set(member_ids),
        "reasons": set(reasons),
        "status": "PENDING",
        "createdAt": created_at,
    }
    transact_write(
        [
            {"Delete": {"Key": {"PK": existing_item["PK"], "SK": existing_item["SK"]}}},
            {"Put": {"Item": candidate_item}},
        ]
    )

    for uid in member_ids:
        table.update_item(
            Key={
                "PK": f"COMMUNITY#{community_id}",
                "SK": f"CANDIDATE#{candidate_id}#MEMBER#{uid}",
            },
            UpdateExpression="SET #status = :pending, createdAt = :created",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":pending": "PENDING", ":created": created_at},
        )

    return candidate_item


def _run_matching(table, community_id, template_id, template):
    """F-401の処理フロー（Lambda設計書v1.1 §6.3）: 空き予定の取得 ->
    条件マッチング（F-402） -> スコアリング（F-403） -> MatchCandidate +
    CandidateMemberの永続化。

    F-402の「日時一致」は、全員の空き予定が寸分違わず一致することではなく、
    共通して空いている時間帯が存在することを指す（例：Aは11:00〜13:00、
    Bは12:00〜14:00なら12:00〜13:00が共通区間）。そのため(startTime, endTime)
    の完全一致ではなく、_overlapping_member_windowsで全員の区間の交差
    （重複区間）を求める。

    [Issue #84] 同一テンプレートへの再生成で、内容（開始/終了時刻・
    メンバー構成）が既存候補と完全一致する場合は新規レコードを作らず
    _revive_candidateで再利用する。今回の結果に対応が見つからなかった
    既存PENDING候補だけを最後に_discard_unmatched_candidatesでDISCARDED
    にする。
    """
    from_time = now_iso_ms()
    to_time = add_days_iso(from_time, _MATCHING_WINDOW_DAYS)

    # 参加頻度上限のジャンル横断カウント（Issue #19）で使う。候補ごとに
    # 変わらないためループの外で1回だけ取得する（N+1回避）。
    community_item = table.get_item(
        Key={"PK": f"COMMUNITY#{community_id}", "SK": "METADATA"}
    ).get("Item") or {}
    community_genre = community_item.get("genre", "")

    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"COMMUNITY#{community_id}")
        & Key("SK").between(f"AVAIL#{from_time}", f"AVAIL#{to_time}")
    )
    availability_items = resp.get("Items", [])

    game_type = template.get("gameType")
    filtered_items = [
        item
        for item in availability_items
        if not item.get("gameTypes") or game_type in item["gameTypes"]
    ]

    # Issue #57: minPlayers=1を許すと1人だけの空き区間がそのまま候補化され、
    # 「相互非公開型マッチング」の前提が管理者側から破れてしまう。
    # `_validate`側で下限2を強制しているが、既存データや将来の書き込み経路
    # 漏れに備えてここでも下限2を強制する二重防御。
    min_players = max(template.get("minPlayers", 2), 2)
    max_players = template.get("maxPlayers", min_players)
    required_members = set(
        (template.get("conditions") or {}).get("requiredMembers", []) or []
    )

    reusable_by_signature, stale_pending = _existing_candidates_for_template(
        table, community_id, template_id
    )

    matched_candidate_ids = set()
    created_candidates = []
    for start_time, end_time, member_ids in _overlapping_member_windows(filtered_items):
        if required_members and not required_members.issubset(member_ids):
            continue
        if len(member_ids) < min_players:
            continue
        if len(member_ids) > max_players:
            # MVPのヒューリスティック: 必須メンバーは維持し、残り枠は全ての
            # 部分集合を探索するのではなく決定的に（userIdでソート）埋める
            # -- ドキュメントには部分集合の選定方法が指定されていないため。
            required = [m for m in member_ids if m in required_members]
            optional = [m for m in member_ids if m not in required_members]
            member_ids = sorted(required + optional[: max_players - len(required)])

        signature = (start_time, end_time, tuple(member_ids))
        existing = reusable_by_signature.get(signature)
        if existing is not None:
            candidate_item = _revive_candidate(
                table,
                community_id,
                existing,
                template_id,
                template,
                start_time,
                end_time,
                member_ids,
                community_genre,
            )
            matched_candidate_ids.add(existing["GSI2PK"].split("#", 1)[1])
        else:
            candidate_item = _create_candidate(
                table,
                community_id,
                template_id,
                template,
                start_time,
                end_time,
                member_ids,
                community_genre,
            )
        created_candidates.append(candidate_item)

    _discard_unmatched_candidates(table, community_id, stale_pending, matched_candidate_ids)

    return created_candidates


def _overlapping_member_windows(availability_items):
    """空き予定区間群から、参加者集合が変化しない極大区間を時系列に列挙する
    （スイープライン法）。各区間は[startTime, endTime)の半開区間として扱う
    ため、同時刻に終了と開始が重なる場合は終了を先に処理し、隙間なく連続
    するだけの区間（例：11:00-12:00と12:00-13:00）を誤って重複扱いしない
    ようにする。

    戻り値は(startTime, endTime, memberIds)のリスト。同じメンバー集合が
    隣接する区間はマージ済み。
    """
    events = []
    for item in availability_items:
        _, start_time, _availability_id = item["SK"].split("#", 2)
        end_time = item.get("endTime")
        if not end_time or end_time <= start_time:
            continue
        events.append((start_time, 1, item["userId"]))  # 1: 開始
        events.append((end_time, 0, item["userId"]))  # 0: 終了（同時刻なら開始より先に処理）

    events.sort(key=lambda e: (e[0], e[1]))

    active_counts = {}
    windows = []
    prev_time = None
    for time, kind, user_id in events:
        if prev_time is not None and time > prev_time and active_counts:
            windows.append((prev_time, time, sorted(active_counts.keys())))
        if kind == 1:
            active_counts[user_id] = active_counts.get(user_id, 0) + 1
        else:
            active_counts[user_id] -= 1
            if active_counts[user_id] <= 0:
                del active_counts[user_id]
        prev_time = time

    merged = []
    for start_time, end_time, member_ids in windows:
        if merged and merged[-1][1] == start_time and merged[-1][2] == member_ids:
            merged[-1] = (merged[-1][0], end_time, member_ids)
        else:
            merged.append((start_time, end_time, member_ids))

    return merged


def _create_candidate(
    table,
    community_id,
    template_id,
    template,
    start_time,
    end_time,
    member_ids,
    community_genre,
):
    profiles = [
        table.get_item(Key={"PK": f"USER#{uid}", "SK": "PROFILE"}).get("Item") or {}
        for uid in member_ids
    ]
    days_since_last_played = [
        _days_since_last_participation(table, uid) for uid in member_ids
    ]
    frequency_status = [
        _frequency_limit_status(table, community_id, uid, community_genre, start_time)
        for uid in member_ids
    ]
    score, reasons = calculate_score(
        template=template,
        members_profiles=profiles,
        members_days_since_last_played=days_since_last_played,
        members_frequency_status=frequency_status,
    )

    candidate_id = generate_id()
    created_at = now_iso_ms()
    candidate_item = {
        "PK": f"COMMUNITY#{community_id}",
        "SK": f"CANDIDATE#{created_at}#{candidate_id}",
        "GSI2PK": f"CANDIDATE#{candidate_id}",
        "GSI2SK": "METADATA",
        "templateId": template_id,
        "score": score,
        "members": set(member_ids),
        "reasons": set(reasons),
        "status": "PENDING",
        "createdAt": created_at,
    }
    table.put_item(Item=candidate_item)

    # DynamoDB物理設計書v1.3 §3.11b: メンバー1人につきCandidateMemberを1行作成し、
    # 事後のダブルブッキング検知（§6.7）と公平性指標（§6.8）の両方に使う。
    for uid in member_ids:
        table.put_item(
            Item={
                "PK": f"COMMUNITY#{community_id}",
                "SK": f"CANDIDATE#{candidate_id}#MEMBER#{uid}",
                "GSI1PK": f"USER#{uid}",
                "GSI1SK": f"CANDIDATE#{start_time}#{candidate_id}",
                "candidateId": candidate_id,
                "startTime": start_time,
                "endTime": end_time,
                "status": "PENDING",
                "conflictWarning": False,
                "createdAt": created_at,
            }
        )

    return candidate_item


def _to_api_candidate(table, community_id, item):
    candidate_id = item["GSI2PK"].split("#", 1)[1]
    members = []
    start_time = None
    end_time = None
    for user_id in sorted(item.get("members", [])):
        candidate_member = (
            table.get_item(
                Key={
                    "PK": f"COMMUNITY#{community_id}",
                    "SK": f"CANDIDATE#{candidate_id}#MEMBER#{user_id}",
                }
            ).get("Item")
            or {}
        )
        # startTime/endTimeはMatchCandidate自体には無く（DynamoDB物理設計書
        # v1.5 §3.8）、全メンバーで共通の値がCandidateMember行にミラーされて
        # いる（event_lambdaのcreate_eventが候補からEventを作る際に行う読み
        # 取りと同一パターン）。フロントの候補レビュー画面が「いつ開催され
        # るか」を表示するために必要。
        if start_time is None:
            start_time = candidate_member.get("startTime")
            end_time = candidate_member.get("endTime")
        members.append(
            {
                "userId": user_id,
                "nickname": get_display_name(table, community_id, user_id),
                # 参考情報のみ (要件定義書v1.2 §17): スコアリング・自動除外
                # には使用しない。
                "fairnessCount": _fairness_count(table, user_id),
                "conflictWarning": candidate_member.get("conflictWarning", False),
            }
        )
    return {
        "candidateId": candidate_id,
        "templateId": item.get("templateId"),
        "score": item.get("score"),
        "status": item.get("status"),
        "reasons": sorted(item.get("reasons", [])),
        "startTime": start_time,
        "endTime": end_time,
        "members": members,
        # Issue #56: 手動作成候補のみ持つ、その場で自由入力したゲーム種別
        # （通常の候補生成はEventTemplate.gameTypeをそのまま使うため無し）。
        "gameType": item.get("gameType"),
        # 候補の生成日時（Issue #28）。管理者が古い候補を選んでしまうと選定〜
        # 全員承認完了までの間にAvailabilityが変わっている可能性が上がるため、
        # 一覧・詳細画面で「新しさ」を認識できるようにする。
        "createdAt": item.get("createdAt"),
    }


def _days_since_last_participation(table, user_id):
    resp = table.query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq(f"USER#{user_id}")
        & Key("GSI1SK").begins_with("PARTICIPANT#"),
        ScanIndexForward=False,
        Limit=1,
    )
    items = resp.get("Items", [])
    if not items:
        return None
    _, last_start_time, _ = items[0]["GSI1SK"].split("#", 2)
    last_dt = datetime.fromisoformat(last_start_time.replace("Z", "+00:00"))
    # startTimeはユーザー入力をそのまま保存しており（Availability登録API参照）、
    # タイムゾーン表記を伴わないことが多い。その場合fromisoformatはoffset-naive
    # なdatetimeを返し、offset-awareなdatetime.now(timezone.utc)との減算で
    # TypeErrorになる（実際にdev環境で確認済み）ため、UTCとして扱う。
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=timezone.utc)
    return max((datetime.now(timezone.utc) - last_dt).days, 0)


def _frequency_limit_status(table, community_id, user_id, community_genre, reference_time):
    """メンバー1人分の参加頻度上限の状態を判定する（Issue #19、要件定義書
    v1.7 §30）。実効上限が未設定、または集計期間内のカウントが上限未満
    なら None（減点対象外）。上限に達している場合のみ、成立理由の文言
    組み立てに必要な情報をdictで返す。
    """
    limit = get_frequency_limit(table, community_id, user_id)
    if limit is None:
        return None
    limit_count, limit_period = limit
    period_start, period_end = period_bounds(reference_time, limit_period)
    count = count_confirmed_events_in_period(
        table, user_id, community_genre, period_start, period_end
    )
    if count < limit_count:
        return None
    return {
        "name": get_display_name(table, community_id, user_id),
        "period": limit_period,
        "limit": limit_count,
        "count": count,
    }


def _fairness_count(table, user_id):
    """§6.8: 直近の期間内で、このユーザーのCandidateMemberレコードのうち
    statusがCONFIRMEDでないもの（＝承認に至らなかった候補に含まれていた
    もの）の件数。MVPの単純化のため読み取りのたびに再計算する。これは
    §6.8自身が明記しているトレードオフに従ったもの（Lambda設計書v1.1 §14
    未決事項5: コミュニティ規模が大きくなった場合は非同期の事前集計を
    再検討すること）。
    """
    from_time = add_days_iso(now_iso_ms(), -_FAIRNESS_WINDOW_DAYS)
    resp = table.query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq(f"USER#{user_id}")
        & Key("GSI1SK").begins_with("CANDIDATE#")
    )
    count = 0
    for item in resp.get("Items", []):
        _, start_time, _ = item["GSI1SK"].split("#", 2)
        if start_time >= from_time and item.get("status") != "CONFIRMED":
            count += 1
    return count
