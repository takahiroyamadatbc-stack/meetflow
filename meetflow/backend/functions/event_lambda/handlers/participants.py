from boto3.dynamodb.conditions import Key

from meetflow_common import (
    CANCEL_APPROVED,
    EVENT_CONFIRMED,
    EVENT_PARTICIPANT_REJECTED,
    EVENT_STATUS_AWAITING_MEMBER_APPROVAL,
    PARTICIPANT_STATUS_AWAITING_APPROVAL,
    PARTICIPANT_STATUS_REJECTED,
    error_response,
    get_display_name,
    get_table,
    now_iso_ms,
    parse_body,
    put_event,
    require_membership,
    success_response,
    write_operation_log,
)

from ._shared import write_status_history


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
        participants.append(
            {
                "userId": uid,
                "nickname": get_display_name(table, community_id, uid),
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


def approve_participation(user_id, event):
    """F-502b (Issue #10): 承認待ちの参加者本人が自分の参加を承認する。
    候補メンバー全員の承認が完了した時点で初めて、イベントを
    AWAITING_MEMBER_APPROVALからCONFIRMEDへ本確定する（EVENT_CONFIRMEDは
    ここで初めて発行される。仮確定＝confirm_event時点ではまだ発行しない）。
    """
    event_id = event["pathParameters"]["eventId"]
    table = get_table()

    event_item = table.get_item(Key={"PK": f"EVENT#{event_id}", "SK": "METADATA"}).get(
        "Item"
    )
    if event_item is None:
        return error_response("EVENT_NOT_FOUND", "指定したイベントが見つかりません")
    community_id = event_item["GSI1PK"].split("#", 1)[1]

    # create_cancel_requestと同じ認可パターン: 参加者本人の操作は
    # Participant行の存在自体が認可の根拠であり、require_membershipは
    # 呼ばない（コミュニティ規模のMembership確認は不要）。
    participant = table.get_item(
        Key={"PK": f"EVENT#{event_id}", "SK": f"PARTICIPANT#{user_id}"}
    ).get("Item")
    if participant is None:
        return error_response(
            "NOT_A_PARTICIPANT", "イベント参加者ではありません", status_code=403
        )

    approved_at = now_iso_ms()
    try:
        table.update_item(
            Key={"PK": f"EVENT#{event_id}", "SK": f"PARTICIPANT#{user_id}"},
            UpdateExpression="SET #status = :confirmed, approvedAt = :now",
            ConditionExpression="#status = :awaiting",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":confirmed": "CONFIRMED",
                ":awaiting": PARTICIPANT_STATUS_AWAITING_APPROVAL,
                ":now": approved_at,
            },
        )
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return error_response(
            "PARTICIPANT_ALREADY_RESPONDED",
            "既に参加への応答が完了しています",
            status_code=409,
        )

    write_operation_log(
        action="APPROVE_PARTICIPATION",
        user_id=user_id,
        community_id=community_id,
        target_type="Participant",
        target_id=user_id,
    )

    event_status = _finalize_if_all_approved(table, event_id, community_id, user_id)

    return success_response(
        {
            "eventId": event_id,
            "userId": user_id,
            "status": "CONFIRMED",
            "eventStatus": event_status,
        }
    )


def reject_participation(user_id, event):
    """F-502c (Issue #10): 承認待ちの参加者本人が参加を明示的に辞退する。
    システムはイベントを自動ではキャンセルしない（要件定義書§17/§19の
    ヒューマン・イン・ザ・ループ原則）。管理者への通知のみを行い、イベント
    全体の中止判断は既存のcancel_eventに委ねる（欠員補充はMVP対象外のため
    ここでは設計しない）。拒否者が残っている限り、他メンバーが全員承認して
    もfinalize（本確定）はされない（_finalize_if_all_approvedがstatus全件
    CONFIRMEDを要求するため）。
    """
    event_id = event["pathParameters"]["eventId"]
    table = get_table()

    event_item = table.get_item(Key={"PK": f"EVENT#{event_id}", "SK": "METADATA"}).get(
        "Item"
    )
    if event_item is None:
        return error_response("EVENT_NOT_FOUND", "指定したイベントが見つかりません")
    community_id = event_item["GSI1PK"].split("#", 1)[1]

    participant = table.get_item(
        Key={"PK": f"EVENT#{event_id}", "SK": f"PARTICIPANT#{user_id}"}
    ).get("Item")
    if participant is None:
        return error_response(
            "NOT_A_PARTICIPANT", "イベント参加者ではありません", status_code=403
        )

    body = parse_body(event)
    reason = body.get("reason", "")
    if not isinstance(reason, str):
        return error_response("INVALID_PARAMETER", "reasonが不正です")

    rejected_at = now_iso_ms()
    try:
        table.update_item(
            Key={"PK": f"EVENT#{event_id}", "SK": f"PARTICIPANT#{user_id}"},
            UpdateExpression=(
                "SET #status = :rejected, rejectedAt = :now, rejectReason = :reason"
            ),
            ConditionExpression="#status = :awaiting",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":rejected": PARTICIPANT_STATUS_REJECTED,
                ":awaiting": PARTICIPANT_STATUS_AWAITING_APPROVAL,
                ":now": rejected_at,
                ":reason": reason,
            },
        )
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return error_response(
            "PARTICIPANT_ALREADY_RESPONDED",
            "既に参加への応答が完了しています",
            status_code=409,
        )

    write_operation_log(
        action="REJECT_PARTICIPATION",
        user_id=user_id,
        community_id=community_id,
        target_type="Participant",
        target_id=user_id,
    )
    put_event(
        EVENT_PARTICIPANT_REJECTED,
        {"eventId": event_id, "communityId": community_id, "userId": user_id},
    )

    return success_response(
        {"eventId": event_id, "userId": user_id, "status": "REJECTED"}
    )


