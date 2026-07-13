import json

from meetflow_common import now_iso_ms


def api_event(*, path_params=None, body=None, query=None):
    return {
        "pathParameters": path_params or {},
        "body": json.dumps(body) if body is not None else None,
        "queryStringParameters": query,
    }


def put_membership(table, community_id, user_id, *, role="MEMBER", status="ACTIVE"):
    table.put_item(
        Item={
            "PK": f"COMMUNITY#{community_id}",
            "SK": f"MEMBER#{user_id}",
            "GSI1PK": f"USER#{user_id}",
            "GSI1SK": f"COMMUNITY#{community_id}",
            "role": role,
            "status": status,
            "joinedAt": now_iso_ms(),
        }
    )


def put_event(table, event_id, community_id, *, status="COMPLETED"):
    table.put_item(
        Item={
            "PK": f"EVENT#{event_id}",
            "SK": "METADATA",
            "GSI1PK": f"COMMUNITY#{community_id}",
            "GSI1SK": f"EVENT#2026-08-05T19:00:00.000Z#{event_id}",
            "status": status,
            "startTime": "2026-08-05T19:00:00.000Z",
            "endTime": "2026-08-05T23:00:00.000Z",
            "createdAt": now_iso_ms(),
        }
    )


def body_of(response):
    return json.loads(response["body"])
