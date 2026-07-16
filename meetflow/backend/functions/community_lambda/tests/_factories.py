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


def put_community(
    table,
    community_id,
    *,
    owner_id,
    name="テストコミュニティ",
    member_approval_required=False,
    theme_color=None,
):
    item = {
        "PK": f"COMMUNITY#{community_id}",
        "SK": "METADATA",
        "name": name,
        "description": "",
        "genre": "麻雀",
        "memberApprovalRequired": member_approval_required,
        "communityType": "PERSONAL",
        "ownerId": owner_id,
        "createdAt": now_iso_ms(),
    }
    if theme_color:
        item["themeColor"] = theme_color
    table.put_item(Item=item)


def put_membership(
    table,
    community_id,
    user_id,
    *,
    role="MEMBER",
    status="ACTIVE",
    display_name=None,
    sort_order=None,
):
    item = {
        "PK": f"COMMUNITY#{community_id}",
        "SK": f"MEMBER#{user_id}",
        "GSI1PK": f"USER#{user_id}",
        "GSI1SK": f"COMMUNITY#{community_id}",
        "role": role,
        "status": status,
        "joinedAt": now_iso_ms(),
    }
    if display_name:
        item["displayName"] = display_name
    if sort_order is not None:
        item["sortOrder"] = sort_order
    table.put_item(Item=item)


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


def put_invite(table, token, *, community_id, created_by, revoked=False):
    table.put_item(
        Item={
            "PK": f"INVITE#{token}",
            "SK": "METADATA",
            "communityId": community_id,
            "createdBy": created_by,
            "revoked": revoked,
            "createdAt": now_iso_ms(),
        }
    )


def put_join_request(table, community_id, user_id, *, status="PENDING", message=None):
    item = {
        "PK": f"COMMUNITY#{community_id}",
        "SK": f"JOINREQ#{user_id}",
        "GSI1PK": f"USER#{user_id}",
        "GSI1SK": f"JOINREQ#{community_id}",
        "status": status,
        "requestedAt": now_iso_ms(),
    }
    if message:
        item["message"] = message
    table.put_item(Item=item)


def body_of(response):
    return json.loads(response["body"])
