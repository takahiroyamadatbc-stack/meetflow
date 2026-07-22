"""F-701 (Lambda設計書v1.1 §9): creates in-app Notification records off the
EventBridge events published by EventLambda/MatchingLambda, and (§9.3b,
v1.2追加) fans each one out over Web Push too. MVP channels are in-app +
Web Push only -- no email/LINE (AWSシステム構成設計書v1.3 §11, resolving
that doc's earlier SES-vs-in-app contradiction in favor of 要件定義書/
機能要件書, later extended by v1.3 27章).
"""

import time

from boto3.dynamodb.conditions import Key

from meetflow_common import (
    AVAILABILITY_REQUEST_CREATED,
    CANCEL_APPROVED,
    CANDIDATE_CONFLICT_DETECTED,
    CONFIRMED_EVENT_CANDIDATE_AVAILABLE,
    EVENT_AWAITING_APPROVAL,
    EVENT_CANCELLED,
    EVENT_CONFIRMED,
    EVENT_PARTICIPANT_REJECTED,
    FEEDBACK_REPLIED,
    generate_id,
    get_table,
    now_iso_ms,
)

from handlers import push_sender

# Issue #91: 未読のまま放置された通知が無期限に増え続けないよう、作成時点
# で仮のTTL（90日後）をセットしておく。既読になった時点でnotifications.py
# のmark_readがより短い期限（24時間後）に上書きする。
_UNREAD_TTL_DAYS = 90

_MESSAGES = {
    "CONFIRMED": "参加予定のイベントが確定しました。",
    "CANCELLED": "参加予定だったイベントが中止になりました。",
    "CANCEL_APPROVED": "キャンセル申請が承認されました。",
    "CANDIDATE_CONFLICT": "候補メンバーに他コミュニティとの日程重複が検知されました。",
    "AVAILABILITY_REQUEST": "空き予定の提出が依頼されました。",
    "AWAITING_APPROVAL": "参加予定のイベントについて、参加承認をお願いします。",
    "PARTICIPANT_REJECTED": "参加予定者が承認待ちの参加を辞退しました。イベントの継続についてご確認ください。",
    "FEEDBACK_REPLIED": "投稿したフィードバックに運営者から返信がありました。",
    "CONFIRMED_EVENT_CANDIDATE_AVAILABLE": "確定済みイベントに追加できるメンバーが見つかりました。",
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
    elif detail_type == AVAILABILITY_REQUEST_CREATED:
        community_id = detail.get("communityId")
        if detail.get("targetScope") == "SPECIFIED":
            target_user_ids = detail.get("targetUserIds", [])
        elif community_id:
            target_user_ids = _list_all_member_user_ids(table, community_id)
        else:
            target_user_ids = []
        for target_user_id in target_user_ids:
            _create_notification(
                table,
                target_user_id,
                "AVAILABILITY_REQUEST",
                None,
                related_community_id=community_id,
            )
    elif detail_type == EVENT_AWAITING_APPROVAL:
        for user_id in detail.get("awaitingUserIds", []):
            _create_notification(
                table, user_id, "AWAITING_APPROVAL", detail.get("eventId")
            )
    elif detail_type == EVENT_PARTICIPANT_REJECTED:
        community_id = detail.get("communityId")
        if community_id:
            for admin_id in _list_admin_user_ids(table, community_id):
                _create_notification(
                    table, admin_id, "PARTICIPANT_REJECTED", detail.get("eventId")
                )
    elif detail_type == FEEDBACK_REPLIED:
        target_user_id = detail.get("targetUserId")
        if target_user_id:
            _create_notification(table, target_user_id, "FEEDBACK_REPLIED", None)
    elif detail_type == CONFIRMED_EVENT_CANDIDATE_AVAILABLE:
        community_id = detail.get("communityId")
        if community_id:
            for admin_id in _list_admin_user_ids(table, community_id):
                _create_notification(
                    table,
                    admin_id,
                    "CONFIRMED_EVENT_CANDIDATE_AVAILABLE",
                    detail.get("eventId"),
                )


def _list_admin_user_ids(table, community_id):
    return [
        user_id
        for user_id, role in _list_member_roles(table, community_id)
        if role in ("OWNER", "ADMIN")
    ]


def _list_all_member_user_ids(table, community_id):
    return [user_id for user_id, _ in _list_member_roles(table, community_id)]


def _list_member_roles(table, community_id):
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"COMMUNITY#{community_id}")
        & Key("SK").begins_with("MEMBER#")
    )
    return [
        (item["SK"].split("#", 1)[1], item.get("role")) for item in resp.get("Items", [])
    ]


def _create_notification(
    table, user_id, notif_type, related_event_id, related_community_id=None
):
    notification_id = generate_id()
    created_at = now_iso_ms()
    item = {
        "PK": f"USER#{user_id}",
        "SK": f"NOTIF#{created_at}#{notification_id}",
        "type": notif_type,
        "message": _MESSAGES[notif_type],
        "read": False,
        "createdAt": created_at,
        "ttl": int(time.time()) + _UNREAD_TTL_DAYS * 86400,
    }
    if related_event_id:
        item["relatedEventId"] = related_event_id
    if related_community_id:
        item["relatedCommunityId"] = related_community_id
    table.put_item(Item=item)
    push_sender.send_push_to_user(
        table, user_id, title="MeetFlow", body=_MESSAGES[notif_type], notif_type=notif_type
    )
