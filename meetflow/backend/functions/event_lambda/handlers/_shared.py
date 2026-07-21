"""Helpers shared between events.py and participants.py -- specific to
EventLambda's own entities, unlike the generic cross-domain helpers in the
meetflow_common Layer.
"""

from boto3.dynamodb.conditions import Key

from meetflow_common import now_iso_ms


def to_api_event(table, item):
    location = None
    location_id = item.get("locationId")
    if location_id:
        place = table.get_item(Key={"PK": f"PLACE#{location_id}", "SK": "METADATA"}).get(
            "Item"
        )
        if place:
            location = {
                "placeId": location_id,
                "name": place.get("name"),
                "address": place.get("address", ""),
                "note": place.get("note", ""),
            }
    return {
        "eventId": item["PK"].split("#", 1)[1],
        "communityId": item["GSI1PK"].split("#", 1)[1],
        "templateId": item.get("templateId"),
        "candidateId": item.get("candidateId"),
        "status": item.get("status"),
        "startTime": item.get("startTime"),
        "endTime": item.get("endTime"),
        "location": location,
        "locationNote": item.get("locationNote", ""),
        "memo": item.get("memo", ""),
        "createdAt": item.get("createdAt"),
    }


def write_status_history(table, event_id, from_status, to_status, changed_by):
    """要件定義書v1.2 §14 lifecycle; DynamoDB物理設計書v1.3 §3.16."""
    created_at = now_iso_ms()
    table.put_item(
        Item={
            "PK": f"EVENT#{event_id}",
            "SK": f"STATUS#{created_at}",
            "fromStatus": from_status,
            "toStatus": to_status,
            "changedBy": changed_by,
            "createdAt": created_at,
        }
    )


def place_exists(table, place_id):
    return (
        table.get_item(Key={"PK": f"PLACE#{place_id}", "SK": "METADATA"}).get("Item")
        is not None
    )


def list_participant_ids(table, event_id):
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"EVENT#{event_id}")
        & Key("SK").begins_with("PARTICIPANT#")
    )
    return [item["SK"].split("#", 1)[1] for item in resp.get("Items", [])]
