import os
import uuid

import boto3
from boto3.dynamodb.conditions import Key

from meetflow_common import (
    dispatch,
    error_response,
    get_table,
    has_upcoming_reserved_participation,
    now_iso_ms,
    parse_body,
    success_response,
    write_operation_log,
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
    ("DELETE", "/users/me"): lambda user_id, event: _delete_account(user_id),
    ("POST", "/users/me/avatar/upload-url"): (
        lambda user_id, event: _create_avatar_upload_url(user_id, event)
    ),
    ("DELETE", "/users/me/avatar"): lambda user_id, event: _delete_avatar(user_id),
}

_s3_client = None
_cognito_client = None


def _get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


def _get_cognito_client():
    global _cognito_client
    if _cognito_client is None:
        _cognito_client = boto3.client("cognito-idp")
    return _cognito_client


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


def _delete_account(user_id):
    """Issue #82: アカウント削除(Cognitoユーザー自体の退会)。

    コミュニティ単位の自主退会(community_lambdaのleave_community)と
    同じ制約を、所属する全コミュニティに対して適用する:
    (1) いずれかでOWNERを務めている場合は、先にオーナー移譲(Issue #24)
        が必要(LAST_OWNER_CANNOT_LEAVEを流用)。
    (2) いずれかで未来の確定イベント参加が残っている場合は、先にキャン
        セル申請が必要(MEMBER_HAS_UPCOMING_EVENTSを流用、Issue #25/#26と
        同じhas_upcoming_reserved_participationで判定)。
    実際の削除処理(Cognitoユーザー削除・Membership削除・Profile削除)を
    始める前に全コミュニティ分を検証し、途中まで削除が進んだ状態を避ける。

    過去の成績(GameResult等)やOperationLog等、他メンバー・コミュニティ
    運営に必要な履歴データは削除しない(本Issueのスコープ外、保持方針は
    別途検討)。userIdへの参照は残るが、実データはUserプロフィール
    (nickname/icon等)を介さず各エンティティ側に非正規化コピーされている
    ため、表示上大きな支障はない。
    """
    table = get_table()

    resp = table.query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq(f"USER#{user_id}")
        & Key("GSI1SK").begins_with("COMMUNITY#"),
    )
    memberships = resp.get("Items", [])

    for m in memberships:
        if m.get("role") == "OWNER":
            return error_response(
                "LAST_OWNER_CANNOT_LEAVE",
                "オーナーを務めているコミュニティがあります。先にオーナーを移譲してください",
                status_code=409,
            )
    for m in memberships:
        community_id = m["GSI1SK"].split("#", 1)[1]
        if has_upcoming_reserved_participation(table, user_id, community_id):
            return error_response(
                "MEMBER_HAS_UPCOMING_EVENTS",
                "未来の確定イベント参加が残っているコミュニティがあります。"
                "先にイベント参加のキャンセル申請をしてください",
                status_code=409,
            )

    _get_cognito_client().admin_delete_user(
        UserPoolId=os.environ["USER_POOL_ID"], Username=user_id
    )

    for m in memberships:
        community_id = m["GSI1SK"].split("#", 1)[1]
        table.delete_item(
            Key={"PK": f"COMMUNITY#{community_id}", "SK": f"MEMBER#{user_id}"}
        )
    table.delete_item(Key={"PK": f"USER#{user_id}", "SK": "PROFILE"})

    write_operation_log(
        action="DELETE_ACCOUNT",
        user_id=user_id,
        target_type="User",
        target_id=user_id,
    )

    return success_response({"userId": user_id, "deleted": True})


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
