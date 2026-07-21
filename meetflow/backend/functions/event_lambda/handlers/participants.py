from boto3.dynamodb.conditions import Key

from meetflow_common import (
    CANCEL_APPROVED,
    EVENT_CONFIRMED,
    EVENT_PARTICIPANT_REJECTED,
    EVENT_STATUS_AWAITING_MEMBER_APPROVAL,
    PARTICIPANT_STATUS_AWAITING_APPROVAL,
    PARTICIPANT_STATUS_REJECTED,
    RESERVED_PARTICIPANT_STATUSES,
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
        # Issue #63: cancel_eventがCONFIRMED状態のParticipant行をCANCELLED
        # へ更新するようになったため、承認待ち中にイベントが中止された場合、
        # ここでの判定は「まだ全員承認済みではない」ではなく「一部が中止に
        # よりCANCELLEDになった」ケースも通るようになった。いずれの場合も
        # AWAITING_MEMBER_APPROVALと決め打ちにせず、Event側の実際の状態を
        # 返す（中止済みならCANCELLEDを正しく返す）。
        current = (
            table.get_item(Key={"PK": f"EVENT#{event_id}", "SK": "METADATA"}).get(
                "Item"
            )
            or {}
        )
        return current.get("status", EVENT_STATUS_AWAITING_MEMBER_APPROVAL)

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


def _check_confirmed_and_not_started(event_item):
    """Issue #78 (F-603のMVP前倒し): 確定後のメンバー追加・削除どちらも、
    対象イベントがCONFIRMEDかつ開始前であることを共通の前提とする
    （開始後・成績確定後は不可）。
    """
    if event_item.get("status") != "CONFIRMED":
        return error_response(
            "INVALID_STATUS_TRANSITION",
            "確定済みのイベントのみ参加者を変更できます",
            status_code=409,
        )
    if event_item.get("startTime", "") <= now_iso_ms():
        return error_response(
            "INVALID_STATUS_TRANSITION",
            "開始済みのイベントの参加者は変更できません",
            status_code=409,
        )
    return None


def _count_reserved_participants(table, event_id):
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"EVENT#{event_id}")
        & Key("SK").begins_with("PARTICIPANT#")
    )
    return sum(
        1 for item in resp.get("Items", []) if item.get("status") in RESERVED_PARTICIPANT_STATUSES
    )


