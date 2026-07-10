import json

# エラーコード一覧v1.1 §1 (common errors) + a couple of domain codes that the
# shared `require_membership` auth helper itself can raise (§3 MEMBER_SUSPENDED)
# or that most domain Lambdas need (§2 PROFILE_VALIDATION_ERROR). Domain-specific
# codes beyond these are looked up by each Lambda's own code and passed through
# `error_response` with an explicit `status_code`.
_STATUS_BY_CODE = {
    "USER_NOT_FOUND": 404,
    "COMMUNITY_NOT_FOUND": 404,
    "FORBIDDEN": 403,
    "UNAUTHORIZED": 401,
    "INVALID_PARAMETER": 400,
    "INTERNAL_ERROR": 500,
    "MEMBER_SUSPENDED": 403,
    "PROFILE_VALIDATION_ERROR": 400,
}


def error_response(code: str, message: str, *, status_code: int = None) -> dict:
    """Build an API Gateway (Lambda proxy integration) error response.

    Envelope matches API設計書v1.4 §2. `status_code` only needs to be passed
    explicitly for codes not in `_STATUS_BY_CODE` above (e.g. 409 conflicts
    defined per-domain in エラーコード一覧v1.1).
    """
    return {
        "statusCode": status_code or _STATUS_BY_CODE.get(code, 400),
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(
            {"success": False, "error": {"code": code, "message": message}},
            ensure_ascii=False,
        ),
    }


def success_response(data, *, status_code: int = 200) -> dict:
    """Build an API Gateway (Lambda proxy integration) success response."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"success": True, "data": data}, ensure_ascii=False),
    }
