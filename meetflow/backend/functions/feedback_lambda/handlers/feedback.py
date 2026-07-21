from datetime import datetime, timedelta

from boto3.dynamodb.conditions import Attr, Key

from meetflow_common import (
    FEEDBACK_REPLIED,
    error_response,
    generate_id,
    get_table,
    now_iso_ms,
    parse_body,
    put_event,
    success_response,
)

from .attachments import generate_view_url
from .operators import require_operator

_KINDS = ("QUICK", "DETAILED")
_RATINGS = ("BAD", "NEUTRAL", "GOOD")
_CATEGORIES = ("BUG", "FEATURE_REQUEST", "UX_IMPROVEMENT")
_STATUSES = ("UNHANDLED", "PLANNED", "DONE")
_PRIORITIES = ("LOW", "MEDIUM", "HIGH")
_QUICK_STATS_PERIODS = ("WEEK", "MONTH")


def create_feedback(user_id, event):
    """F-1401/F-1402 (API設計書v1.17 §12b.1)。`kind`でQUICK(1クリック評価)/
    DETAILED(詳細投稿)を分岐する。投稿者はJWTのuserIdから自動的に紐付け、
    連絡先の別入力は求めない(コミュニティメンバーである以上、常に本人の
    アカウントを通じて追跡可能なため)。
    """
    body = parse_body(event)
    kind = body.get("kind")
    if kind not in _KINDS:
        return error_response("FEEDBACK_VALIDATION_ERROR", "kindが不正です")

    related_feature = body.get("relatedFeature")
    if not isinstance(related_feature, str) or not related_feature:
        return error_response(
            "FEEDBACK_VALIDATION_ERROR", "relatedFeatureは必須です"
        )

    rating = None
    category = None
    content = None
    attachment_keys = None

    if kind == "QUICK":
        rating = body.get("rating")
        if rating not in _RATINGS:
            return error_response("FEEDBACK_VALIDATION_ERROR", "ratingが不正です")
    else:
        category = body.get("category")
        if category not in _CATEGORIES:
            return error_response(
                "FEEDBACK_VALIDATION_ERROR", "categoryが不正です"
            )
        content = body.get("content")
        if content is not None and not isinstance(content, str):
            return error_response("FEEDBACK_VALIDATION_ERROR", "contentが不正です")
        attachment_keys = body.get("attachmentKeys")
        if attachment_keys is not None and (
            not isinstance(attachment_keys, list)
            or not all(isinstance(k, str) and k for k in attachment_keys)
        ):
            return error_response(
                "FEEDBACK_VALIDATION_ERROR", "attachmentKeysが不正です"
            )

    feedback_id = generate_id()
    now = now_iso_ms()
    item = {
        "PK": f"FEEDBACK#{feedback_id}",
        "SK": "METADATA",
        "GSI1PK": f"USER#{user_id}",
        "GSI1SK": f"FEEDBACK#{now}#{feedback_id}",
        "GSI2PK": "FEEDBACK",
        "GSI2SK": f"{now}#{feedback_id}",
        "userId": user_id,
        "kind": kind,
        "relatedFeature": related_feature,
        "status": "UNHANDLED",
        "createdAt": now,
        "updatedAt": now,
    }
    if rating is not None:
        item["rating"] = rating
    if category is not None:
        item["category"] = category
    if content:
        item["content"] = content
    if attachment_keys:
        item["attachmentKeys"] = set(attachment_keys)

    get_table().put_item(Item=item)

    return success_response(
        {"feedbackId": feedback_id, "createdAt": now}, status_code=201
    )


def list_feedback(user_id, event):
    """F-1403 (API設計書v1.17 §12b.3)。運営者限定。GSI2PK固定値`FEEDBACK`で
    種別横断の一覧を取得し(DynamoDB物理設計書v1.12 §3.19)、`status`/
    `category`/`kind`はFilterExpressionで絞り込む。
    """
    require_operator(event)

    params = event.get("queryStringParameters") or {}
    filter_expr = None
    for field in ("status", "category", "kind"):
        value = params.get(field)
        if value:
            condition = Attr(field).eq(value)
            filter_expr = condition if filter_expr is None else filter_expr & condition

    query_kwargs = {
        "IndexName": "GSI2",
        "KeyConditionExpression": Key("GSI2PK").eq("FEEDBACK"),
        "ScanIndexForward": False,
    }
    if filter_expr is not None:
        query_kwargs["FilterExpression"] = filter_expr

    resp = get_table().query(**query_kwargs)
    items = [_to_api_feedback(item) for item in resp.get("Items", [])]
    return success_response({"feedbacks": items})


def get_feedback(user_id, event):
    """F-1403 (API設計書v1.17 §12b.4)。運営者限定。"""
    require_operator(event)

    feedback_id = event["pathParameters"]["feedbackId"]
    resp = get_table().get_item(
        Key={"PK": f"FEEDBACK#{feedback_id}", "SK": "METADATA"}
    )
    item = resp.get("Item")
    if item is None:
        return error_response("FEEDBACK_NOT_FOUND", "指定したフィードバックが見つかりません")

    result = _to_api_feedback(item, include_reply=True)
    result["attachmentUrls"] = [
        generate_view_url(key) for key in sorted(item.get("attachmentKeys", []))
    ]
    return success_response(result)


