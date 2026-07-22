"""Issue #97: 確定済み・定員未充足イベントについて、別メンバーの空き予定
更新（AvailabilityLambdaが発行する`AvailabilityUpdated`）が時間帯・ゲーム
種別に合致したら、追加候補が見つかったことをNotificationLambdaへ知らせる。
追加そのものは常に管理者操作（既存の`participants.add_participant`）を経る
（HITL厳守。ここでは検知して通知するだけで、参加者を自動追加しない）。
"""

from boto3.dynamodb.conditions import Key

from meetflow_common import (
    CONFIRMED_EVENT_CANDIDATE_AVAILABLE,
    RESERVED_PARTICIPANT_STATUSES,
    get_table,
    put_event,
)

from .participants import _count_reserved_participants


def handle_availability_updated(event):
    detail = event.get("detail", {})
    community_id = detail.get("communityId")
    user_id = detail.get("userId")
    start_time = detail.get("startTime")
    end_time = detail.get("endTime")
    game_types = detail.get("gameTypes") or []
    if not community_id or not user_id or not start_time or not end_time:
        return

    table = get_table()
    resp = table.query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq(f"COMMUNITY#{community_id}")
        & Key("GSI1SK").begins_with("EVENT#"),
    )
    for item in resp.get("Items", []):
        if item.get("status") != "CONFIRMED":
            continue

        event_start = item.get("startTime")
        event_end = item.get("endTime")
        if not event_start or not event_end:
            continue
        # 半開区間[event_start, event_end)と[start_time, end_time)の重複判定。
        if not (event_start < end_time and start_time < event_end):
            continue

        # Issue #56の手動作成候補由来イベント等、templateIdを持たないイベント
        # はgameType・定員の判断材料が無いため対象外とする（安全側）。
        template_id = item.get("templateId")
        if not template_id:
            continue
        event_id = item["PK"].split("#", 1)[1]
        template = table.get_item(
            Key={"PK": f"COMMUNITY#{community_id}", "SK": f"TEMPLATE#{template_id}"}
        ).get("Item")
        if template is None:
            continue

        required_game_type = template.get("gameType")
        if game_types and required_game_type not in game_types:
            continue

        max_players = template.get("maxPlayers")
        if max_players is not None and _count_reserved_participants(table, event_id) >= max_players:
            continue

        existing_participant = table.get_item(
            Key={"PK": f"EVENT#{event_id}", "SK": f"PARTICIPANT#{user_id}"}
        ).get("Item")
        if (
            existing_participant is not None
            and existing_participant.get("status") in RESERVED_PARTICIPANT_STATUSES
        ):
            continue

        put_event(
            CONFIRMED_EVENT_CANDIDATE_AVAILABLE,
            {
                "eventId": event_id,
                "communityId": community_id,
                "candidateUserId": user_id,
            },
        )
