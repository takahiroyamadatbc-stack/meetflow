from boto3.dynamodb.conditions import Key

from meetflow_common import (
    EVENT_CANCELLED,
    EVENT_CONFIRMED,
    error_response,
    generate_id,
    get_table,
    now_iso_ms,
    parse_body,
    put_event,
    require_membership,
    success_response,
    transact_write,
    write_operation_log,
)

from ._shared import (
    list_participant_ids,
    place_exists,
    to_api_event,
    write_status_history,
)


def create_event(user_id, event):
    """F-501 (API設計書v1.4 §8.1).

    Only candidate-based creation is implemented. 機能要件書 F-501 mentions
    manual creation ("手動作成") as an alternative, but DynamoDB物理設計書
    v1.3 §3.10's Event entity has no attribute to hold an intended
    participant list before confirmation (unlike candidate-based creation,
    where MatchCandidate.members already exists) -- there's no documented
    place to persist "who's coming" for a manually-created event prior to
    `confirm_event` creating Participant rows. Implementing it would mean
    inventing an attribute outside the physical design (CLAUDE.md: never
    deviate from the DynamoDB key/attribute design), so it's left
    unsupported pending that gap being resolved in the docs.
    """
    body = parse_body(event)
    candidate_id = body.get("candidateId")
    if not isinstance(candidate_id, str) or not candidate_id:
        return error_response(
            "INVALID_PARAMETER",
            "candidateIdが必要です（手動作成は現在の物理設計では未対応）",
        )

    table = get_table()
    candidate_resp = table.query(
        IndexName="GSI2",
        KeyConditionExpression=Key("GSI2PK").eq(f"CANDIDATE#{candidate_id}"),
        Limit=1,
    )
    candidate_items = candidate_resp.get("Items", [])
    if not candidate_items:
        return error_response("CANDIDATE_NOT_FOUND", "指定した候補が見つかりません")
    candidate = candidate_items[0]
    community_id = candidate["PK"].split("#", 1)[1]
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    if candidate.get("status") != "PENDING":
        return error_response(
            "CANDIDATE_ALREADY_USED", "既にイベント化済みの候補です", status_code=409
        )

    member_ids = sorted(candidate.get("members", []))
    if not member_ids:
        return error_response("CANDIDATE_NOT_FOUND", "指定した候補が見つかりません")

    # startTime/endTime live on CandidateMember rows, not MatchCandidate
    # itself (DynamoDB物理設計書v1.3 §3.8's attribute list has neither).
    sample_member = (
        table.get_item(
            Key={
                "PK": f"COMMUNITY#{community_id}",
                "SK": f"CANDIDATE#{candidate_id}#MEMBER#{member_ids[0]}",
            }
        ).get("Item")
        or {}
    )
    start_time = sample_member.get("startTime")
    end_time = sample_member.get("endTime")

    location_id = body.get("locationId")
    if location_id and not place_exists(table, location_id):
        return error_response("LOCATION_NOT_FOUND", "指定した会場が見つかりません")

    event_id = generate_id()
    created_at = now_iso_ms()
    event_item = {
        "PK": f"EVENT#{event_id}",
        "SK": "METADATA",
        "GSI1PK": f"COMMUNITY#{community_id}",
        "GSI1SK": f"EVENT#{start_time}#{event_id}",
        "templateId": candidate.get("templateId"),
        "candidateId": candidate_id,
        "locationId": location_id,
        "locationNote": body.get("locationNote", ""),
        "status": "PENDING_APPROVAL",
        "startTime": start_time,
        "endTime": end_time,
        "createdAt": created_at,
    }

    # Candidate -> Event is committed atomically: repurposing
    # MatchCandidate.status=CONFIRMED here (there's no separate "USED"
    # value in the PENDING/CONFIRMED/DISCARDED enum, DynamoDB物理設計書
    # v1.3 §3.8) to mean "spoken for", guarded by a ConditionExpression so
    # two concurrent event-creation attempts on the same candidate can't
    # both succeed (CANDIDATE_ALREADY_USED).
    try:
        transact_write(
            [
                {
                    "Update": {
                        "Key": {"PK": f"COMMUNITY#{community_id}", "SK": candidate["SK"]},
                        "UpdateExpression": "SET #status = :confirmed",
                        "ConditionExpression": "#status = :pending",
                        "ExpressionAttributeNames": {"#status": "status"},
                        "ExpressionAttributeValues": {
                            ":confirmed": "CONFIRMED",
                            ":pending": "PENDING",
                        },
                    }
                },
                {
                    "Put": {
                        "Item": event_item,
                        "ConditionExpression": "attribute_not_exists(PK)",
                    }
                },
            ]
        )
    except table.meta.client.exceptions.TransactionCanceledException:
        return error_response(
            "CANDIDATE_ALREADY_USED", "既にイベント化済みの候補です", status_code=409
        )

    # CandidateMember.status mirrors MatchCandidate.status (§3.11b) --
    # best-effort, not part of the transaction above (a brief mirror lag is
    # acceptable for this display-only field).
    for uid in member_ids:
        table.update_item(
            Key={
                "PK": f"COMMUNITY#{community_id}",
                "SK": f"CANDIDATE#{candidate_id}#MEMBER#{uid}",
            },
            UpdateExpression="SET #status = :confirmed",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":confirmed": "CONFIRMED"},
        )

    write_status_history(table, event_id, None, "PENDING_APPROVAL", user_id)
    write_operation_log(
        action="CREATE_EVENT",
        user_id=user_id,
        community_id=community_id,
        target_type="Event",
        target_id=event_id,
    )
    return success_response(to_api_event(table, event_item), status_code=201)


