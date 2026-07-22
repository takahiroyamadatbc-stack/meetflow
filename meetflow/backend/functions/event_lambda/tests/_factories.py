import json

from meetflow_common import now_iso_ms


def api_event(*, path_params=None, body=None, query=None):
    return {
        "pathParameters": path_params or {},
        "body": json.dumps(body) if body is not None else None,
        "queryStringParameters": query,
    }


def domain_event(detail_type, detail):
    return {"detail-type": detail_type, "source": "meetflow.events", "detail": detail}


def put_community(table, community_id, *, owner_id="user-1", genre="麻雀"):
    table.put_item(
        Item={
            "PK": f"COMMUNITY#{community_id}",
            "SK": "METADATA",
            "name": "テストコミュニティ",
            "description": "",
            "genre": genre,
            "memberApprovalRequired": False,
            "communityType": "PERSONAL",
            "ownerId": owner_id,
            "createdAt": now_iso_ms(),
        }
    )


def put_membership(
    table, community_id, user_id, *, role="MEMBER", status="ACTIVE", display_name=None
):
    item = {
        "PK": f"COMMUNITY#{community_id}",
        "SK": f"MEMBER#{user_id}",
        "GSI1PK": f"USER#{user_id}",
        "GSI1SK": f"COMMUNITY#{community_id}",
        "role": role,
        "status": status,
        "joinedAt": now_iso_ms(),
    }
    if display_name:
        item["displayName"] = display_name
    table.put_item(Item=item)


def put_profile(table, user_id, *, nickname="ぷれいやー", auto_approve=None):
    item = {"PK": f"USER#{user_id}", "SK": "PROFILE", "nickname": nickname, "bio": ""}
    if auto_approve is not None:
        item["autoApprove"] = auto_approve
    table.put_item(Item=item)


def put_place(table, community_id, place_id, *, name="雀荘A"):
    table.put_item(
        Item={
            "PK": f"PLACE#{place_id}",
            "SK": "METADATA",
            "GSI1PK": f"COMMUNITY#{community_id}",
            "GSI1SK": f"PLACE#{place_id}",
            "name": name,
            "address": "",
            "ownerType": "COMMUNITY",
            "ownerId": community_id,
            "note": "",
            "createdAt": now_iso_ms(),
        }
    )


def put_candidate(
    table,
    community_id,
    candidate_id,
    member_ids,
    *,
    template_id="template-1",
    start_time="2026-08-05T19:00:00.000Z",
    end_time="2026-08-05T23:00:00.000Z",
    status="PENDING",
):
    table.put_item(
        Item={
            "PK": f"COMMUNITY#{community_id}",
            "SK": f"CANDIDATE#{start_time}#{candidate_id}",
            "GSI2PK": f"CANDIDATE#{candidate_id}",
            "GSI2SK": "METADATA",
            "templateId": template_id,
            "score": 80,
            "members": set(member_ids),
            "reasons": {"全員予定一致"},
            "status": status,
            "createdAt": now_iso_ms(),
        }
    )
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
                "status": status,
                "conflictWarning": False,
                "createdAt": now_iso_ms(),
            }
        )
    return start_time, end_time


def put_event_template(table, community_id, template_id, *, min_players=2, max_players=4):
    table.put_item(
        Item={
            "PK": f"COMMUNITY#{community_id}",
            "SK": f"TEMPLATE#{template_id}",
            "gameType": "MAHJONG4",
            "minPlayers": min_players,
            "maxPlayers": max_players,
            "priority": 1,
            "createdAt": now_iso_ms(),
        }
    )


def put_event_status(table, event_id, status):
    """Directly overrides an already-created Event's status -- for states
    (e.g. COMPLETED) that no handler in this domain can produce yet."""
    table.update_item(
        Key={"PK": f"EVENT#{event_id}", "SK": "METADATA"},
        UpdateExpression="SET #status = :s",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={":s": status},
    )


def put_availability(
    table,
    community_id,
    user_id,
    availability_id,
    *,
    start_time,
    end_time,
    comment="",
    game_types=None,
):
    item = {
        "PK": f"COMMUNITY#{community_id}",
        "SK": f"AVAIL#{start_time}#{availability_id}",
        "GSI1PK": f"USER#{user_id}",
        "GSI1SK": f"AVAIL#{start_time}",
        "userId": user_id,
        "endTime": end_time,
        "comment": comment,
        "createdAt": now_iso_ms(),
    }
    if game_types:
        item["gameTypes"] = set(game_types)
    table.put_item(Item=item)


def put_confirmed_event(
    table,
    community_id,
    event_id,
    *,
    template_id="template-1",
    start_time="2026-08-05T19:00:00.000Z",
    end_time="2026-08-05T23:00:00.000Z",
    status="CONFIRMED",
):
    """Issue #97のavailability_subscriberテスト用: `events.create_event`を
    経由せず、実際のEvent Item（DynamoDB物理設計書v1.23 §3.10）と同じ形
    （PK/SK + GSI1）を直接投入する。"""
    table.put_item(
        Item={
            "PK": f"EVENT#{event_id}",
            "SK": "METADATA",
            "GSI1PK": f"COMMUNITY#{community_id}",
            "GSI1SK": f"EVENT#{start_time}#{event_id}",
            "templateId": template_id,
            "status": status,
            "startTime": start_time,
            "endTime": end_time,
            "createdAt": now_iso_ms(),
        }
    )


def put_confirmed_participant(
    table, user_id, *, start_time, end_time, event_id="other-event", status="CONFIRMED"
):
    """別イベント向けのParticipant行を投入し、confirm_eventの
    PARTICIPANT_SCHEDULE_CONFLICTハードチェックを発火させる。statusを
    AWAITING_APPROVALにすれば、仮確定＝承認待ち中のメンバーとの重複検知も
    テストできる（Issue #10でRESERVED_PARTICIPANT_STATUSESに追加された対象）。
    """
    table.put_item(
        Item={
            "PK": f"EVENT#{event_id}",
            "SK": f"PARTICIPANT#{user_id}",
            "GSI1PK": f"USER#{user_id}",
            "GSI1SK": f"PARTICIPANT#{start_time}#{event_id}",
            "status": status,
            "startTime": start_time,
            "endTime": end_time,
            "joinedAt": now_iso_ms(),
        }
    )


def body_of(response):
    return json.loads(response["body"])
