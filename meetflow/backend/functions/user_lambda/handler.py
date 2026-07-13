from meetflow_common import (
    dispatch,
    error_response,
    get_table,
    now_iso_ms,
    parse_body,
    success_response,
)

# Not specified in the design docs; conservative MVP bounds for
# PROFILE_VALIDATION_ERROR (エラーコード一覧v1.1 §2).
_MAX_NICKNAME_LENGTH = 30
_MAX_BIO_LENGTH = 300

_ROUTES = {
    ("GET", "/users/me"): lambda user_id, event: _get_profile(user_id),
    ("PUT", "/users/me"): lambda user_id, event: _update_profile(user_id, event),
}


def handler(event, context):
    """UserLambda (Lambda設計書v1.1 §3): F-001 registration via Cognito Post
    Confirmation trigger, plus F-003 profile get/update via API Gateway.

    Cognito trigger events always carry `triggerSource` and never
    `httpMethod`; API Gateway proxy events always carry `httpMethod`. That's
    enough to route between the two without a separate entry point per
    trigger.
    """
    if "triggerSource" in event:
        return _handle_post_confirmation(event)
    return dispatch(_ROUTES, event)


def _handle_post_confirmation(event):
    # This trigger slot also fires for other Cognito flows (e.g. forgotten
    # password); only create a profile on actual sign-up confirmation.
    if event.get("triggerSource") != "PostConfirmation_ConfirmSignUp":
        return event

    attrs = event["request"]["userAttributes"]
    user_id = attrs["sub"]
    email = attrs.get("email", "")

    # Cognito holds only email/password (Lambda設計書v1.1 §3.1); nickname is
    # collected on the sign-up form (F-001) but is not a Cognito attribute,
    # so the client must pass it through SignUp's ClientMetadata to reach
    # this trigger. Fall back to the email's local part so registration
    # never hard-fails just because a client forgot to send it.
    nickname = event.get("request", {}).get("clientMetadata", {}).get("nickname")
    if not nickname:
        nickname = email.split("@")[0] if email else "名無しさん"

    get_table().put_item(
        Item={
            "PK": f"USER#{user_id}",
            "SK": "PROFILE",
            "userId": user_id,
            "nickname": nickname,
            "icon": "",
            "bio": "",
            "beginnerOk": False,
            "createdAt": now_iso_ms(),
        },
        # Post Confirmation can be retried by Cognito on transient failure;
        # don't clobber a profile that a previous attempt already created.
        ConditionExpression="attribute_not_exists(PK)",
    )
    return event


def _get_profile(user_id):
    item = get_table().get_item(Key={"PK": f"USER#{user_id}", "SK": "PROFILE"}).get(
        "Item"
    )
    if item is None:
        return error_response("USER_NOT_FOUND", "ユーザーが見つかりません")
    return success_response(_to_api_profile(item))


def _update_profile(user_id, event):
    body = parse_body(event)

    # F-003 manageable fields: nickname, icon, bio ("profile" in the API
    # contract, API設計書v1.4 §3.2), gameTypes, beginnerOk.
    nickname = body.get("nickname")
    if nickname is not None and not (
        isinstance(nickname, str) and 1 <= len(nickname) <= _MAX_NICKNAME_LENGTH
    ):
        return error_response("PROFILE_VALIDATION_ERROR", "ニックネームが不正です")

    bio = body.get("profile")
    if bio is not None and not (isinstance(bio, str) and len(bio) <= _MAX_BIO_LENGTH):
        return error_response("PROFILE_VALIDATION_ERROR", "自己紹介が長すぎます")

    names = {}
    values = {}
    set_clauses = []
    remove_clauses = []

    def _set(attr, value):
        names[f"#{attr}"] = attr
        values[f":{attr}"] = value
        set_clauses.append(f"#{attr} = :{attr}")

    if nickname is not None:
        _set("nickname", nickname)
    if bio is not None:
        _set("bio", bio)
    if "icon" in body:
        _set("icon", body["icon"])
    if "beginnerOk" in body:
        _set("beginnerOk", bool(body["beginnerOk"]))
    if "gameTypes" in body:
        game_types = body["gameTypes"] or []
        if game_types:
            _set("gameTypes", set(game_types))
        else:
            # DynamoDB rejects empty String Sets -- clearing the list means
            # removing the attribute entirely rather than SET-ing it to [].
            names["#gameTypes"] = "gameTypes"
            remove_clauses.append("#gameTypes")

    if not set_clauses and not remove_clauses:
        return error_response("INVALID_PARAMETER", "更新項目がありません")

    expression_parts = []
    if set_clauses:
        expression_parts.append("SET " + ", ".join(set_clauses))
    if remove_clauses:
        expression_parts.append("REMOVE " + ", ".join(remove_clauses))

    update_kwargs = {
        "Key": {"PK": f"USER#{user_id}", "SK": "PROFILE"},
        "UpdateExpression": " ".join(expression_parts),
        "ConditionExpression": "attribute_exists(PK)",
        "ExpressionAttributeNames": names,
    }
    if values:
        update_kwargs["ExpressionAttributeValues"] = values

    table = get_table()
    try:
        table.update_item(**update_kwargs)
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return error_response("USER_NOT_FOUND", "ユーザーが見つかりません")

    return _get_profile(user_id)


def _to_api_profile(item):
    # DynamoDB attribute `bio` is exposed as `profile` in the API contract
    # (API設計書v1.4 §3.1/3.2 response/request examples).
    return {
        "userId": item.get("userId"),
        "nickname": item.get("nickname"),
        "profile": item.get("bio", ""),
        "icon": item.get("icon", ""),
        "gameTypes": sorted(item["gameTypes"]) if item.get("gameTypes") else [],
        "beginnerOk": item.get("beginnerOk", False),
    }
