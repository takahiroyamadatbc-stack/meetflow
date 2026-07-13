from boto3.dynamodb.conditions import Key

from meetflow_common import (
    error_response,
    generate_id,
    get_table,
    now_iso_ms,
    parse_body,
    require_membership,
    success_response,
    transact_write,
    write_operation_log,
)

_MAX_NAME_LENGTH = 50  # not specified in docs; conservative MVP bound


def create_community(user_id, event):
    """F-101 (API設計書v1.4 §4.1). Community creation + owner Membership are
    two plain PutItems, not a transaction -- DynamoDB物理設計書v1.3 §5 only
    lists join request approval / owner transfer / event confirmation as
    needing TransactWriteItems, so this intentionally doesn't go beyond that.
    """
    body = parse_body(event)
    name = body.get("name")
    if not isinstance(name, str) or not (1 <= len(name) <= _MAX_NAME_LENGTH):
        return _invalid_name()

    description = body.get("description", "")
    genre = body.get("genre", "")
    member_approval_required = bool(body.get("memberApprovalRequired", False))

    community_id = generate_id()
    created_at = now_iso_ms()
    table = get_table()

    table.put_item(
        Item={
            "PK": f"COMMUNITY#{community_id}",
            "SK": "METADATA",
            "name": name,
            "description": description,
            "genre": genre,
            "memberApprovalRequired": member_approval_required,
            # MVP always creates PERSONAL communities (DynamoDB物理設計書v1.3
            # §3.2); STORE/OFFICIAL is a Phase3 concern.
            "communityType": "PERSONAL",
            "ownerId": user_id,
            "createdAt": created_at,
        }
    )
    table.put_item(
        Item={
            "PK": f"COMMUNITY#{community_id}",
            "SK": f"MEMBER#{user_id}",
            "GSI1PK": f"USER#{user_id}",
            "GSI1SK": f"COMMUNITY#{community_id}",
            "role": "OWNER",
            "status": "ACTIVE",
            "joinedAt": created_at,
        }
    )
    write_operation_log(
        action="CREATE_COMMUNITY",
        user_id=user_id,
        community_id=community_id,
        target_type="Community",
        target_id=community_id,
    )
    return success_response(
        {
            "communityId": community_id,
            "name": name,
            "description": description,
            "genre": genre,
            "memberApprovalRequired": member_approval_required,
        },
        status_code=201,
    )


def list_communities(user_id, event):
    """GET /communities (API設計書v1.4 §4.2): communities the caller
    belongs to, via GSI1 (`USER#{userId}` / `COMMUNITY#`). Community count
    per user is small at this project's scale (10-30 members per
    community), so a GetItem per community here is simpler than batching.
    """
    table = get_table()
    resp = table.query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq(f"USER#{user_id}")
        & Key("GSI1SK").begins_with("COMMUNITY#"),
    )

    communities = []
    for membership in resp.get("Items", []):
        community_id = membership["GSI1SK"].split("#", 1)[1]
        community = table.get_item(
            Key={"PK": f"COMMUNITY#{community_id}", "SK": "METADATA"}
        ).get("Item")
        if community is None:
            continue
        communities.append(
            {
                "communityId": community_id,
                "name": community.get("name"),
                "description": community.get("description", ""),
                "genre": community.get("genre", ""),
                "role": membership.get("role"),
            }
        )
    return success_response({"communities": communities})


