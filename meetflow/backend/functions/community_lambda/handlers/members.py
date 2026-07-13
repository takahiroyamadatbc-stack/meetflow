from boto3.dynamodb.conditions import Key

from meetflow_common import (
    error_response,
    get_table,
    parse_body,
    require_membership,
    success_response,
    write_operation_log,
)


def list_members(user_id, event):
    """GET /communities/{communityId}/members (API設計書v1.4 §4.5)."""
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    require_membership(table, community_id, user_id)

    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"COMMUNITY#{community_id}")
        & Key("SK").begins_with("MEMBER#")
    )

    members = []
    for item in resp.get("Items", []):
        member_user_id = item["SK"].split("#", 1)[1]
        profile = (
            table.get_item(Key={"PK": f"USER#{member_user_id}", "SK": "PROFILE"}).get(
                "Item"
            )
            or {}
        )
        members.append(
            {
                "userId": member_user_id,
                "nickname": profile.get("nickname", ""),
                "role": item.get("role"),
                "status": item.get("status"),
                "joinedAt": item.get("joinedAt"),
            }
        )
    return success_response({"members": members})


def update_member(user_id, event):
    """PUT /communities/{communityId}/members/{userId} (F-104: role change,
    suspend, forced removal -- 要件定義書v1.2 §10.3).

    Not in DynamoDB物理設計書v1.3's schema yet, so not implemented here:
    "募集参加制限" (per-member matching/recruitment restriction) has no
    Membership attribute defined for it.
    """
    community_id = event["pathParameters"]["communityId"]
    target_user_id = event["pathParameters"]["userId"]
    table = get_table()
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    target = table.get_item(
        Key={"PK": f"COMMUNITY#{community_id}", "SK": f"MEMBER#{target_user_id}"}
    ).get("Item")
    if target is None:
        return error_response("USER_NOT_FOUND", "対象メンバーが見つかりません")

    body = parse_body(event)
    remove = bool(body.get("remove", False))
    new_status = body.get("status")
    new_role = body.get("role")

    # 要件定義書v1.2 §9 / エラーコード一覧v1.1 LAST_OWNER_CANNOT_LEAVE: the
    # sole OWNER must transfer ownership (owner-transfer endpoint) before
    # leaving or being suspended.
    if (remove or new_status == "SUSPENDED") and target.get("role") == "OWNER":
        return error_response(
            "LAST_OWNER_CANNOT_LEAVE",
            "OWNERの退出・一時停止の前にオーナー移譲が必要です",
            status_code=409,
        )

    if remove:
        table.delete_item(
            Key={"PK": f"COMMUNITY#{community_id}", "SK": f"MEMBER#{target_user_id}"}
        )
        write_operation_log(
            action="REMOVE_MEMBER",
            user_id=user_id,
            community_id=community_id,
            target_type="Membership",
            target_id=target_user_id,
        )
        return success_response(
            {"communityId": community_id, "userId": target_user_id, "removed": True}
        )

    names = {}
    values = {}
    set_clauses = []
    if new_role is not None:
        if new_role not in ("ADMIN", "MEMBER"):
            return error_response(
                "INVALID_PARAMETER",
                "roleはADMIN/MEMBERのみ指定できます（OWNER変更は別API）",
            )
        names["#role"] = "role"
        values[":role"] = new_role
        set_clauses.append("#role = :role")
    if new_status is not None:
        if new_status not in ("ACTIVE", "SUSPENDED"):
            return error_response("INVALID_PARAMETER", "statusが不正です")
        names["#status"] = "status"
        values[":status"] = new_status
        set_clauses.append("#status = :status")

    if not set_clauses:
        return error_response("INVALID_PARAMETER", "更新項目がありません")

    table.update_item(
        Key={"PK": f"COMMUNITY#{community_id}", "SK": f"MEMBER#{target_user_id}"},
        UpdateExpression="SET " + ", ".join(set_clauses),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )
    write_operation_log(
        action="UPDATE_MEMBER",
        user_id=user_id,
        community_id=community_id,
        target_type="Membership",
        target_id=target_user_id,
        after={"role": new_role, "status": new_status},
    )
    return success_response(
        {
            "communityId": community_id,
            "userId": target_user_id,
            "role": new_role or target.get("role"),
            "status": new_status or target.get("status"),
        }
    )