def get_event(user_id, event):
    """F-504 (API設計書v1.4 §8.2)."""
    event_id = event["pathParameters"]["eventId"]
    table = get_table()
    item = table.get_item(Key={"PK": f"EVENT#{event_id}", "SK": "METADATA"}).get("Item")
    if item is None:
        return error_response("EVENT_NOT_FOUND", "指定したイベントが見つかりません")
    community_id = item["GSI1PK"].split("#", 1)[1]
    require_membership(table, community_id, user_id)
    return success_response(to_api_event(table, item))


def confirm_event(user_id, event):
    """F-502 (API設計書v1.4 §8.3, Lambda設計書v1.1 §7.2/§7.2b).

    Runs the double-booking hard check (candidate members vs. already
    CONFIRMED Participant rows, via Participant's GSI1 time-range query)
    *before* the TransactWriteItems that flips the event to CONFIRMED and
    creates Participant rows -- this is the synchronous "実害防止" half of
    the two-layer double-booking design (要件定義書v1.2 §17); the
    asynchronous half (post-hoc conflictWarning on other communities'
    PENDING candidates) lives in MatchingLambda's EventConfirmed
    subscriber.
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

    status = event_item.get("status")
    if status == "CONFIRMED":
        return error_response(
            "EVENT_ALREADY_CONFIRMED", "既に承認済みのイベントです", status_code=409
        )
    if status == "CANCELLED":
        return error_response(
            "EVENT_ALREADY_CANCELLED", "中止済みのイベントです", status_code=409
        )
    if status != "PENDING_APPROVAL":
        return error_response(
            "INVALID_STATUS_TRANSITION", "この状態からは承認できません", status_code=409
        )

    candidate_id = event_item.get("candidateId")
    candidate_resp = table.query(
        IndexName="GSI2",
        KeyConditionExpression=Key("GSI2PK").eq(f"CANDIDATE#{candidate_id}"),
        Limit=1,
    )
    candidate_items = candidate_resp.get("Items", [])
    member_ids = sorted(candidate_items[0].get("members", [])) if candidate_items else []

    start_time = event_item["startTime"]
    end_time = event_item["endTime"]

    for uid in member_ids:
        resp = table.query(
            IndexName="GSI1",
            KeyConditionExpression=Key("GSI1PK").eq(f"USER#{uid}")
            & Key("GSI1SK").between(
                f"PARTICIPANT#{start_time}", f"PARTICIPANT#{end_time}"
            ),
        )
        if any(p.get("status") == "CONFIRMED" for p in resp.get("Items", [])):
            return error_response(
                "PARTICIPANT_SCHEDULE_CONFLICT",
                "参加者に、既に確定済みの別イベントと時間が重複するメンバーがいます",
                status_code=409,
            )

    created_at = now_iso_ms()
    operations = [
        {
            "Update": {
                "Key": {"PK": f"EVENT#{event_id}", "SK": "METADATA"},
                "UpdateExpression": "SET #status = :confirmed",
                "ConditionExpression": "#status = :pending_approval",
                "ExpressionAttributeNames": {"#status": "status"},
                "ExpressionAttributeValues": {
                    ":confirmed": "CONFIRMED",
                    ":pending_approval": "PENDING_APPROVAL",
                },
            }
        }
    ]
    for uid in member_ids:
        operations.append(
            {
                "Put": {
                    "Item": {
                        "PK": f"EVENT#{event_id}",
                        "SK": f"PARTICIPANT#{uid}",
                        "GSI1PK": f"USER#{uid}",
                        "GSI1SK": f"PARTICIPANT#{start_time}#{event_id}",
                        "status": "CONFIRMED",
                        "startTime": start_time,
                        "endTime": end_time,
                        "joinedAt": created_at,
                    },
                    "ConditionExpression": "attribute_not_exists(PK)",
                }
            }
        )

    try:
        transact_write(operations)
    except table.meta.client.exceptions.TransactionCanceledException:
        return error_response(
            "EVENT_ALREADY_CONFIRMED", "既に承認済みのイベントです", status_code=409
        )

    write_status_history(table, event_id, "PENDING_APPROVAL", "CONFIRMED", user_id)
    write_operation_log(
        action="CONFIRM_EVENT",
        user_id=user_id,
        community_id=community_id,
        target_type="Event",
        target_id=event_id,
    )
    put_event(
        EVENT_CONFIRMED,
        {
            "eventId": event_id,
            "communityId": community_id,
            "participantIds": member_ids,
            "startTime": start_time,
            "endTime": end_time,
        },
    )

    return success_response(to_api_event(table, {**event_item, "status": "CONFIRMED"}))


def cancel_event(user_id, event):
    """F-605 (API設計書v1.4 §8.4): cancels the whole event, distinct from a
    single participant's cancel request (F-601/9.2)."""
    event_id = event["pathParameters"]["eventId"]
    table = get_table()
    event_item = table.get_item(Key={"PK": f"EVENT#{event_id}", "SK": "METADATA"}).get(
        "Item"
    )
    if event_item is None:
        return error_response("EVENT_NOT_FOUND", "指定したイベントが見つかりません")

    community_id = event_item["GSI1PK"].split("#", 1)[1]
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    status = event_item.get("status")
    if status == "CANCELLED":
        return error_response(
            "EVENT_ALREADY_CANCELLED", "既に中止済みのイベントです", status_code=409
        )
    if status == "COMPLETED":
        return error_response(
            "INVALID_STATUS_TRANSITION", "終了済みのイベントは中止できません", status_code=409
        )

    table.update_item(
        Key={"PK": f"EVENT#{event_id}", "SK": "METADATA"},
        UpdateExpression="SET #status = :cancelled",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={":cancelled": "CANCELLED"},
    )
    write_status_history(table, event_id, status, "CANCELLED", user_id)
    write_operation_log(
        action="CANCEL_EVENT",
        user_id=user_id,
        community_id=community_id,
        target_type="Event",
        target_id=event_id,
    )

    put_event(
        EVENT_CANCELLED,
        {
            "eventId": event_id,
            "communityId": community_id,
            "participantIds": list_participant_ids(table, event_id),
        },
    )
    return success_response({"eventId": event_id, "status": "CANCELLED"})


def list_community_events(user_id, event):
    """API設計書v1.4 §8.7 (画面設計書 S-17)."""
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    require_membership(table, community_id, user_id)

    status_param = (event.get("queryStringParameters") or {}).get("status")
    status_filter = set(status_param.split(",")) if status_param else None

    resp = table.query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq(f"COMMUNITY#{community_id}")
        & Key("GSI1SK").begins_with("EVENT#"),
    )
    items = resp.get("Items", [])
    if status_filter:
        items = [item for item in items if item.get("status") in status_filter]

    events_out = []
    for item in items:
        location_name = None
        if item.get("locationId"):
            place = table.get_item(
                Key={"PK": f"PLACE#{item['locationId']}", "SK": "METADATA"}
            ).get("Item")
            location_name = place.get("name") if place else None
        events_out.append(
            {
                "eventId": item["PK"].split("#", 1)[1],
                "startTime": item.get("startTime"),
                "locationName": location_name,
                "status": item.get("status"),
            }
        )
    return success_response({"events": events_out})
