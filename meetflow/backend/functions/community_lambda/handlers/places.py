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


def _to_api_place(item):
    return {
        "placeId": item["PK"].split("#", 1)[1],
        "name": item.get("name"),
        "address": item.get("address", ""),
        "note": item.get("note", ""),
    }
