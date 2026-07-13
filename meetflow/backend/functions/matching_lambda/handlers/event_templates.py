from boto3.dynamodb.conditions import Key

from meetflow_common import (
    error_response,
    generate_id,
    get_table,
    now_iso_ms,
    parse_body,
    require_membership,
    success_response,
    write_operation_log,
)


def create_template(user_id, event):
    """F-301 (API設計書v1.4 §7.1)."""
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    body = parse_body(event)
    validation_error = _validate(body)
    if validation_error:
        return validation_error

    template_id = generate_id()
    item = {
        "PK": f"COMMUNITY#{community_id}",
        "SK": f"TEMPLATE#{template_id}",
        "gameType": body["gameType"],
        "minPlayers": body["minPlayers"],
        "maxPlayers": body["maxPlayers"],
        "priority": body.get("priority", 0),
        "conditions": body.get("conditions", {}),
        "createdAt": now_iso_ms(),
    }
    table.put_item(Item=item)
    write_operation_log(
        action="CREATE_EVENT_TEMPLATE",
        user_id=user_id,
        community_id=community_id,
        target_type="EventTemplate",
        target_id=template_id,
    )
    return success_response(_to_api_template(item, template_id), status_code=201)


def list_templates(user_id, event):
    """F-302 (API設計書v1.4 §7.2)."""
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    require_membership(table, community_id, user_id)

    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"COMMUNITY#{community_id}")
        & Key("SK").begins_with("TEMPLATE#")
    )
    templates = [
        _to_api_template(item, item["SK"].split("#", 1)[1])
        for item in resp.get("Items", [])
    ]
    return success_response({"templates": templates})


def update_template(user_id, event):
    """F-303.

    Lambda設計書v1.1 §6.2 documents this as `PUT /event-templates/{id}`
    (no communityId segment), but EventTemplate has no GSI to resolve
    templateId -> communityId (DynamoDB物理設計書v1.3 §3.7 only defines the
    PK=COMMUNITY#{id} primary access pattern). The route is corrected to
    include communityId here, matching every other community-scoped
    sub-resource in this API and staying consistent with the documented key
    design (CLAUDE.md: never deviate from it) -- see handler.py's routing
    table.
    """
    community_id = event["pathParameters"]["communityId"]
    template_id = event["pathParameters"]["templateId"]
    table = get_table()
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    existing = table.get_item(
        Key={"PK": f"COMMUNITY#{community_id}", "SK": f"TEMPLATE#{template_id}"}
    ).get("Item")
    if existing is None:
        return error_response(
            "EVENT_TEMPLATE_NOT_FOUND", "指定した開催条件が見つかりません"
        )

    body = parse_body(event)
    if not body:
        return error_response("INVALID_PARAMETER", "更新項目がありません")

    merged = {
        "gameType": body.get("gameType", existing.get("gameType")),
        "minPlayers": body.get("minPlayers", existing.get("minPlayers")),
        "maxPlayers": body.get("maxPlayers", existing.get("maxPlayers")),
        "priority": body.get("priority", existing.get("priority", 0)),
        "conditions": body.get("conditions", existing.get("conditions", {})),
    }
    validation_error = _validate(merged)
    if validation_error:
        return validation_error

    table.update_item(
        Key={"PK": f"COMMUNITY#{community_id}", "SK": f"TEMPLATE#{template_id}"},
        UpdateExpression=(
            "SET gameType = :g, minPlayers = :mn, maxPlayers = :mx, "
            "priority = :p, conditions = :c"
        ),
        ExpressionAttributeValues={
            ":g": merged["gameType"],
            ":mn": merged["minPlayers"],
            ":mx": merged["maxPlayers"],
            ":p": merged["priority"],
            ":c": merged["conditions"],
        },
    )
    write_operation_log(
        action="UPDATE_EVENT_TEMPLATE",
        user_id=user_id,
        community_id=community_id,
        target_type="EventTemplate",
        target_id=template_id,
    )
    return success_response(_to_api_template(merged, template_id))


def delete_template(user_id, event):
    """F-304. Same routing correction as `update_template` (communityId
    added to the path)."""
    community_id = event["pathParameters"]["communityId"]
    template_id = event["pathParameters"]["templateId"]
    table = get_table()
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    try:
        table.delete_item(
            Key={"PK": f"COMMUNITY#{community_id}", "SK": f"TEMPLATE#{template_id}"},
            ConditionExpression="attribute_exists(PK)",
        )
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return error_response(
            "EVENT_TEMPLATE_NOT_FOUND", "指定した開催条件が見つかりません"
        )

    write_operation_log(
        action="DELETE_EVENT_TEMPLATE",
        user_id=user_id,
        community_id=community_id,
        target_type="EventTemplate",
        target_id=template_id,
    )
    return success_response({"templateId": template_id, "deleted": True})


def _validate(body):
    game_type = body.get("gameType")
    if not isinstance(game_type, str) or not game_type:
        return error_response("INVALID_PARAMETER", "gameTypeが不正です")

    min_players = body.get("minPlayers")
    max_players = body.get("maxPlayers")
    if (
        not isinstance(min_players, int)
        or not isinstance(max_players, int)
        or isinstance(min_players, bool)
        or isinstance(max_players, bool)
        or min_players < 1
        or min_players > max_players
    ):
        return error_response("INVALID_PLAYER_RANGE", "人数の範囲指定が不正です")

    priority = body.get("priority", 0)
    if not isinstance(priority, int) or isinstance(priority, bool) or not (
        0 <= priority <= 100
    ):
        return error_response("INVALID_PARAMETER", "priorityは0〜100で指定してください")

    conditions = body.get("conditions", {})
    if not isinstance(conditions, dict):
        return error_response("INVALID_PARAMETER", "conditionsはオブジェクトで指定してください")

    return None


def _to_api_template(item, template_id):
    return {
        "templateId": template_id,
        "gameType": item.get("gameType"),
        "minPlayers": item.get("minPlayers"),
        "maxPlayers": item.get("maxPlayers"),
        "priority": item.get("priority", 0),
        "conditions": item.get("conditions", {}),
    }
