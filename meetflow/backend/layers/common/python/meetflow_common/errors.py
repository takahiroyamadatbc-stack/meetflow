import json
from decimal import Decimal

# Every code from エラーコード一覧v1.1 (§1-8), centralized here rather than
# left for each call site to remember a `status_code=` -- an earlier version
# of this dict only had the common (§1) codes plus a couple of extras, and
# several call sites across domain Lambdas forgot to pass `status_code`
# explicitly for their own domain's codes (e.g. EVENT_NOT_FOUND silently
# falling back to this function's 400 default instead of the documented
# 404). Keeping the full table here means a call site only needs
# `status_code=` for the rare case for where NO_CANDIDATES_FOUND-style logic
# means the "error" is actually a normal response.
_STATUS_BY_CODE = {
    # §1 共通エラー
    "USER_NOT_FOUND": 404,
    "COMMUNITY_NOT_FOUND": 404,
    "FORBIDDEN": 403,
    "UNAUTHORIZED": 401,
    "INVALID_PARAMETER": 400,
    "INTERNAL_ERROR": 500,
    # §2 User
    "PROFILE_VALIDATION_ERROR": 400,
    # §3 Community
    "INVITE_NOT_FOUND": 404,
    "INVITE_REVOKED": 410,
    "INVITE_EXPIRED": 410,
    "ALREADY_MEMBER": 409,
    "JOIN_REQUEST_ALREADY_PENDING": 409,
    "JOIN_REQUEST_NOT_FOUND": 404,
    "JOIN_REQUEST_ALREADY_PROCESSED": 409,
    "LAST_OWNER_CANNOT_LEAVE": 409,
    "MEMBER_SUSPENDED": 403,
    "LOCATION_NOT_FOUND": 404,
    # §4 Availability
    "INVALID_TIME_RANGE": 400,
    "AVAILABILITY_NOT_FOUND": 404,
    "AVAILABILITY_OVERLAP": 409,
    "BATCH_SIZE_EXCEEDED": 400,
    "AVAILABILITY_REQUEST_NOT_FOUND": 404,
    # §5 Matching (EventTemplate / MatchCandidate)
    "INVALID_PLAYER_RANGE": 400,
    "EVENT_TEMPLATE_NOT_FOUND": 404,
    "NO_CANDIDATES_FOUND": 200,
    "CANDIDATE_NOT_FOUND": 404,
    "CANDIDATE_ALREADY_USED": 409,
    # §6 Event (イベント・参加者・キャンセル)
    "EVENT_NOT_FOUND": 404,
    "INVALID_STATUS_TRANSITION": 409,
    "EVENT_ALREADY_CONFIRMED": 409,
    "EVENT_ALREADY_CANCELLED": 409,
    "PARTICIPANT_NOT_FOUND": 404,
    "CANCEL_REQUEST_ALREADY_PENDING": 409,
    "CANCEL_REQUEST_NOT_FOUND": 404,
    "CANCEL_REQUEST_ALREADY_PROCESSED": 409,
    "NOT_A_PARTICIPANT": 403,
    "PARTICIPANT_SCHEDULE_CONFLICT": 409,
    # §7 Result
    "EVENT_NOT_COMPLETED": 409,
    "RESULT_VALIDATION_ERROR": 400,
    "RESULT_ACCESS_DENIED": 403,
    # §8 Notification
    "NOTIFICATION_NOT_FOUND": 404,
}


def _json_default(value):
    # boto3's Table resource deserializes every DynamoDB Number attribute to
    # decimal.Decimal (never int/float), so any handler that echoes a value
    # read straight from DynamoDB back into a response (as opposed to a
    # freshly-parsed request body, which is already plain int/float) hits
    # `TypeError: Object of type Decimal is not JSON serializable` unless
    # it's converted first. Centralized here so every domain gets this for
    # free instead of each call site remembering to cast.
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def error_response(code: str, message: str, *, status_code: int = None) -> dict:
    """Build an API Gateway (Lambda proxy integration) error response.

    Envelope matches API設計書v1.4 §2. `status_code` only needs to be passed
    explicitly to override the table above (e.g. NO_CANDIDATES_FOUND is
    handled as a normal empty-list response rather than through this
    function at all -- see MatchingLambda).
    """
    return {
        "statusCode": status_code or _STATUS_BY_CODE.get(code, 400),
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(
            {"success": False, "error": {"code": code, "message": message}},
            ensure_ascii=False,
            default=_json_default,
        ),
    }


def success_response(data, *, status_code: int = 200) -> dict:
    """Build an API Gateway (Lambda proxy integration) success response."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(
            {"success": True, "data": data}, ensure_ascii=False, default=_json_default
        ),
    }
