import hashlib

from meetflow_common import error_response, get_table, now_iso_ms, parse_body, success_response


def register_push_subscription(user_id, event):
    """F-703 (API設計書v1.5 §11.3). `endpointHash` (DynamoDB物理設計書v1.4
    §3.17) makes re-registering the same browser endpoint a natural
    overwrite via PutItem, and unregistration a direct DeleteItem by the
    same hash -- no Query needed either way.
    """
    body = parse_body(event)
    endpoint = body.get("endpoint")
    keys = body.get("keys")
    if not isinstance(endpoint, str) or not endpoint:
        return error_response("INVALID_PARAMETER", "endpointが不正です")
    if (
        not isinstance(keys, dict)
        or not isinstance(keys.get("p256dh"), str)
        or not keys.get("p256dh")
        or not isinstance(keys.get("auth"), str)
        or not keys.get("auth")
    ):
        return error_response("INVALID_PARAMETER", "keysが不正です")
    user_agent = body.get("userAgent")
    if user_agent is not None and not isinstance(user_agent, str):
        return error_response("INVALID_PARAMETER", "userAgentが不正です")

    endpoint_hash = _hash_endpoint(endpoint)
    table = get_table()
    item = {
        "PK": f"USER#{user_id}",
        "SK": f"PUSHSUB#{endpoint_hash}",
        "endpoint": endpoint,
        "p256dh": keys["p256dh"],
        "auth": keys["auth"],
        "createdAt": now_iso_ms(),
    }
    if user_agent:
        item["userAgent"] = user_agent
    table.put_item(Item=item)

    return success_response({"endpointHash": endpoint_hash}, status_code=201)


def unregister_push_subscription(user_id, event):
    """F-704 (API設計書v1.5 §11.4). Idempotent by design -- エラーコード一覧
    v1.2 §8: unregistering an endpoint that's already gone (or never
    existed) is still a success, not a dedicated not-found error.
    """
    body = parse_body(event)
    endpoint = body.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint:
        return error_response("INVALID_PARAMETER", "endpointが不正です")

    endpoint_hash = _hash_endpoint(endpoint)
    table = get_table()
    table.delete_item(Key={"PK": f"USER#{user_id}", "SK": f"PUSHSUB#{endpoint_hash}"})

    return success_response({"unregistered": True})


def _hash_endpoint(endpoint):
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()
