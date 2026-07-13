from boto3.dynamodb.conditions import Key

from meetflow_common import (
    CANCEL_APPROVED,
    error_response,
    get_table,
    now_iso_ms,
    parse_body,
    put_event,
    require_membership,
    success_response,
    write_operation_log,
)


def list_participants(user_id, event):
    """9.1 (API設計書v1.4)."""
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
        & Key("SK").begins_with("PARTICIPANT#")
    )
    participants = []
    for item in resp.get("Items", []):
        uid = item["SK"].split("#", 1)[1]
        profile = table.get_item(Key={"PK": f"USER#{uid}", "SK": "PROFILE"}).get(
            "Item"
        ) or {}
        participants.append(
            {
                "userId": uid,
                "nickname": profile.get("nickname", ""),
                "status": item.get("status"),
            }
        )
    return success_response({"participants": participants})


def create_cancel_request(user_id, event):
    """F-601 (API設計書v1.4 §9.2): 個人の離脱申請。イベント全体の中止
    （F-605/8.4）とは別物。申請だけでは即座には反映されず、管理者が承認
    するまでPENDINGのままとなる（要件定義書v1.2 §15.1: 既に確定済みの
    メンバーに対して即座に「人数減少」通知が飛ぶことを避けるため）。
    """
    event_id = event["pathParameters"]["eventId"]
    table = get_table()

    # 下記のparticipant statusチェックより先にここでチェックする: 成功した
    # キャンセル申請は既にParticipant自身のstatusをCONFIRMEDから変更して
    # いる（CANCEL_REQUESTEDへ）ため、再申請時にstatusチェックを先に行うと
    # 常にそちらが先に発火してしまい、より具体的（かつ正しい）エラーで
    # あるCANCEL_REQUEST_ALREADY_PENDINGではなくNOT_A_PARTICIPANTを誤って
    # 返してしまう。
    existing = table.get_item(
        Key={"PK": f"EVENT#{event_id}", "SK": f"CANCELREQ#{user_id}"}
    ).get("Item")
    if existing is not None and existing.get("status") == "PENDING":
        return error_response(
            "CANCEL_REQUEST_ALREADY_PENDING",
            "既にキャンセル申請済みです",
            status_code=409,
        )

    participant = table.get_item(
        Key={"PK": f"EVENT#{event_id}", "SK": f"PARTICIPANT#{user_id}"}
    ).get("Item")
    if participant is None or participant.get("status") != "CONFIRMED":
        return error_response(
            "NOT_A_PARTICIPANT", "イベント参加者ではありません", status_code=403
        )

    body = parse_body(event)
    reason = body.get("reason", "")
    if not isinstance(reason, str):
        return error_response("INVALID_PARAMETER", "reasonが不正です")

    table.put_item(
        Item={
            "PK": f"EVENT#{event_id}",
            "SK": f"CANCELREQ#{user_id}",
            "reason": reason,
            "status": "PENDING",
            "requestedAt": now_iso_ms(),
        }
    )
    # Participant自身のstatusをCANCEL_REQUESTEDに更新。管理者承認までは
    # CONFIRMEDのまま扱わないが、正式な離脱（CANCELLED）でもない中間状態。
    table.update_item(
        Key={"PK": f"EVENT#{event_id}", "SK": f"PARTICIPANT#{user_id}"},
        UpdateExpression="SET #status = :requested",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={":requested": "CANCEL_REQUESTED"},
    )

    event_item = (
        table.get_item(Key={"PK": f"EVENT#{event_id}", "SK": "METADATA"}).get("Item")
        or {}
    )
    community_id = event_item.get("GSI1PK", "COMMUNITY#").split("#", 1)[1]
    write_operation_log(
        action="CREATE_CANCEL_REQUEST",
        user_id=user_id,
        community_id=community_id,
        target_type="CancelRequest",
        target_id=user_id,
    )
    return success_response({"eventId": event_id, "status": "PENDING"}, status_code=201)


def list_cancel_requests(user_id, event):
    """9.1b (API設計書v1.4, 画面設計書 S-19)."""
    event_id = event["pathParameters"]["eventId"]
    table = get_table()
    event_item = table.get_item(Key={"PK": f"EVENT#{event_id}", "SK": "METADATA"}).get(
        "Item"
    )
    if event_item is None:
        return error_response("EVENT_NOT_FOUND", "指定したイベントが見つかりません")
    community_id = event_item["GSI1PK"].split("#", 1)[1]
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    status_filter = (event.get("queryStringParameters") or {}).get("status", "PENDING")
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"EVENT#{event_id}")
        & Key("SK").begins_with("CANCELREQ#")
    )
    items = resp.get("Items", [])
    if status_filter:
        items = [item for item in items if item.get("status") == status_filter]

    requests = [
        {
            "userId": item["SK"].split("#", 1)[1],
            "reason": item.get("reason", ""),
            "status": item.get("status"),
            "requestedAt": item.get("requestedAt"),
        }
        for item in items
    ]
    return success_response({"cancelRequests": requests})


def approve_cancel_request(user_id, event):
    """F-602 (API設計書v1.4 §9.3)。`ConditionExpression: status=PENDING`
    により二重承認を防止する（DynamoDB物理設計書v1.3 §3.12）。"""
    event_id = event["pathParameters"]["eventId"]
    target_user_id = event["pathParameters"]["userId"]
    table = get_table()

    event_item = table.get_item(Key={"PK": f"EVENT#{event_id}", "SK": "METADATA"}).get(
        "Item"
    )
    if event_item is None:
        return error_response("EVENT_NOT_FOUND", "指定したイベントが見つかりません")
    community_id = event_item["GSI1PK"].split("#", 1)[1]
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    cancel_request = table.get_item(
        Key={"PK": f"EVENT#{event_id}", "SK": f"CANCELREQ#{target_user_id}"}
    ).get("Item")
    if cancel_request is None:
        return error_response(
            "CANCEL_REQUEST_NOT_FOUND", "指定したキャンセル申請が見つかりません"
        )

    try:
        table.update_item(
            Key={"PK": f"EVENT#{event_id}", "SK": f"CANCELREQ#{target_user_id}"},
            UpdateExpression=(
                "SET #status = :approved, approvedBy = :by, approvedAt = :now"
            ),
            ConditionExpression="#status = :pending",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":approved": "APPROVED",
                ":pending": "PENDING",
                ":by": user_id,
                ":now": now_iso_ms(),
            },
        )
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return error_response(
            "CANCEL_REQUEST_ALREADY_PROCESSED",
            "既に処理済みのキャンセル申請です",
            status_code=409,
        )

    table.update_item(
        Key={"PK": f"EVENT#{event_id}", "SK": f"PARTICIPANT#{target_user_id}"},
        UpdateExpression="SET #status = :cancelled",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={":cancelled": "CANCELLED"},
    )

    write_operation_log(
        action="APPROVE_CANCEL_REQUEST",
        user_id=user_id,
        community_id=community_id,
        target_type="CancelRequest",
        target_id=target_user_id,
    )
    # 欠員補充（F-603）はPhase2のため、ここでは通知のみで後続処理は発火し
    # ない（Lambda設計書v1.1 §7.3）。
    put_event(CANCEL_APPROVED, {"eventId": event_id, "userId": target_user_id})

    return success_response(
        {"eventId": event_id, "userId": target_user_id, "status": "APPROVED"}
    )
