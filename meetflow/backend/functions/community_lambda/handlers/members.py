from boto3.dynamodb.conditions import Key

from meetflow_common import (
    error_response,
    get_table,
    is_display_name_taken,
    parse_body,
    require_membership,
    resolve_display_name,
    success_response,
    write_operation_log,
)

_MAX_DISPLAY_NAME_LENGTH = 30


def list_members(user_id, event):
    """GET /communities/{communityId}/members（API設計書v1.4 §4.5）。"""
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
                "nickname": resolve_display_name(item, profile),
                "role": item.get("role"),
                "status": item.get("status"),
                "joinedAt": item.get("joinedAt"),
            }
        )
    return success_response({"members": members})


def update_member(user_id, event):
    """PUT /communities/{communityId}/members/{userId}（F-104: ロール変更、
    一時停止、強制退会 -- 要件定義書v1.2 §10.3）。

    DynamoDB物理設計書v1.3のスキーマにまだ無いため、ここでは未実装:
    「募集参加制限」（メンバーごとのマッチング/募集参加制限）に対応する
    Membership属性は定義されていない。
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

    # 要件定義書v1.2 §9 / エラーコード一覧v1.1 LAST_OWNER_CANNOT_LEAVE: 唯一の
    # OWNERは、退出や一時停止の前に（オーナー移譲用エンドポイントで）
    # オーナー権を移譲しなければならない。
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


def update_my_display_name(user_id, event):
    """PUT /communities/{communityId}/members/me/display-name（F-108:
    コミュニティごとの表示名設定・変更 -- 機能要件書v1.5）。

    自分自身のMembership.displayNameを設定・変更・解除する。空文字列/null
    送信は解除（User.nicknameへのフォールバック表示に戻す）を意味する。
    表示ロジック自体はmeetflow_common.display_nameに一元化している。
    """
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    require_membership(table, community_id, user_id)

    body = parse_body(event)
    raw = body.get("displayName")
    if raw is not None and not isinstance(raw, str):
        return error_response("PROFILE_VALIDATION_ERROR", "表示名が不正です")

    display_name = (raw or "").strip()
    if display_name and len(display_name) > _MAX_DISPLAY_NAME_LENGTH:
        return error_response(
            "PROFILE_VALIDATION_ERROR",
            f"表示名は{_MAX_DISPLAY_NAME_LENGTH}文字以内で入力してください",
        )

    # なりすまし・混同防止: 同一コミュニティ内で他メンバーの実効表示名
    # （displayNameまたはフォールバック後のnickname）と重複しないか確認する。
    if display_name and is_display_name_taken(
        table, community_id, display_name, exclude_user_id=user_id
    ):
        return error_response(
            "DISPLAY_NAME_ALREADY_TAKEN",
            "この名前は既に使われています",
            status_code=409,
        )

    key = {"PK": f"COMMUNITY#{community_id}", "SK": f"MEMBER#{user_id}"}
    if display_name:
        table.update_item(
            Key=key,
            UpdateExpression="SET displayName = :v",
            ConditionExpression="attribute_exists(PK)",
            ExpressionAttributeValues={":v": display_name},
        )
    else:
        table.update_item(
            Key=key,
            UpdateExpression="REMOVE displayName",
            ConditionExpression="attribute_exists(PK)",
        )

    write_operation_log(
        action="UPDATE_DISPLAY_NAME",
        user_id=user_id,
        community_id=community_id,
        target_type="Membership",
        target_id=user_id,
        after={"displayName": display_name or None},
    )
    return success_response(
        {
            "communityId": community_id,
            "userId": user_id,
            "displayName": display_name or None,
        }
    )
