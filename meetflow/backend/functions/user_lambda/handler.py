from meetflow_common import (
    dispatch,
    error_response,
    get_table,
    now_iso_ms,
    parse_body,
    success_response,
)

# 設計書には明記されていない、PROFILE_VALIDATION_ERROR
# （エラーコード一覧v1.1 §2）のためのMVP向け保守的な上限値。
_MAX_NICKNAME_LENGTH = 30
_MAX_BIO_LENGTH = 300

_ROUTES = {
    ("GET", "/users/me"): lambda user_id, event: _get_profile(user_id),
    ("PUT", "/users/me"): lambda user_id, event: _update_profile(user_id, event),
}


def handler(event, context):
    """UserLambda（Lambda設計書v1.1 §3）: Cognito Post Confirmationトリガー
    経由のF-001登録処理、およびAPI Gateway経由のF-003プロフィール取得/更新。

    Cognitoトリガーイベントは常に`triggerSource`を持ち`httpMethod`は持たない。
    API Gatewayプロキシイベントは常に`httpMethod`を持つ。トリガーごとに
    別々のエントリポイントを用意しなくても、この違いだけで両者を振り分けるのに
    十分である。
    """
    if "triggerSource" in event:
        return _handle_post_confirmation(event)
    return dispatch(_ROUTES, event)


def _handle_post_confirmation(event):
    # このトリガー枠は他のCognitoフロー（パスワード忘れ等）でも発火するため、
    # 実際のサインアップ確認時にのみプロフィールを作成する。
    if event.get("triggerSource") != "PostConfirmation_ConfirmSignUp":
        return event

    attrs = event["request"]["userAttributes"]
    user_id = attrs["sub"]
    email = attrs.get("email", "")

    # Cognitoが保持するのはメール/パスワードのみ（Lambda設計書v1.1 §3.1）。
    # ニックネームはサインアップフォーム（F-001）で収集するがCognito属性では
    # ないため、クライアントはSignUpのClientMetadata経由でこのトリガーまで
    # 渡す必要がある。クライアントが送り忘れただけで登録が完全に失敗しない
    # よう、メールのローカル部にフォールバックする。
    nickname = event.get("request", {}).get("clientMetadata", {}).get("nickname")
    if not nickname:
        nickname = email.split("@")[0] if email else "名無しさん"

    table = get_table()
    try:
        table.put_item(
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
            # Post Confirmationは一時的な失敗時にCognitoからリトライされうる。
            # 前回の試行ですでに作成済みのプロフィールを上書きしないこと。
            ConditionExpression="attribute_not_exists(PK)",
        )
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        pass
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

    # F-003で更新可能なフィールド: nickname, icon, bio（APIの契約上は
    # "profile"、API設計書v1.4 §3.2）, gameTypes, beginnerOk。
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
            # DynamoDBは空のString Setを拒否する -- リストのクリアは
            # 空配列でSETするのではなく、属性自体をREMOVEすることを意味する。
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
    # DynamoDBの`bio`属性は、APIの契約上は`profile`として公開される
    # （API設計書v1.4 §3.1/3.2のレスポンス/リクエスト例）。
    return {
        "userId": item.get("userId"),
        "nickname": item.get("nickname"),
        "profile": item.get("bio", ""),
        "icon": item.get("icon", ""),
        "gameTypes": sorted(item["gameTypes"]) if item.get("gameTypes") else [],
        "beginnerOk": item.get("beginnerOk", False),
    }