def update_community(user_id, event):
    """PUT /communities/{communityId} (要件定義書v1.2 §10.1: 管理者は情報編集
    を実施できる -> OWNER/ADMIN)."""
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    body = parse_body(event)
    names = {}
    values = {}
    set_clauses = []

    if "name" in body:
        name = body["name"]
        if not isinstance(name, str) or not (1 <= len(name) <= _MAX_NAME_LENGTH):
            return _invalid_name()
        names["#name"] = "name"
        values[":name"] = name
        set_clauses.append("#name = :name")
    if "description" in body:
        names["#description"] = "description"
        values[":description"] = body["description"]
        set_clauses.append("#description = :description")
    if "genre" in body:
        names["#genre"] = "genre"
        values[":genre"] = body["genre"]
        set_clauses.append("#genre = :genre")
    if "memberApprovalRequired" in body:
        names["#mar"] = "memberApprovalRequired"
        values[":mar"] = bool(body["memberApprovalRequired"])
        set_clauses.append("#mar = :mar")

    if not set_clauses:
        return _no_fields_to_update()

    table.update_item(
        Key={"PK": f"COMMUNITY#{community_id}", "SK": "METADATA"},
        UpdateExpression="SET " + ", ".join(set_clauses),
        ConditionExpression="attribute_exists(PK)",
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )
    write_operation_log(
        action="UPDATE_COMMUNITY",
        user_id=user_id,
        community_id=community_id,
        target_type="Community",
        target_id=community_id,
        after=body,
    )
    community = table.get_item(
        Key={"PK": f"COMMUNITY#{community_id}", "SK": "METADATA"}
    ).get("Item")
    return success_response(
        {
            "communityId": community_id,
            "name": community.get("name"),
            "description": community.get("description", ""),
            "genre": community.get("genre", ""),
            "memberApprovalRequired": community.get("memberApprovalRequired", False),
        }
    )


def transfer_owner(user_id, event):
    """F-106 (Lambda設計書v1.1 §4.2): OWNER transfers ownership; the
    previous OWNER reverts to MEMBER (要件定義書v1.2 §9, not demoted to
    ADMIN). Both role changes + Community.ownerId are one TransactWriteItems
    call (DynamoDB物理設計書v1.3 §5) so a partial failure can't leave two
    members simultaneously holding/lacking the OWNER role.
    """
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    require_membership(table, community_id, user_id, roles=("OWNER",))

    body = parse_body(event)
    new_owner_id = body.get("newOwnerId")
    if not isinstance(new_owner_id, str) or not new_owner_id or new_owner_id == user_id:
        return error_response("INVALID_PARAMETER", "移譲先のuserIdが不正です")

    new_owner_membership = table.get_item(
        Key={"PK": f"COMMUNITY#{community_id}", "SK": f"MEMBER#{new_owner_id}"}
    ).get("Item")
    if new_owner_membership is None or new_owner_membership.get("status") == "SUSPENDED":
        return error_response(
            "INVALID_PARAMETER", "移譲先はアクティブなメンバーである必要があります"
        )

    transact_write(
        [
            {
                "Update": {
                    "Key": {
                        "PK": f"COMMUNITY#{community_id}",
                        "SK": f"MEMBER#{new_owner_id}",
                    },
                    "UpdateExpression": "SET #role = :owner",
                    "ExpressionAttributeNames": {"#role": "role"},
                    "ExpressionAttributeValues": {":owner": "OWNER"},
                }
            },
            {
                "Update": {
                    "Key": {"PK": f"COMMUNITY#{community_id}", "SK": f"MEMBER#{user_id}"},
                    "UpdateExpression": "SET #role = :member",
                    "ExpressionAttributeNames": {"#role": "role"},
                    "ExpressionAttributeValues": {":member": "MEMBER"},
                }
            },
            {
                "Update": {
                    "Key": {"PK": f"COMMUNITY#{community_id}", "SK": "METADATA"},
                    "UpdateExpression": "SET ownerId = :new_owner",
                    "ExpressionAttributeValues": {":new_owner": new_owner_id},
                }
            },
        ]
    )
    write_operation_log(
        action="TRANSFER_OWNER",
        user_id=user_id,
        community_id=community_id,
        target_type="Community",
        target_id=community_id,
        before={"ownerId": user_id},
        after={"ownerId": new_owner_id},
    )
    return success_response({"communityId": community_id, "ownerId": new_owner_id})


def _invalid_name():
    return error_response("INVALID_PARAMETER", "コミュニティ名が不正です")


def _no_fields_to_update():
    return error_response("INVALID_PARAMETER", "更新項目がありません")
