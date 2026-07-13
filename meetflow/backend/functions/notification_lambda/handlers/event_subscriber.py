"""F-701 (Lambda設計書v1.1 §9): creates in-app Notification records off the
EventBridge events published by EventLambda/MatchingLambda.

MVP has only the in-app channel -- no email/push/LINE (AWSシステム構成設計書
v1.2 §11, resolving that doc's earlier SES-vs-in-app contradiction in favor
of 要件定義書/機能要件書).
"""

from boto3.dynamodb.conditions import Key

from meetflow_common import (
    CANCEL_APPROVED,
    CANDIDATE_CONFLICT_DETECTED,
    EVENT_CANCELLED,
    EVENT_CONFIRMED,
    generate_id,
    get_table,
    now_iso_ms,
)

_MESSAGES = {
    "CONFIRMED": "参加予定のイベントが確定しました。",
    "CANCELLED": "参加予定だったイベントが中止になりました。",
    "CANCEL_APPROVED": "キャンセル申請が承認されました。",
    "CANDIDATE_CONFLICT": "候補メンバーに他コミュニティとの日程重複が検知されました。",
}


def handle_domain_event(event):
    detail_type = event.get("detail-type")
    detail = event.get("detail", {})
    table = get_table()

    if detail_type == EVENT_CONFIRMED:
        for user_id in detail.get("participantIds", []):
            _create_notification(
                table, user_id, "CONFIRMED", detail.get("eventId")
            )
    elif detail_type == EVENT_CANCELLED:
        for user_id in detail.get("participantIds", []):
            _create_notification(
                table, user_id, "CANCELLED", detail.get("eventId")
            )
    elif detail_type == CANCEL_APPROVED:
        user_id = detail.get("userId")
        if user_id:
            _create_notification(
                table, user_id, "CANCEL_APPROVED", detail.get("eventId")
            )
        # 欠員補充（F-603）はPhase2のため、ここでは本人への受理通知のみで
        # 完結する（Lambda設計書v1.1 §7.3）。
    elif detail_type == CANDIDATE_CONFLICT_DETECTED:
        community_id = detail.get("communityId")
        if community_id:
            for admin_id in _list_admin_user_ids(table, community_id):
                _create_notification(table, admin_id, "CANDIDATE_CONFLICT", None)


def _list_admin_user_ids(table, community_id):
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"COMMUNITY#{community_id}")
        & Key("SK").begins_with("MEMBER#")
    )
    return [
        item["SK"].split("#", 1)[1]
        for item in resp.get("Items", [])
        if item.get("role") in ("OWNER", "ADMIN")
    ]


def _create_notification(table, user_id, notif_type, related_event_id):
    notification_id = generate_id()
    created_at = now_iso_ms()
    item = {
        "PK": f"USER#{user_id}",
        "SK": f"NOTIF#{created_at}#{notification_id}",
        "type": notif_type,
        "message": _MESSAGES[notif_type],
        "read": False,
        "createdAt": created_at,
    }
    if related_event_id:
        item["relatedEventId"] = related_event_id
    table.put_item(Item=item)
