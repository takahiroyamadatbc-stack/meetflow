from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key

from meetflow_common import (
    add_days_iso,
    error_response,
    generate_id,
    get_table,
    now_iso_ms,
    parse_body,
    require_membership,
    success_response,
)

from .scoring import calculate_score

_MATCHING_WINDOW_DAYS = 30  # not specified in docs; MVP search horizon for F-401
_FAIRNESS_WINDOW_DAYS = 45  # docs: "直近30〜60日"; MVP picks the midpoint


def generate_candidates(user_id, event):
    """F-401 (API設計書v1.4 §6.1). MVP: manual admin trigger only
    (Lambda設計書v1.1 §6.6) -- kept independent of *how* it's invoked so a
    future scheduled/automatic trigger can call the same logic without new
    API surface.
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

    # NO_CANDIDATES_FOUND (エラーコード一覧v1.1 §5) is a normal 200 empty
    # result, not an error -- an empty `candidates` list covers it here.
    candidate_items = _run_matching(table, community_id, template_id, template)
    candidates = [_to_api_candidate(table, community_id, item) for item in candidate_items]
    return success_response({"candidates": candidates}, status_code=201)


def list_candidates(user_id, event):
    """F-404 list (API設計書v1.4 §6.2)."""
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"COMMUNITY#{community_id}")
        & Key("SK").begins_with("CANDIDATE#")
    )
    # DynamoDB物理設計書v1.3 §3.8 (MatchCandidate, SK=CANDIDATE#{createdAt}#
    # {id}) and §3.11b (CandidateMember, SK=CANDIDATE#{id}#MEMBER#{userId})
    # share the literal "CANDIDATE#" SK prefix under the same community PK,
    # so this query also returns CandidateMember rows -- MatchCandidate's SK
    # never contains "#MEMBER#", so that's the discriminator.
    candidate_items = [
        item for item in resp.get("Items", []) if "#MEMBER#" not in item["SK"]
    ]
    candidates = [_to_api_candidate(table, community_id, item) for item in candidate_items]
    return success_response({"candidates": candidates})


def get_candidate_detail(user_id, event):
    """F-404 detail (API設計書v1.4 §6.3), resolved via GSI2 without needing
    communityId in the path (DynamoDB物理設計書v1.3 §3.8)."""
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


def _run_matching(table, community_id, template_id, template):
    """F-401 processing flow (Lambda設計書v1.1 §6.3): availability lookup ->
    condition matching (F-402) -> scoring (F-403) -> MatchCandidate +
    CandidateMember persistence.

    Grouping is by exact (startTime, endTime) match, per F-402's "日時一致"
    requirement (an exact match, not an overlap/interval computation).
    """
    from_time = now_iso_ms()
    to_time = add_days_iso(from_time, _MATCHING_WINDOW_DAYS)

    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"COMMUNITY#{community_id}")
        & Key("SK").between(f"AVAIL#{from_time}", f"AVAIL#{to_time}")
    )
    availability_items = resp.get("Items", [])

    game_type = template.get("gameType")
    groups = {}
    for item in availability_items:
        supported_games = item.get("gameTypes")
        if supported_games and game_type not in supported_games:
            continue
        _, start_time, _availability_id = item["SK"].split("#", 2)
        groups.setdefault((start_time, item.get("endTime")), []).append(item)

    min_players = template.get("minPlayers", 1)
    max_players = template.get("maxPlayers", min_players)
    required_members = set(
        (template.get("conditions") or {}).get("requiredMembers", []) or []
    )

    created_candidates = []
    for (start_time, end_time), entries in groups.items():
        member_ids = sorted({entry["userId"] for entry in entries})
        if required_members and not required_members.issubset(member_ids):
            continue
        if len(member_ids) < min_players:
            continue
        if len(member_ids) > max_players:
            # MVP heuristic: keep required members, fill remaining slots
            # deterministically (sorted userId) rather than search every
            # subset -- the docs don't specify a subset-selection method.
            required = [m for m in member_ids if m in required_members]
            optional = [m for m in member_ids if m not in required_members]
            member_ids = sorted(required + optional[: max_players - len(required)])

        candidate_item = _create_candidate(
            table, community_id, template_id, template, start_time, end_time, member_ids
        )
        created_candidates.append(candidate_item)

    return created_candidates


def _create_candidate(
    table, community_id, template_id, template, start_time, end_time, member_ids
):
    profiles = [
        table.get_item(Key={"PK": f"USER#{uid}", "SK": "PROFILE"}).get("Item") or {}
        for uid in member_ids
    ]
    days_since_last_played = [
        _days_since_last_participation(table, uid) for uid in member_ids
    ]
    score, reasons = calculate_score(
        template=template,
        members_profiles=profiles,
        members_days_since_last_played=days_since_last_played,
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

    # DynamoDB物理設計書v1.3 §3.11b: one CandidateMember row per member, used
    # for both post-hoc double-booking detection (§6.7) and the fairness
    # indicator (§6.8).
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
        profile = (
            table.get_item(Key={"PK": f"USER#{user_id}", "SK": "PROFILE"}).get("Item")
            or {}
        )
        members.append(
            {
                "userId": user_id,
                "nickname": profile.get("nickname", ""),
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
        "members": members,
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
    return max((datetime.now(timezone.utc) - last_dt).days, 0)


def _fairness_count(table, user_id):
    """§6.8: count of this user's CandidateMember records in the trailing
    window whose status isn't CONFIRMED (i.e. they were in a candidate that
    didn't end up getting approved). Recomputed on every read for MVP
    simplicity, per §6.8's own noted tradeoff (Lambda設計書v1.1 §14 未決事項
    5: revisit with async pre-aggregation if community scale grows).
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
