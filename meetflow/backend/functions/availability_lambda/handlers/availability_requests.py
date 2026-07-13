from datetime import datetime

from boto3.dynamodb.conditions import Key

from meetflow_common import (
    AVAILABILITY_REQUEST_CREATED,
    error_response,
    generate_id,
    get_table,
    now_iso_ms,
    parse_body,
    put_event,
    require_membership,
    success_response,
    write_operation_log,
)

_VALID_SCOPES = ("ALL", "SPECIFIED")


def create_availability_request(user_id, event):
    """F-205 (要件定義書v1.3 §28, API設計書v1.5 §5.5). Publishes
    AvailabilityRequestCreated so NotificationLambda can fan out to the
    target members -- consuming that event is out of scope here (no
    EventBridge Rule targets it yet), same bootstrapping order as
    CandidateConflictDetected before EventLambda existed.
    """
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    body = parse_body(event)
    validation_error = _validate(body)
    if validation_error:
        return validation_error

    target_scope = body["targetScope"]
    target_user_ids = sorted(set(body.get("targetUserIds", []))) if target_scope == "SPECIFIED" else []

    request_id = generate_id()
    created_at = now_iso_ms()
    item = {
        "PK": f"COMMUNITY#{community_id}",
        "SK": f"AVAILREQ#{request_id}",
        "targetPeriodStart": body["targetPeriodStart"],
        "targetPeriodEnd": body["targetPeriodEnd"],
        "deadline": body["deadline"],
        "targetScope": target_scope,
        "message": body.get("message", ""),
        "createdBy": user_id,
        "createdAt": created_at,
    }
    if target_user_ids:
        item["targetUserIds"] = set(target_user_ids)
    table.put_item(Item=item)

    put_event(
        AVAILABILITY_REQUEST_CREATED,
        {
            "communityId": community_id,
            "requestId": request_id,
            "targetScope": target_scope,
            "targetUserIds": target_user_ids,
        },
    )
    write_operation_log(
        action="CREATE_AVAILABILITY_REQUEST",
        user_id=user_id,
        community_id=community_id,
        target_type="AvailabilityRequest",
        target_id=request_id,
    )
    return success_response(_to_api_request(item, request_id), status_code=201)


def list_availability_requests(user_id, event):
    """GET /communities/{communityId}/availability-requests (API設計書v1.5
    §5.6). Only OWNER/ADMIN and the request's own target members can see
    each request -- members who weren't asked shouldn't see requests
    directed at other members.
    """
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    membership = require_membership(table, community_id, user_id)

    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"COMMUNITY#{community_id}")
        & Key("SK").begins_with("AVAILREQ#")
    )
    is_admin = membership.get("role") in ("OWNER", "ADMIN")
    requests = []
    for item in resp.get("Items", []):
        target_scope = item.get("targetScope")
        is_target = target_scope == "ALL" or (
            target_scope == "SPECIFIED" and user_id in item.get("targetUserIds", set())
        )
        if not (is_admin or is_target):
            continue
        request_id = item["SK"].split("#", 1)[1]
        requests.append(_to_api_request(item, request_id))
    return success_response({"requests": requests})


def list_pending_members(user_id, event):
    """F-206 (要件定義書v1.3 §28, API設計書v1.5 §5.7). "未提出" is a
    lightweight existence check (0 vs >0 Availability records in the target
    period via the existing GSI1), not a full attendance/response tracker
    (DynamoDB物理設計書v1.4 §3.18).
    """
    community_id = event["pathParameters"]["communityId"]
    request_id = event["pathParameters"]["requestId"]
    table = get_table()
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    availability_request = table.get_item(
        Key={"PK": f"COMMUNITY#{community_id}", "SK": f"AVAILREQ#{request_id}"}
    ).get("Item")
    if availability_request is None:
        return error_response(
            "AVAILABILITY_REQUEST_NOT_FOUND", "指定した空き予定提出リクエストが見つかりません"
        )

    target_user_ids = _resolve_target_user_ids(table, community_id, availability_request)

    period_start = availability_request["targetPeriodStart"]
    period_end = availability_request["targetPeriodEnd"]
    pending_members = []
    for target_user_id in target_user_ids:
        resp = table.query(
            IndexName="GSI1",
            KeyConditionExpression=Key("GSI1PK").eq(f"USER#{target_user_id}")
            & Key("GSI1SK").between(f"AVAIL#{period_start}", f"AVAIL#{period_end}"),
        )
        if resp.get("Items"):
            continue
        profile = (
            table.get_item(Key={"PK": f"USER#{target_user_id}", "SK": "PROFILE"}).get(
                "Item"
            )
            or {}
        )
        pending_members.append(
            {"userId": target_user_id, "nickname": profile.get("nickname", "")}
        )
    return success_response({"pendingMembers": pending_members})


def _resolve_target_user_ids(table, community_id, availability_request):
    if availability_request.get("targetScope") == "SPECIFIED":
        return sorted(availability_request.get("targetUserIds", set()))

    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"COMMUNITY#{community_id}")
        & Key("SK").begins_with("MEMBER#")
    )
    return [item["SK"].split("#", 1)[1] for item in resp.get("Items", [])]


def _validate(body):
    start_dt = _parse_iso(body.get("targetPeriodStart"))
    end_dt = _parse_iso(body.get("targetPeriodEnd"))
    if start_dt is None or end_dt is None or start_dt >= end_dt:
        return error_response("INVALID_PARAMETER", "対象期間の指定が不正です")
    if _parse_iso(body.get("deadline")) is None:
        return error_response("INVALID_PARAMETER", "提出期限の指定が不正です")

    target_scope = body.get("targetScope")
    if target_scope not in _VALID_SCOPES:
        return error_response("INVALID_PARAMETER", "targetScopeはALL/SPECIFIEDのみ指定できます")
    if target_scope == "SPECIFIED":
        target_user_ids = body.get("targetUserIds")
        if (
            not isinstance(target_user_ids, list)
            or not target_user_ids
            or not all(isinstance(uid, str) for uid in target_user_ids)
        ):
            return error_response(
                "INVALID_PARAMETER", "targetScope=SPECIFIEDの場合targetUserIdsが必須です"
            )

    message = body.get("message", "")
    if not isinstance(message, str):
        return error_response("INVALID_PARAMETER", "messageが不正です")
    return None


def _parse_iso(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _to_api_request(item, request_id):
    return {
        "requestId": request_id,
        "targetPeriodStart": item.get("targetPeriodStart"),
        "targetPeriodEnd": item.get("targetPeriodEnd"),
        "deadline": item.get("deadline"),
        "targetScope": item.get("targetScope"),
        "targetUserIds": sorted(item["targetUserIds"]) if item.get("targetUserIds") else [],
        "message": item.get("message", ""),
        "createdBy": item.get("createdBy"),
        "createdAt": item.get("createdAt"),
    }
