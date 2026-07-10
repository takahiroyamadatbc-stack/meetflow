class AuthError(Exception):
    """Carries the エラーコード一覧v1.1 error code alongside the message, so
    a handler can pass it straight to `errors.error_response(exc.code,
    exc.message)`.
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def get_authenticated_user_id(event: dict) -> str:
    """Extract the Cognito-verified user id (sub) from an API Gateway proxy
    event.

    API Gateway's Cognito Authorizer has already validated the JWT before
    this Lambda runs (AWSシステム構成設計書v1.2 §5) -- this only reads the
    claim the authorizer attached to the request context, it does not
    perform verification itself.
    """
    try:
        return event["requestContext"]["authorizer"]["claims"]["sub"]
    except (KeyError, TypeError) as exc:
        raise AuthError("UNAUTHORIZED", "認証情報が見つかりません") from exc


def require_membership(table, community_id: str, user_id: str, *, roles=None):
    """機能要件書v1.1 §6 common control: confirm the authenticated user
    belongs to the community (and, if `roles` is given, holds one of those
    roles). Returns the Membership item on success.
    """
    resp = table.get_item(
        Key={"PK": f"COMMUNITY#{community_id}", "SK": f"MEMBER#{user_id}"}
    )
    item = resp.get("Item")
    if item is None:
        raise AuthError("FORBIDDEN", "コミュニティに所属していません")
    if item.get("status") == "SUSPENDED":
        raise AuthError("MEMBER_SUSPENDED", "一時停止中のため操作できません")
    if roles is not None and item.get("role") not in roles:
        raise AuthError("FORBIDDEN", "この操作を行う権限がありません")
    return item
