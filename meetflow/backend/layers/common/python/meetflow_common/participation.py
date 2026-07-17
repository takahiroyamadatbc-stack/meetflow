"""コミュニティ退会（自主退会・強制退会）が未来の確定参加をブロックするための
共通判定ロジック（Issue #25/#26）。

Participantエンティティ自体はcommunityIdを持たない（PK=EVENT#{eventId}、
DynamoDB物理設計書v1.11 §3.11）ため、GSI1（USER#{userId}）でユーザーの
参加行を横断取得したうえで、該当するEventをGetItemしてGSI1PK
（COMMUNITY#{communityId}）から紐づくコミュニティを判定する。
"""

from boto3.dynamodb.conditions import Key

from .event_status import RESERVED_PARTICIPANT_STATUSES
from .time_utils import now_iso_ms


def has_upcoming_reserved_participation(
    table, user_id: str, community_id: str
) -> bool:
    """あるユーザーが、指定コミュニティ発のイベントで、開催日時が未来かつ
    予約済み（CONFIRMED/AWAITING_APPROVAL、RESERVED_PARTICIPANT_STATUSES）な
    参加を1件でも持つか判定する。ダブルブッキング事前チェック（confirm_event）
    と同じ「仮確定時点で時間枠は事実上予約済み」という扱いに合わせる。
    """
    now = now_iso_ms()
    resp = table.query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq(f"USER#{user_id}")
        & Key("GSI1SK").begins_with("PARTICIPANT#"),
    )
    for item in resp.get("Items", []):
        if item.get("status") not in RESERVED_PARTICIPANT_STATUSES:
            continue
        start_time = item.get("startTime")
        if not start_time or start_time <= now:
            continue
        event_id = item["PK"].split("#", 1)[1]
        event_item = table.get_item(
            Key={"PK": f"EVENT#{event_id}", "SK": "METADATA"}
        ).get("Item")
        if event_item and event_item.get("GSI1PK") == f"COMMUNITY#{community_id}":
            return True
    return False
