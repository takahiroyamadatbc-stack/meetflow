"""§6.7 ダブルブッキング事後検知 (Lambda設計書v1.1).

Subscribes to `EventConfirmed` (published by EventLambda on event
confirmation, detail carries the confirmed participants + time range). For
each participant, finds this community's still-PENDING candidates whose
slot overlaps that time range and flags them with conflictWarning=true, then
publishes `CandidateConflictDetected` per affected community so its admins
get notified (NotificationLambda).

Distinct from EventLambda's own `PARTICIPANT_SCHEDULE_CONFLICT` hard check
(Lambda設計書v1.1 §7.2b): that blocks a confirmation outright when a member
already has a confirmed clash; this is a soft, informational flag raised
*after* some other community's event got confirmed, for candidates that
haven't been decided yet. It never auto-excludes anyone (要件定義書v1.2
§17) -- only sets a display-only flag.
"""

from boto3.dynamodb.conditions import Key

from meetflow_common import CANDIDATE_CONFLICT_DETECTED, get_table, put_event


def handle_event_confirmed(event):
    detail = event.get("detail", {})
    participant_ids = detail.get("participantIds", [])
    start_time = detail.get("startTime")
    end_time = detail.get("endTime")
    if not participant_ids or not start_time or not end_time:
        return

    table = get_table()
    affected_communities = set()

    for user_id in participant_ids:
        resp = table.query(
            IndexName="GSI1",
            KeyConditionExpression=Key("GSI1PK").eq(f"USER#{user_id}")
            & Key("GSI1SK").between(f"CANDIDATE#{start_time}", f"CANDIDATE#{end_time}"),
        )
        for candidate_member in resp.get("Items", []):
            if candidate_member.get("status") != "PENDING":
                continue
            table.update_item(
                Key={"PK": candidate_member["PK"], "SK": candidate_member["SK"]},
                UpdateExpression="SET conflictWarning = :true",
                ExpressionAttributeValues={":true": True},
            )
            affected_communities.add(candidate_member["PK"].split("#", 1)[1])

    for community_id in affected_communities:
        put_event(CANDIDATE_CONFLICT_DETECTED, {"communityId": community_id})
