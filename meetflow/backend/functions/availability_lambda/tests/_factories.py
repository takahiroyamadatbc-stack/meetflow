import json

from meetflow_common import now_iso_ms


def api_event(*, path_params=None, body=None, query=None):
    """Builds a minimal API Gateway (Lambda proxy integration) event, as far
    as the individual handler_fn(user_id, event) functions read it -- they
    never touch requestContext/httpMethod/resource themselves, that's
    dispatch()'s job.
    """
    return {
        "pathParameters": path_params or {},
        "body": json.dumps(body) if body is not None else None,
        "queryStringParameters": query,
    }


def put_community(table, community_id, *, owner_id, name="テストコミュニティ"):
    table.put_item(
        Item={
            "PK": f"COMMUNITY#{community_id}",
            "SK": "METADATA",
            "name": name,
            "description": "",
            "genre": "麻雀",
            "memberApprovalRequired": False,
            "communityType": "PERSONAL",
            "ownerId": owner_id,
            "createdAt": now_iso_ms(),
        }
    )


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


def put_profile(table, user_id, *, nickname="ぷれいやー"):
    table.put_item(
        Item={
            "PK": f"USER#{user_id}",
            "SK": "PROFILE",
            "nickname": nickname,
            "bio": "",
            "gameTypes": [],
            "beginnerOk": False,
        }
    )


def put_availability(table, community_id, user_id, *, start_time, end_time, availability_id="avail-1"):
    table.put_item(
        Item={
            "PK": f"COMMUNITY#{community_id}",
            "SK": f"AVAIL#{start_time}#{availability_id}",
            "GSI1PK": f"USER#{user_id}",
            "GSI1SK": f"AVAIL#{start_time}",
            "userId": user_id,
            "endTime": end_time,
            "comment": "",
            "createdAt": now_iso_ms(),
        }
    )


def body_of(response):
    return json.loads(response["body"])
