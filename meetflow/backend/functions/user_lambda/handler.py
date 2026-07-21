import os
import uuid

import boto3

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

# Issue #47: アバター画像アップロード。許可フォーマットはFeedbackLambdaの
# 添付機能（feedback_lambda/handlers/attachments.py）と揃える。
_ALLOWED_AVATAR_CONTENT_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}
_AVATAR_UPLOAD_EXPIRES_IN_SECONDS = 300

_ROUTES = {
    ("GET", "/users/me"): lambda user_id, event: _get_profile(user_id),
    ("PUT", "/users/me"): lambda user_id, event: _update_profile(user_id, event),
    ("POST", "/users/me/avatar/upload-url"): (
        lambda user_id, event: _create_avatar_upload_url(user_id, event)
    ),
    ("DELETE", "/users/me/avatar"): lambda user_id, event: _delete_avatar(user_id),
}

_s3_client = None


def _get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


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
    if "autoApprove" in body:
        _set("autoApprove", bool(body["autoApprove"]))
    if "frequencyLimitCount" in body or "frequencyLimitPeriod" in body:
        limit_count = body.get("frequencyLimitCount")
        limit_period = body.get("frequencyLimitPeriod")
        if (limit_count is None) != (limit_period is None):
            return error_response(
                "PROFILE_VALIDATION_ERROR",
                "参加頻度上限は回数と期間を同時に設定・解除してください",
            )
        if limit_count is not None:
            if (
                not isinstance(limit_count, int)
                or isinstance(limit_count, bool)
                or limit_count <= 0
            ):
                return error_response(
                    "PROFILE_VALIDATION_ERROR", "上限回数は正の整数で指定してください"
                )
            if limit_period not in ("WEEK", "MONTH"):
                return error_response(
                    "PROFILE_VALIDATION_ERROR",
                    "期間はWEEK/MONTHのいずれかで指定してください",
                )
            _set("frequencyLimitCount", limit_count)
            _set("frequencyLimitPeriod", limit_period)
        else:
            names["#frequencyLimitCount"] = "frequencyLimitCount"
            names["#frequencyLimitPeriod"] = "frequencyLimitPeriod"
            remove_clauses.append("#frequencyLimitCount")
            remove_clauses.append("#frequencyLimitPeriod")
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


def _create_avatar_upload_url(user_id, event):
    """Issue #47: アバター画像アップロード用の署名付きPUT URLを発行する。

    フロントエンドはS3へ直接PUTした後、返却された`avatarUrl`をそのまま
    `PUT /users/me`の`icon`に渡して確定する（バイナリはAPI Gateway/Lambdaを
    経由しない、feedback_lambdaの添付機能と同じ方式）。アバター用バケットは
    CloudFront(OAC)経由の公開読み取りのため、フィードバック添付と異なり
    閲覧用の署名付きGET URLは不要で、CloudFrontドメインから直接組み立てた
    URLをそのまま返せる。
    """
    body = parse_body(event)
    content_type = body.get("contentType")
    if content_type not in _ALLOWED_AVATAR_CONTENT_TYPES:
        return error_response(
            "PROFILE_VALIDATION_ERROR", "画像形式はPNG/JPEG/WebPのいずれかにしてください"
        )

    ext = _ALLOWED_AVATAR_CONTENT_TYPES[content_type]
    avatar_key = f"avatars/{user_id}/{uuid.uuid4().hex}.{ext}"
    upload_url = _get_s3_client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": os.environ["AVATAR_BUCKET_NAME"],
            "Key": avatar_key,
            "ContentType": content_type,
        },
        ExpiresIn=_AVATAR_UPLOAD_EXPIRES_IN_SECONDS,
    )
    avatar_url = f"https://{os.environ['AVATAR_CLOUDFRONT_DOMAIN']}/{avatar_key}"

    return success_response(
        {
            "uploadUrl": upload_url,
            "avatarUrl": avatar_url,
            "expiresIn": _AVATAR_UPLOAD_EXPIRES_IN_SECONDS,
        }
    )


def _delete_avatar(user_id):
    """Issue #76: プロフィール画像の削除。DB上のicon参照をクリアするのに
    加えて、S3上のアップロード済みファイルも削除する。iconが既に空の
    場合は何もせず現在のプロフィールを返す(冪等)。
    """
    table = get_table()
    item = table.get_item(Key={"PK": f"USER#{user_id}", "SK": "PROFILE"}).get("Item")
    if item is None:
        return error_response("USER_NOT_FOUND", "ユーザーが見つかりません")

    icon = item.get("icon", "")
    if not icon:
        return success_response(_to_api_profile(item))

    # 自分がアップロードしたアバターバケット配下のファイルであることを
    # URLのプレフィックスで確認してから削除する(不正な外部URLが
    # iconに紛れ込んでいた場合に誤って任意のキーを消さないため)。
    avatar_prefix = f"https://{os.environ['AVATAR_CLOUDFRONT_DOMAIN']}/"
    if icon.startswith(avatar_prefix):
        avatar_key = icon[len(avatar_prefix):]
        _get_s3_client().delete_object(
            Bucket=os.environ["AVATAR_BUCKET_NAME"], Key=avatar_key
        )

    table.update_item(
        Key={"PK": f"USER#{user_id}", "SK": "PROFILE"},
        UpdateExpression="SET #icon = :icon",
        ExpressionAttributeNames={"#icon": "icon"},
        ExpressionAttributeValues={":icon": ""},
    )

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
        "autoApprove": item.get("autoApprove", False),
        "frequencyLimitCount": item.get("frequencyLimitCount"),
        "frequencyLimitPeriod": item.get("frequencyLimitPeriod"),
    }
