from datetime import datetime

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

# 設計書には明記されていない、MVP向け保守的な上限値。
_MAX_COMMENT_LENGTH = 200
_MAX_BATCH_SIZE = 100


def create_availability(user_id, event):
    """F-201（API設計書v1.4 §5.1）。

    AVAILABILITY_OVERLAP（エラーコード一覧v1.1 §4）は、そのドキュメント内で
    明示的に未決事項とされている（「エラーとして弾くか警告に留めるかは実装時に
    確定」）-- 設計書がまだ確定させていない方針を先取りして固定しないよう、
    ここでは意図的にチェックを実施していない。
    """
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    require_membership(table, community_id, user_id)

    body = parse_body(event)
    validation_error = _validate(body)
    if validation_error:
        return validation_error

    availability_id = generate_id()
    item = _build_item(community_id, user_id, availability_id, body, now_iso_ms())
    table.put_item(Item=item)
    write_operation_log(
        action="CREATE_AVAILABILITY",
        user_id=user_id,
        community_id=community_id,
        target_type="Availability",
        target_id=availability_id,
    )
    return success_response(
        _to_api_availability(item, availability_id), status_code=201
    )


def create_availability_batch(user_id, event):
    """カレンダーUI（画面設計書 S-09）向けのバッチ登録、Lambda設計書
    v1.1 §5.2。DynamoDBの実際のBatchWriteItem上限は1回の呼び出しあたり
    25件だが、`Table.batch_writer()`が自動でチャンク分割してくれるため、
    ここでは常識的でないほど大きな単一リクエストだけをガードすればよい
    （エラーコード一覧v1.1 BATCH_SIZE_EXCEEDED）。
    """
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    require_membership(table, community_id, user_id)

    body = parse_body(event)
    entries = body.get("availabilities")
    if not isinstance(entries, list) or not entries:
        return error_response("INVALID_PARAMETER", "availabilitiesが不正です")
    if len(entries) > _MAX_BATCH_SIZE:
        return error_response(
            "BATCH_SIZE_EXCEEDED", "一度に登録できる件数の上限を超えています"
        )
    for entry in entries:
        validation_error = _validate(entry)
        if validation_error:
            return validation_error

    created_at = now_iso_ms()
    created = []
    with table.batch_writer() as batch:
        for entry in entries:
            availability_id = generate_id()
            item = _build_item(community_id, user_id, availability_id, entry, created_at)
            batch.put_item(Item=item)
            created.append((item, availability_id))

    write_operation_log(
        action="CREATE_AVAILABILITY_BATCH",
        user_id=user_id,
        community_id=community_id,
        target_type="Availability",
        target_id=f"{len(created)} items",
    )
    return success_response(
        {
            "availabilities": [
                _to_api_availability(item, aid) for item, aid in created
            ]
        },
        status_code=201,
    )


def list_availability(user_id, event):
    """GET /communities/{communityId}/availability（F-204: 「自身の登録済み
    予定」）。このコミュニティ（パスパラメータ）と呼び出し元の両方に
    スコープされている -- コミュニティ全体・ユーザー横断の可視性は
    MatchingLambdaの内部アクセスパターン（DynamoDB物理設計書v1.3 §4の
    row 6）であり、メンバー向けAPIではない。
    """
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    require_membership(table, community_id, user_id)

    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"COMMUNITY#{community_id}")
        & Key("SK").begins_with("AVAIL#"),
    )
    availabilities = [
        _to_api_availability(item, item["SK"].split("#", 2)[2])
        for item in resp.get("Items", [])
        if item.get("userId") == user_id
    ]
    return success_response({"availabilities": availabilities})


