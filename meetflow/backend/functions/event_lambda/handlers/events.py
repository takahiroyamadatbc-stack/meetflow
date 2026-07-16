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
    """F-501 (API設計書v1.4 §8.1)。

    候補ベースの作成のみを実装している。機能要件書 F-501は代替案として
    手動作成（「手動作成」）に言及しているが、DynamoDB物理設計書v1.3
    §3.10のEventエンティティには、承認前の参加予定者リストを保持する属性
    が無い（候補ベースの作成ではMatchCandidate.membersが既に存在するのと
    対照的）-- `confirm_event`がParticipant行を作成する前に、手動作成
    イベントの「誰が参加するか」を永続化する場所がドキュメント上定義され
    ていない。これを実装するには物理設計の外側に属性を作ることになって
    しまう（CLAUDE.md: 絶対に逸脱しないこと）ため、このギャップがドキュ
    メント側で解消されるまで未対応のままとする。
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

    # startTime/endTimeはMatchCandidate自体ではなくCandidateMember行に
    # 存在する（DynamoDB物理設計書v1.3 §3.8の属性一覧にはどちらも無い）。
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

    # Candidate -> Eventはアトミックにコミットされる: ここでは
    # MatchCandidate.status=CONFIRMEDを「使用済み」を表すために転用して
    # いる（PENDING/CONFIRMED/DISCARDEDのenumに独立した"USED"値は無い、
    # DynamoDB物理設計書v1.3 §3.8）。ConditionExpressionでガードすること
    # で、同じ候補に対する2つの同時イベント作成試行が両方成功することを
    # 防ぐ（CANDIDATE_ALREADY_USED）。
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

    # CandidateMember.statusはMatchCandidate.statusをミラーする（§3.11b）
    # -- ベストエフォートであり、上記トランザクションには含まれない
    # （表示専用のフィールドなので、ミラーの一時的な遅延は許容できる）。
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
    """F-502 (API設計書v1.4 §8.3, Lambda設計書v1.1 §7.2/§7.2b)。

    イベントをCONFIRMEDに切り替えてParticipant行を作成するTransactWriteItems
    の*前に*、ダブルブッキングのハードチェック（候補メンバーと既に
    CONFIRMEDなParticipant行を、ParticipantのGSI1時間範囲クエリで突き
    合わせる）を実行する -- これは二層のダブルブッキング防止設計
    （要件定義書v1.2 §17）のうち、同期的な「実害防止」側にあたる。非同期
    側（他コミュニティのPENDING候補への事後的なconflictWarning付与）は
    MatchingLambdaのEventConfirmed購読側にある。
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
    """F-605 (API設計書v1.4 §8.4): イベント全体を中止する。参加者個人の
    キャンセル申請（F-601/9.2）とは別物。"""
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
    _reopen_candidate(table, community_id, event_item.get("candidateId"))
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


def _reopen_candidate(table, community_id, candidate_id):
    """イベント全体中止時に、confirm_event/create_eventがCONFIRMED
    （＝使用済み）に転用していたMatchCandidate.statusをPENDINGへ戻し、
    同じ候補から再度イベントを作成できるようにする。これを行わないと、
    中止済みのイベントが残っているように見え、かつ同一候補は
    CANDIDATE_ALREADY_USEDで永久に再利用できなくなってしまう。
    """
    if not candidate_id:
        return
    candidate_resp = table.query(
        IndexName="GSI2",
        KeyConditionExpression=Key("GSI2PK").eq(f"CANDIDATE#{candidate_id}"),
        Limit=1,
    )
    candidate_items = candidate_resp.get("Items", [])
    if not candidate_items:
        return
    candidate = candidate_items[0]

    table.update_item(
        Key={"PK": candidate["PK"], "SK": candidate["SK"]},
        UpdateExpression="SET #status = :pending",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={":pending": "PENDING"},
    )
    for uid in candidate.get("members", []):
        table.update_item(
            Key={
                "PK": f"COMMUNITY#{community_id}",
                "SK": f"CANDIDATE#{candidate_id}#MEMBER#{uid}",
            },
            UpdateExpression="SET #status = :pending",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":pending": "PENDING"},
        )


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
