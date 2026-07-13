from boto3.dynamodb.conditions import Key

from meetflow_common import (
    error_response,
    get_table,
    now_iso_ms,
    require_membership,
    success_response,
    transact_write,
    write_operation_log,
)

# JoinRequest is keyed as SK=JOINREQ#{userId} (DynamoDB物理設計書v1.3 §3.5) --
# there is no separate generated request id in the physical design, even
# though API設計書v1.4's paths call this path segment `{requestId}`. Every
# handler here treats that path parameter as the target user's id.


def list_join_requests(user_id, event):
    """GET /communities/{communityId}/join-requests (API設計書v1.4 §4.6,
    画面設計書 S-07). Enriches each JoinRequest with the requester's profile
    since a nickname alone isn't enough for an admin to decide (API設計書
    v1.4 changelog v1.2->v1.3)."""
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    status_filter = (event.get("queryStringParameters") or {}).get("status", "PENDING")

    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"COMMUNITY#{community_id}")
        & Key("SK").begins_with("JOINREQ#")
    )
    items = resp.get("Items", [])
    if status_filter:
        items = [item for item in items if item.get("status") == status_filter]

    requests = []
    for item in items:
        target_user_id = item["SK"].split("#", 1)[1]
        profile = (
            table.get_item(Key={"PK": f"USER#{target_user_id}", "SK": "PROFILE"}).get(
                "Item"
            )
            or {}
        )
        requests.append(
            {
                "requestId": target_user_id,
                "userId": target_user_id,
                "nickname": profile.get("nickname", ""),
                "bio": profile.get("bio", ""),
                "gameTypes": sorted(profile["gameTypes"])
                if profile.get("gameTypes")
                else [],
                "beginnerOk": profile.get("beginnerOk", False),
                "message": item.get("message", ""),
                "status": item.get("status"),
                "requestedAt": item.get("requestedAt"),
            }
        )
    return success_response({"requests": requests})


def approve_join_request(user_id, event):
    """F-104b (API設計書v1.4 §4.4b): JoinRequest status update + Membership
    creation as a single TransactWriteItems call (DynamoDB物理設計書v1.3
    §3.5), so a mid-way failure can't leave an approved request with no
    Membership (or vice versa)."""
    community_id = event["pathParameters"]["communityId"]
    target_user_id = event["pathParameters"]["requestId"]
    table = get_table()
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    join_request = table.get_item(
        Key={"PK": f"COMMUNITY#{community_id}", "SK": f"JOINREQ#{target_user_id}"}
    ).get("Item")
    if join_request is None:
        return error_response("JOIN_REQUEST_NOT_FOUND", "参加リクエストが見つかりません")
    if join_request.get("status") != "PENDING":
        return _already_processed()

    now = now_iso_ms()
    try:
        transact_write(
            [
                {
                    "Update": {
                        "Key": {
                            "PK": f"COMMUNITY#{community_id}",
                            "SK": f"JOINREQ#{target_user_id}",
                        },
                        "UpdateExpression": (
                            "SET #status = :approved, processedAt = :now, "
                            "processedBy = :by"
                        ),
                        "ConditionExpression": "#status = :pending",
                        "ExpressionAttributeNames": {"#status": "status"},
                        "ExpressionAttributeValues": {
                            ":approved": "APPROVED",
                            ":pending": "PENDING",
                            ":now": now,
                            ":by": user_id,
                        },
                    }
                },
                {
                    "Put": {
                        "Item": {
                            "PK": f"COMMUNITY#{community_id}",
                            "SK": f"MEMBER#{target_user_id}",
                            "GSI1PK": f"USER#{target_user_id}",
                            "GSI1SK": f"COMMUNITY#{community_id}",
                            "role": "MEMBER",
                            "status": "ACTIVE",
                            "joinedAt": now,
                        },
                        "ConditionExpression": "attribute_not_exists(PK)",
                    }
                },
            ]
        )
    except table.meta.client.exceptions.TransactionCanceledException:
        return _already_processed()

    write_operation_log(
        action="ADD_MEMBER",
        user_id=user_id,
        community_id=community_id,
        target_type="Membership",
        target_id=target_user_id,
    )
    return success_response(
        {"communityId": community_id, "userId": target_user_id, "status": "ACTIVE"}
    )


def reject_join_request(user_id, event):
    """F-104c (API設計書v1.4 §4.4c)."""
    community_id = event["pathParameters"]["communityId"]
    target_user_id = event["pathParameters"]["requestId"]
    table = get_table()
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    join_request = table.get_item(
        Key={"PK": f"COMMUNITY#{community_id}", "SK": f"JOINREQ#{target_user_id}"}
    ).get("Item")
    if join_request is None:
        return error_response("JOIN_REQUEST_NOT_FOUND", "参加リクエストが見つかりません")

    try:
        table.update_item(
            Key={
                "PK": f"COMMUNITY#{community_id}",
                "SK": f"JOINREQ#{target_user_id}",
            },
            UpdateExpression=(
                "SET #status = :rejected, processedAt = :now, processedBy = :by"
            ),
            ConditionExpression="#status = :pending",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":rejected": "REJECTED",
                ":pending": "PENDING",
                ":now": now_iso_ms(),
                ":by": user_id,
            },
        )
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return _already_processed()

    write_operation_log(
        action="REJECT_JOIN_REQUEST",
        user_id=user_id,
        community_id=community_id,
        target_type="JoinRequest",
        target_id=target_user_id,
    )
    return success_response(
        {"communityId": community_id, "userId": target_user_id, "status": "REJECTED"}
    )


def _already_processed():
    return error_response(
        "JOIN_REQUEST_ALREADY_PROCESSED",
        "既に処理済みの参加リクエストです",
        status_code=409,
    )
