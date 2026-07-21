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

_MAX_NAME_LENGTH = 50  # 設計書には明記されていない、MVP向け保守的な上限値


def list_places(user_id, event):
    """GET /communities/{communityId}/locations（API設計書v1.4 §8.5）。
    どのメンバーでも閲覧可能 -- OWNER/ADMIN限定なのは登録（F-107）のみ。
    """
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    require_membership(table, community_id, user_id)

    resp = table.query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq(f"COMMUNITY#{community_id}")
        & Key("GSI1SK").begins_with("PLACE#"),
    )
    return success_response({"places": [_to_api_place(item) for item in resp.get("Items", [])]})


def create_place(user_id, event):
    """F-107（API設計書v1.4 §8.6）。MVPでは常に`ownerType=COMMUNITY`として
    登録する（DynamoDB物理設計書v1.3 §3.9）-- STORE/OFFICIALの会場は、
    Placeを複数コミュニティ間で共有できるようになった際の将来的な課題。"""
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    body = parse_body(event)
    name = body.get("name")
    if not isinstance(name, str) or not (1 <= len(name) <= _MAX_NAME_LENGTH):
        return error_response("INVALID_PARAMETER", "会場名が不正です")

    place_id = generate_id()
    item = {
        "PK": f"PLACE#{place_id}",
        "SK": "METADATA",
        "GSI1PK": f"COMMUNITY#{community_id}",
        "GSI1SK": f"PLACE#{place_id}",
        "name": name,
        # `address`は任意項目（要件定義書v1.2 §18: 住所を必須としない）
        "address": body.get("address", ""),
        "ownerType": "COMMUNITY",
        "ownerId": community_id,
        "note": body.get("note", ""),
        "createdAt": now_iso_ms(),
    }
    table.put_item(Item=item)
    write_operation_log(
        action="CREATE_PLACE",
        user_id=user_id,
        community_id=community_id,
        target_type="Place",
        target_id=place_id,
    )
    return success_response(_to_api_place(item), status_code=201)


def update_place(user_id, event):
    """PUT /communities/{communityId}/locations/{placeId}（Issue #86）。
    権限は登録（create_place）と同じくOWNER/ADMIN限定。"""
    community_id = event["pathParameters"]["communityId"]
    place_id = event["pathParameters"]["placeId"]
    table = get_table()
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    place = _get_place_in_community(table, community_id, place_id)
    if place is None:
        return error_response("LOCATION_NOT_FOUND", "会場が見つかりません")

    body = parse_body(event)
    names = {}
    values = {}
    set_clauses = []

    if "name" in body:
        name = body["name"]
        if not isinstance(name, str) or not (1 <= len(name) <= _MAX_NAME_LENGTH):
            return error_response("INVALID_PARAMETER", "会場名が不正です")
        names["#name"] = "name"
        values[":name"] = name
        set_clauses.append("#name = :name")
    if "address" in body:
        names["#address"] = "address"
        values[":address"] = body["address"]
        set_clauses.append("#address = :address")
    if "note" in body:
        names["#note"] = "note"
        values[":note"] = body["note"]
        set_clauses.append("#note = :note")

    if not set_clauses:
        return error_response("INVALID_PARAMETER", "更新する項目がありません")

    resp = table.update_item(
        Key={"PK": f"PLACE#{place_id}", "SK": "METADATA"},
        UpdateExpression="SET " + ", ".join(set_clauses),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
        ReturnValues="ALL_NEW",
    )
    write_operation_log(
        action="UPDATE_PLACE",
        user_id=user_id,
        community_id=community_id,
        target_type="Place",
        target_id=place_id,
    )
    return success_response(_to_api_place(resp["Attributes"]))


def delete_place(user_id, event):
    """DELETE /communities/{communityId}/locations/{placeId}（Issue #86）。
    権限はOWNER/ADMIN限定。中止・完了以外のステータスのイベントで使用中の
    会場は削除できない（過去の利用履歴は削除の妨げにしない）。"""
    community_id = event["pathParameters"]["communityId"]
    place_id = event["pathParameters"]["placeId"]
    table = get_table()
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    place = _get_place_in_community(table, community_id, place_id)
    if place is None:
        return error_response("LOCATION_NOT_FOUND", "会場が見つかりません")

    if _is_place_in_use(table, community_id, place_id):
        return error_response(
            "LOCATION_IN_USE", "開催予定のイベントで使用中の会場は削除できません"
        )

    table.delete_item(Key={"PK": f"PLACE#{place_id}", "SK": "METADATA"})
    write_operation_log(
        action="DELETE_PLACE",
        user_id=user_id,
        community_id=community_id,
        target_type="Place",
        target_id=place_id,
    )
    return success_response({"placeId": place_id})


def _get_place_in_community(table, community_id, place_id):
    place = table.get_item(Key={"PK": f"PLACE#{place_id}", "SK": "METADATA"}).get("Item")
    if place is None or place.get("ownerId") != community_id:
        return None
    return place


_INACTIVE_EVENT_STATUSES = ("CANCELLED", "COMPLETED")


def _is_place_in_use(table, community_id, place_id):
    resp = table.query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq(f"COMMUNITY#{community_id}")
        & Key("GSI1SK").begins_with("EVENT#"),
    )
    return any(
        item.get("locationId") == place_id
        and item.get("status") not in _INACTIVE_EVENT_STATUSES
        for item in resp.get("Items", [])
    )


def _to_api_place(item):
    return {
        "placeId": item["PK"].split("#", 1)[1],
        "name": item.get("name"),
        "address": item.get("address", ""),
        "note": item.get("note", ""),
    }