def add_participant(user_id, event):
    """9.6 (Issue #78、F-603のMVP前倒し)。管理者が確定済みイベントに、
    コミュニティメンバーを1名任意に追加する。候補ベースの承認フロー
    （confirm_event）とは別の、管理者主導・即時確定の経路。
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

    status_error = _check_confirmed_and_not_started(event_item)
    if status_error:
        return status_error

    body = parse_body(event)
    target_user_id = body.get("userId")
    if not isinstance(target_user_id, str) or not target_user_id:
        return error_response("INVALID_PARAMETER", "userIdは必須です")

    membership = table.get_item(
        Key={"PK": f"COMMUNITY#{community_id}", "SK": f"MEMBER#{target_user_id}"}
    ).get("Item")
    if membership is None or membership.get("status") != "ACTIVE":
        return error_response(
            "INVALID_PARAMETER", "対象ユーザーはこのコミュニティのアクティブなメンバーではありません"
        )

    existing = table.get_item(
        Key={"PK": f"EVENT#{event_id}", "SK": f"PARTICIPANT#{target_user_id}"}
    ).get("Item")
    if existing is not None and existing.get("status") in RESERVED_PARTICIPANT_STATUSES:
        return error_response(
            "INVALID_PARAMETER", "既にこのイベントの参加者です", status_code=409
        )

    start_time = event_item["startTime"]
    end_time = event_item["endTime"]

    template_id = event_item.get("templateId")
    if template_id is not None:
        template = table.get_item(
            Key={"PK": f"COMMUNITY#{community_id}", "SK": f"TEMPLATE#{template_id}"}
        ).get("Item")
        if template is not None:
            max_players = template.get("maxPlayers")
            if max_players is not None and _count_reserved_participants(
                table, event_id
            ) + 1 > max_players:
                return error_response(
                    "INVALID_PARAMETER",
                    f"参加者の上限({max_players}人)を超えるため追加できません",
                    status_code=409,
                )

    # confirm_eventと同じ同期ハードチェック（要件定義書v1.2 §17）。
    resp = table.query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq(f"USER#{target_user_id}")
        & Key("GSI1SK").between(f"PARTICIPANT#{start_time}", f"PARTICIPANT#{end_time}"),
    )
    for p in resp.get("Items", []):
        if p.get("status") not in RESERVED_PARTICIPANT_STATUSES:
            continue
        conflicting_event_id = p["PK"].split("#", 1)[1]
        conflicting_event = table.get_item(
            Key={"PK": f"EVENT#{conflicting_event_id}", "SK": "METADATA"}
        ).get("Item")
        if conflicting_event and conflicting_event.get("status") == "CANCELLED":
            continue
        return error_response(
            "PARTICIPANT_SCHEDULE_CONFLICT",
            "対象ユーザーは、既に確定済みまたは承認待ちの別イベントと時間が重複しています",
            status_code=409,
        )

    community_item = table.get_item(
        Key={"PK": f"COMMUNITY#{community_id}", "SK": "METADATA"}
    ).get("Item") or {}

    joined_at = now_iso_ms()
    table.put_item(
        Item={
            "PK": f"EVENT#{event_id}",
            "SK": f"PARTICIPANT#{target_user_id}",
            "GSI1PK": f"USER#{target_user_id}",
            "GSI1SK": f"PARTICIPANT#{start_time}#{event_id}",
            "status": "CONFIRMED",
            "startTime": start_time,
            "endTime": end_time,
            "joinedAt": joined_at,
            "communityGenre": community_item.get("genre", ""),
        }
    )

    write_operation_log(
        action="ADD_PARTICIPANT",
        user_id=user_id,
        community_id=community_id,
        target_type="Participant",
        target_id=target_user_id,
    )

    return success_response(
        {
            "eventId": event_id,
            "userId": target_user_id,
            "nickname": get_display_name(table, community_id, target_user_id),
            "status": "CONFIRMED",
        },
        status_code=201,
    )


def remove_participant(user_id, event):
    """9.7 (Issue #78、F-603のMVP前倒し)。管理者が確定済みイベントから、
    本人同意なしに参加者を強制的に取り消す。既存のキャンセル申請
    （F-601/602、本人発・管理者承認）とは別の、管理者主導の経路。
    削除の結果minPlayersを割り込んでもイベントは自動中止しない
    （`belowMinPlayers`フラグで管理者に警告表示するのみ、要件はブレスト
    時の合意事項）。
    """
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

    status_error = _check_confirmed_and_not_started(event_item)
    if status_error:
        return status_error

    participant = table.get_item(
        Key={"PK": f"EVENT#{event_id}", "SK": f"PARTICIPANT#{target_user_id}"}
    ).get("Item")
    if participant is None or participant.get("status") not in RESERVED_PARTICIPANT_STATUSES:
        return error_response(
            "PARTICIPANT_NOT_FOUND", "指定した参加者が見つかりません"
        )

    table.update_item(
        Key={"PK": f"EVENT#{event_id}", "SK": f"PARTICIPANT#{target_user_id}"},
        UpdateExpression="SET #status = :cancelled, removedBy = :by, removedAt = :now",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":cancelled": "CANCELLED",
            ":by": user_id,
            ":now": now_iso_ms(),
        },
    )

    write_operation_log(
        action="REMOVE_PARTICIPANT",
        user_id=user_id,
        community_id=community_id,
        target_type="Participant",
        target_id=target_user_id,
    )

    remaining_count = _count_reserved_participants(table, event_id)
    below_min_players = False
    template_id = event_item.get("templateId")
    if template_id is not None:
        template = table.get_item(
            Key={"PK": f"COMMUNITY#{community_id}", "SK": f"TEMPLATE#{template_id}"}
        ).get("Item")
        min_players = (template or {}).get("minPlayers")
        if min_players is not None and remaining_count < min_players:
            below_min_players = True

    return success_response(
        {
            "eventId": event_id,
            "userId": target_user_id,
            "status": "CANCELLED",
            "remainingParticipantCount": remaining_count,
            "belowMinPlayers": below_min_players,
        }
    )