def _finalize_if_all_approved(table, event_id, community_id, approved_by):
    """全Participant行の状態を確認し、全員CONFIRMEDならイベントを本確定
    （AWAITING_MEMBER_APPROVAL→CONFIRMED）する。1件でもAWAITING_APPROVAL/
    REJECTEDが残っていればfinalizeしない（拒否者がいる限りシステムは自動で
    確定しない -- 要件定義書§17/§19のヒューマン・イン・ザ・ループ原則）。
    """
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"EVENT#{event_id}")
        & Key("SK").begins_with("PARTICIPANT#")
    )
    items = resp.get("Items", [])
    if not items or any(p.get("status") != "CONFIRMED" for p in items):
        return EVENT_STATUS_AWAITING_MEMBER_APPROVAL

    member_ids = sorted(item["SK"].split("#", 1)[1] for item in items)
    try:
        table.update_item(
            Key={"PK": f"EVENT#{event_id}", "SK": "METADATA"},
            UpdateExpression="SET #status = :confirmed",
            ConditionExpression="#status = :awaiting",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":confirmed": "CONFIRMED",
                ":awaiting": EVENT_STATUS_AWAITING_MEMBER_APPROVAL,
            },
        )
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        # 他の承認呼び出しとの無害な競合（既にCONFIRMED）か、承認待ち中に
        # 管理者がイベント全体を中止した（CANCELLED）かのいずれか。後者では
        # EVENT_CONFIRMEDを発行してはならないため、実際の状態を再取得して
        # 判定する（自分自身の承認自体は既に成功しているため、呼び出し元に
        # エラーは返さない）。
        current = (
            table.get_item(Key={"PK": f"EVENT#{event_id}", "SK": "METADATA"}).get(
                "Item"
            )
            or {}
        )
        return current.get("status", EVENT_STATUS_AWAITING_MEMBER_APPROVAL)

    event_item = (
        table.get_item(Key={"PK": f"EVENT#{event_id}", "SK": "METADATA"}).get("Item")
        or {}
    )
    write_status_history(
        table, event_id, EVENT_STATUS_AWAITING_MEMBER_APPROVAL, "CONFIRMED", approved_by
    )
    write_operation_log(
        action="FINALIZE_EVENT",
        user_id=approved_by,
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
            "startTime": event_item.get("startTime"),
            "endTime": event_item.get("endTime"),
        },
    )
    return "CONFIRMED"
