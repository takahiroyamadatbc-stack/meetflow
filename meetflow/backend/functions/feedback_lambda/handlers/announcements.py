from boto3.dynamodb.conditions import Attr, Key

from meetflow_common import (
    error_response,
    generate_id,
    get_table,
    now_iso_ms,
    parse_body,
    success_response,
)

from .operators import require_operator

_STATUSES = ("DRAFT", "PUBLISHED", "ARCHIVED")


def list_announcements(user_id, event):
    """F-1406 (API設計書v1.17 §12c.1)。一般ユーザーは公開中(PUBLISHED)の
    もののみ、`includeAll=true`指定時(運営者限定)はDRAFT/ARCHIVEDも含めて
    返す。
    """
    include_all = (event.get("queryStringParameters") or {}).get(
        "includeAll"
    ) == "true"
    if include_all:
        require_operator(event)

    query_kwargs = {
        "IndexName": "GSI2",
        "KeyConditionExpression": Key("GSI2PK").eq("ANNOUNCEMENT"),
        "ScanIndexForward": False,
    }
    if not include_all:
        query_kwargs["FilterExpression"] = Attr("status").eq("PUBLISHED")

    resp = get_table().query(**query_kwargs)
    items = [_to_api_announcement(item) for item in resp.get("Items", [])]
    return success_response({"announcements": items})


def create_announcement(user_id, event):
    """F-1406 (API設計書v1.17 §12c.2)。運営者限定。`status=DRAFT`で作成する。"""
    require_operator(event)

    body = parse_body(event)
    title = body.get("title")
    content = body.get("body")
    if not isinstance(title, str) or not title:
        return error_response("INVALID_PARAMETER", "titleは必須です")
    if not isinstance(content, str) or not content:
        return error_response("INVALID_PARAMETER", "bodyは必須です")

    announcement_id = generate_id()
    now = now_iso_ms()
    get_table().put_item(
        Item={
            "PK": f"ANNOUNCEMENT#{announcement_id}",
            "SK": "METADATA",
            "GSI2PK": "ANNOUNCEMENT",
            "GSI2SK": f"{now}#{announcement_id}",
            "title": title,
            "body": content,
            "status": "DRAFT",
            "createdBy": user_id,
            "createdAt": now,
            "updatedAt": now,
        }
    )

    return success_response(
        {"announcementId": announcement_id, "createdAt": now}, status_code=201
    )


def update_announcement(user_id, event):
    """F-1406 (API設計書v1.17 §12c.3)。運営者限定。取り下げは`DELETE`ではなく
    `status=ARCHIVED`への更新で行う(監査証跡を残すため)。
    """
    require_operator(event)

    announcement_id = event["pathParameters"]["announcementId"]
    table = get_table()
    key = {"PK": f"ANNOUNCEMENT#{announcement_id}", "SK": "METADATA"}
    resp = table.get_item(Key=key)
    if resp.get("Item") is None:
        return error_response("ANNOUNCEMENT_NOT_FOUND", "指定したお知らせが見つかりません")

    body = parse_body(event)
    title = body.get("title")
    content = body.get("body")
    status = body.get("status")
    if title is not None and (not isinstance(title, str) or not title):
        return error_response("INVALID_PARAMETER", "titleが不正です")
    if content is not None and (not isinstance(content, str) or not content):
        return error_response("INVALID_PARAMETER", "bodyが不正です")
    if status is not None and status not in _STATUSES:
        return error_response("INVALID_PARAMETER", "statusが不正です")

    now = now_iso_ms()
    set_clauses = ["updatedAt = :updatedAt"]
    values = {":updatedAt": now}
    if title is not None:
        set_clauses.append("title = :title")
        values[":title"] = title
    if content is not None:
        set_clauses.append("body = :body")
        values[":body"] = content
    if status is not None:
        set_clauses.append("#status = :status")
        values[":status"] = status

    update_kwargs = {
        "Key": key,
        "UpdateExpression": "SET " + ", ".join(set_clauses),
        "ExpressionAttributeValues": values,
    }
    if status is not None:
        update_kwargs["ExpressionAttributeNames"] = {"#status": "status"}
    table.update_item(**update_kwargs)

    return success_response({"announcementId": announcement_id, "updatedAt": now})


def _to_api_announcement(item):
    return {
        "announcementId": item["PK"].split("#", 1)[1],
        "title": item.get("title"),
        "body": item.get("body"),
        "status": item.get("status"),
        "createdBy": item.get("createdBy"),
        "createdAt": item.get("createdAt"),
        "updatedAt": item.get("updatedAt"),
    }
