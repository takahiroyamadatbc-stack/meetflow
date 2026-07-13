from .auth import AuthError, get_authenticated_user_id
from .errors import error_response
from .http import BadRequest


def dispatch(routes: dict, event: dict) -> dict:
    """Shared API Gateway (Lambda proxy) entry point for every domain
    Lambda's `handler.py`: looks up `routes[(httpMethod, resource)]`,
    authenticates the caller via API Gateway's Cognito Authorizer claims
    (already verified before this Lambda runs -- AWSシステム構成設計書v1.2
    §5), and converts AuthError/BadRequest into the common error envelope
    (エラーコード一覧v1.1, API設計書v1.4 §2), so individual handler
    functions don't repeat this boilerplate.

    `routes` values are `handler_fn(user_id, event) -> dict` callables.
    Routing keys off `event["resource"]` (API Gateway's resolved resource
    path template, e.g. "/communities/{communityId}/members/{userId}")
    rather than the raw path, since API Gateway has already extracted
    `pathParameters` for us -- no regex path matching needed here.
    """
    route_key = (event.get("httpMethod"), event.get("resource"))
    handler_fn = routes.get(route_key)
    if handler_fn is None:
        return error_response("INVALID_PARAMETER", f"unknown route: {route_key}")

    try:
        user_id = get_authenticated_user_id(event)
        return handler_fn(user_id, event)
    except AuthError as exc:
        return error_response(exc.code, exc.message)
    except BadRequest as exc:
        return error_response("INVALID_PARAMETER", exc.message)