def update_availability(user_id, event):
    """F-202。`startTime`はSK/GSI1SKの中にしか存在しない（DynamoDB物理設計書
    v1.3 §3.6にはトップレベルのstartTime属性は無い）ため、これを変更する
    ことはアイテムのキー自体が変わることを意味する。DynamoDBのアイテムキーは
    その場での変更ができないため、このケースはUpdateItemではなく、
    アトミックなdelete+recreate（TransactWriteItems）で対応する。
    """
    availability_id = event["pathParameters"]["availabilityId"]
    table = get_table()
    existing = _find_own_availability(table, user_id, availability_id)
    if existing is None:
        return error_response("AVAILABILITY_NOT_FOUND", "指定した空き予定が見つかりません")

    body = parse_body(event)
    current_start_time = existing["SK"].split("#", 2)[1]
    merged = {
        "startTime": body.get("startTime", current_start_time),
        "endTime": body.get("endTime", existing.get("endTime")),
        "gameTypes": body.get(
            "gameTypes",
            sorted(existing["gameTypes"]) if existing.get("gameTypes") else [],
        ),
        "comment": body.get("comment", existing.get("comment", "")),
    }
    validation_error = _validate(merged)
    if validation_error:
        return validation_error

    community_id = existing["PK"].split("#", 1)[1]
    new_item = _build_item(
        community_id,
        user_id,
        availability_id,
        merged,
        existing.get("createdAt", now_iso_ms()),
    )

    if merged["startTime"] == current_start_time:
        table.put_item(Item=new_item)
    else:
        transact_write(
            [
                {"Put": {"Item": new_item}},
                {"Delete": {"Key": {"PK": existing["PK"], "SK": existing["SK"]}}},
            ]
        )

    write_operation_log(
        action="UPDATE_AVAILABILITY",
        user_id=user_id,
        community_id=community_id,
        target_type="Availability",
        target_id=availability_id,
    )
    return success_response(_to_api_availability(new_item, availability_id))


def delete_availability(user_id, event):
    """F-203。"""
    availability_id = event["pathParameters"]["availabilityId"]
    table = get_table()
    existing = _find_own_availability(table, user_id, availability_id)
    if existing is None:
        return error_response("AVAILABILITY_NOT_FOUND", "指定した空き予定が見つかりません")

    table.delete_item(Key={"PK": existing["PK"], "SK": existing["SK"]})
    write_operation_log(
        action="DELETE_AVAILABILITY",
        user_id=user_id,
        community_id=existing["PK"].split("#", 1)[1],
        target_type="Availability",
        target_id=availability_id,
    )
    return success_response({"availabilityId": availability_id, "deleted": True})


def _find_own_availability(table, user_id, availability_id):
    """GSI1は`USER#{user_id}`（呼び出し元自身のパーティション）にスコープ
    されているため、これは所有者チェックも兼ねている -- 他のユーザーの
    空き予定は、availabilityIdが何であれ、このクエリには一切現れない。
    """
    resp = table.query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq(f"USER#{user_id}")
        & Key("GSI1SK").begins_with("AVAIL#"),
    )
    for item in resp.get("Items", []):
        if item["SK"].split("#", 2)[2] == availability_id:
            return item
    return None


def _validate(body):
    start_dt = _parse_iso(body.get("startTime"))
    end_dt = _parse_iso(body.get("endTime"))
    if start_dt is None or end_dt is None or start_dt >= end_dt:
        return error_response(
            "INVALID_TIME_RANGE", "開始時刻・終了時刻の指定が不正です"
        )
    comment = body.get("comment", "")
    if not isinstance(comment, str) or len(comment) > _MAX_COMMENT_LENGTH:
        return error_response("INVALID_PARAMETER", "コメントが長すぎます")
    game_types = body.get("gameTypes", [])
    if not isinstance(game_types, list) or not all(
        isinstance(g, str) for g in game_types
    ):
        return error_response("INVALID_PARAMETER", "gameTypesが不正です")
    return None


def _parse_iso(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _build_item(community_id, user_id, availability_id, body, created_at):
    start_time = body["startTime"]
    item = {
        "PK": f"COMMUNITY#{community_id}",
        "SK": f"AVAIL#{start_time}#{availability_id}",
        "GSI1PK": f"USER#{user_id}",
        "GSI1SK": f"AVAIL#{start_time}",
        "userId": user_id,
        "endTime": body["endTime"],
        "comment": body.get("comment", ""),
        "createdAt": created_at,
    }
    game_types = body.get("gameTypes")
    if game_types:
        item["gameTypes"] = set(game_types)
    return item


def _to_api_availability(item, availability_id):
    return {
        "availabilityId": availability_id,
        "startTime": item["SK"].split("#", 2)[1],
        "endTime": item.get("endTime"),
        "gameTypes": sorted(item["gameTypes"]) if item.get("gameTypes") else [],
        "comment": item.get("comment", ""),
    }