def update_feedback(user_id, event):
    """F-1403/F-1404 (API設計書v1.17 §12b.5)。運営者限定。`status`/
    `priority`/`reply`はいずれも任意の部分更新。`reply`指定時は投稿者への
    通知のため`FeedbackReplied`をEventBridgeへ発行する。
    """
    require_operator(event)

    feedback_id = event["pathParameters"]["feedbackId"]
    table = get_table()
    key = {"PK": f"FEEDBACK#{feedback_id}", "SK": "METADATA"}
    resp = table.get_item(Key=key)
    item = resp.get("Item")
    if item is None:
        return error_response("FEEDBACK_NOT_FOUND", "指定したフィードバックが見つかりません")

    body = parse_body(event)
    status = body.get("status")
    if status is not None and status not in _STATUSES:
        return error_response("FEEDBACK_VALIDATION_ERROR", "statusが不正です")
    priority = body.get("priority")
    if priority is not None and priority not in _PRIORITIES:
        return error_response("FEEDBACK_VALIDATION_ERROR", "priorityが不正です")
    reply = body.get("reply")
    if reply is not None and (not isinstance(reply, str) or not reply):
        return error_response("FEEDBACK_VALIDATION_ERROR", "replyが不正です")

    now = now_iso_ms()
    update_names = {}
    update_values = {":updatedAt": now}
    set_clauses = ["updatedAt = :updatedAt"]

    if status is not None:
        set_clauses.append("#status = :status")
        update_names["#status"] = "status"
        update_values[":status"] = status
    if priority is not None:
        set_clauses.append("priority = :priority")
        update_values[":priority"] = priority
    if reply is not None:
        set_clauses.append("reply = :reply")
        update_values[":reply"] = {
            "message": reply,
            "repliedBy": user_id,
            "repliedAt": now,
        }

    update_kwargs = {
        "Key": key,
        "UpdateExpression": "SET " + ", ".join(set_clauses),
        "ExpressionAttributeValues": update_values,
    }
    if update_names:
        update_kwargs["ExpressionAttributeNames"] = update_names
    table.update_item(**update_kwargs)

    if reply is not None:
        put_event(
            FEEDBACK_REPLIED,
            {
                "feedbackId": feedback_id,
                "targetUserId": item["userId"],
                "message": reply,
            },
        )

    return success_response({"feedbackId": feedback_id, "updatedAt": now})


def get_feedback_stats(user_id, event):
    """F-1405 (API設計書v1.17 §12b.6)。運営者限定。

    Issue #85: QUICK評価(絵文字1クリック評価)は一覧表示から外す代わりに、
    relatedFeature(該当機能)×rating(評価)で期間(週/月)ごとに集計し、
    時系列グラフ表示に使う`quickStats`を追加する。既存のGSI2への1回の
    Queryで全件取得できているため、新しいアクセスパターン・GSIは不要で
    Lambda側の集計ロジックを増やすのみ。
    """
    require_operator(event)

    params = event.get("queryStringParameters") or {}
    period = params.get("period") or "WEEK"
    if period not in _QUICK_STATS_PERIODS:
        return error_response(
            "FEEDBACK_VALIDATION_ERROR", "periodはWEEK/MONTHのいずれかで指定してください"
        )

    resp = get_table().query(
        IndexName="GSI2",
        KeyConditionExpression=Key("GSI2PK").eq("FEEDBACK"),
    )
    items = resp.get("Items", [])

    by_category, by_status, by_priority = {}, {}, {}
    quick_buckets = {}
    for item in items:
        category = item.get("category")
        if category:
            by_category[category] = by_category.get(category, 0) + 1
        status = item.get("status")
        if status:
            by_status[status] = by_status.get(status, 0) + 1
        priority = item.get("priority")
        if priority:
            by_priority[priority] = by_priority.get(priority, 0) + 1

        if item.get("kind") == "QUICK":
            rating = item.get("rating")
            related_feature = item.get("relatedFeature")
            created_at = item.get("createdAt")
            if not (rating and related_feature and created_at):
                continue
            bucket_start = _quick_stats_bucket_start(created_at, period)
            feature_ratings = quick_buckets.setdefault(bucket_start, {})
            rating_counts = feature_ratings.setdefault(related_feature, {})
            rating_counts[rating] = rating_counts.get(rating, 0) + 1

    quick_stats_buckets = [
        {"bucketStart": bucket_start, "byFeatureRating": feature_ratings}
        for bucket_start, feature_ratings in sorted(quick_buckets.items())
    ]

    return success_response(
        {
            "byCategory": by_category,
            "byStatus": by_status,
            "byPriority": by_priority,
            "quickStats": {"period": period, "buckets": quick_stats_buckets},
        }
    )


def _quick_stats_bucket_start(created_at, period):
    """ISO8601文字列から、その週(月曜始まり)/月の開始日を`YYYY-MM-DD`
    形式で返す(グラフのX軸ラベルとソートキーを兼ねる)。
    """
    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    if period == "MONTH":
        return dt.strftime("%Y-%m-01")
    monday = dt - timedelta(days=dt.weekday())
    return monday.strftime("%Y-%m-%d")


def _to_api_feedback(item, *, include_reply=False):
    result = {
        "feedbackId": item["PK"].split("#", 1)[1],
        "userId": item.get("userId"),
        "kind": item.get("kind"),
        "relatedFeature": item.get("relatedFeature"),
        "rating": item.get("rating"),
        "category": item.get("category"),
        "content": item.get("content"),
        "attachmentKeys": sorted(item.get("attachmentKeys", [])),
        "status": item.get("status"),
        "priority": item.get("priority"),
        "createdAt": item.get("createdAt"),
        "updatedAt": item.get("updatedAt"),
    }
    if include_reply:
        result["reply"] = item.get("reply")
    return result
