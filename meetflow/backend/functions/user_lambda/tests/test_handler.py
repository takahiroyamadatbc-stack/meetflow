import os

import boto3

import handler

from _factories import api_event, body_of, cognito_post_confirmation_event, put_profile


def test_get_profile_success(table):
    put_profile(table, "user-1", nickname="たろう")

    response = handler._get_profile("user-1")

    assert response["statusCode"] == 200
    data = body_of(response)["data"]
    assert data["userId"] == "user-1"
    assert data["nickname"] == "たろう"


def test_get_profile_not_found(table):
    response = handler._get_profile("user-1")

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "USER_NOT_FOUND"


def test_update_profile_success(table):
    put_profile(table, "user-1")

    response = handler._update_profile(
        "user-1",
        api_event(
            body={
                "nickname": "新しい名前",
                "profile": "麻雀好きです",
                "icon": "icon.png",
                "beginnerOk": True,
                "gameTypes": ["MAHJONG4", "MAHJONG3"],
            }
        ),
    )

    assert response["statusCode"] == 200
    data = body_of(response)["data"]
    assert data["nickname"] == "新しい名前"
    assert data["profile"] == "麻雀好きです"
    assert data["icon"] == "icon.png"
    assert data["beginnerOk"] is True
    assert data["gameTypes"] == ["MAHJONG3", "MAHJONG4"]


def test_update_profile_auto_approve(table):
    """Issue #10: 自動承認フラグ(全体デフォルト)をON/OFFできること。"""
    put_profile(table, "user-1")

    response = handler._update_profile(
        "user-1", api_event(body={"autoApprove": True})
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["autoApprove"] is True

    response = handler._update_profile(
        "user-1", api_event(body={"autoApprove": False})
    )

    assert body_of(response)["data"]["autoApprove"] is False


def test_get_profile_auto_approve_defaults_false(table):
    put_profile(table, "user-1")

    response = handler._get_profile("user-1")

    assert body_of(response)["data"]["autoApprove"] is False


def test_update_profile_frequency_limit_set(table):
    """Issue #19: 参加頻度上限(全体デフォルト)を回数+期間で設定できること。"""
    put_profile(table, "user-1")

    response = handler._update_profile(
        "user-1",
        api_event(body={"frequencyLimitCount": 2, "frequencyLimitPeriod": "MONTH"}),
    )

    assert response["statusCode"] == 200
    data = body_of(response)["data"]
    assert data["frequencyLimitCount"] == 2
    assert data["frequencyLimitPeriod"] == "MONTH"


def test_update_profile_frequency_limit_clear(table):
    put_profile(table, "user-1")
    handler._update_profile(
        "user-1",
        api_event(body={"frequencyLimitCount": 1, "frequencyLimitPeriod": "WEEK"}),
    )

    response = handler._update_profile(
        "user-1",
        api_event(body={"frequencyLimitCount": None, "frequencyLimitPeriod": None}),
    )

    assert response["statusCode"] == 200
    data = body_of(response)["data"]
    assert data["frequencyLimitCount"] is None
    assert data["frequencyLimitPeriod"] is None


def test_update_profile_frequency_limit_partial_only_count(table):
    put_profile(table, "user-1")

    response = handler._update_profile(
        "user-1", api_event(body={"frequencyLimitCount": 2})
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "PROFILE_VALIDATION_ERROR"


def test_update_profile_frequency_limit_non_positive_count(table):
    put_profile(table, "user-1")

    response = handler._update_profile(
        "user-1",
        api_event(body={"frequencyLimitCount": 0, "frequencyLimitPeriod": "WEEK"}),
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "PROFILE_VALIDATION_ERROR"


def test_update_profile_frequency_limit_invalid_period(table):
    put_profile(table, "user-1")

    response = handler._update_profile(
        "user-1",
        api_event(body={"frequencyLimitCount": 2, "frequencyLimitPeriod": "YEAR"}),
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "PROFILE_VALIDATION_ERROR"


def test_get_profile_frequency_limit_defaults_null(table):
    put_profile(table, "user-1")

    response = handler._get_profile("user-1")

    data = body_of(response)["data"]
    assert data["frequencyLimitCount"] is None
    assert data["frequencyLimitPeriod"] is None


def test_update_profile_invalid_nickname_too_long(table):
    put_profile(table, "user-1")

    response = handler._update_profile(
        "user-1", api_event(body={"nickname": "あ" * 31})
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "PROFILE_VALIDATION_ERROR"


def test_update_profile_invalid_bio_too_long(table):
    put_profile(table, "user-1")

    response = handler._update_profile(
        "user-1", api_event(body={"profile": "あ" * 301})
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "PROFILE_VALIDATION_ERROR"


def test_update_profile_no_fields(table):
    put_profile(table, "user-1")

    response = handler._update_profile("user-1", api_event(body={}))

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "INVALID_PARAMETER"


def test_update_profile_not_found(table):
    response = handler._update_profile(
        "user-1", api_event(body={"nickname": "誰か"})
    )

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "USER_NOT_FOUND"


def test_update_profile_clears_game_types_with_empty_list(table):
    put_profile(table, "user-1")
    handler._update_profile(
        "user-1", api_event(body={"gameTypes": ["MAHJONG4"]})
    )

    response = handler._update_profile("user-1", api_event(body={"gameTypes": []}))

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["gameTypes"] == []


def test_create_avatar_upload_url_success(table):
    put_profile(table, "user-1")

    response = handler._create_avatar_upload_url(
        "user-1", api_event(body={"contentType": "image/webp"})
    )

    assert response["statusCode"] == 200
    data = body_of(response)["data"]
    assert data["uploadUrl"].startswith("https://")
    assert data["avatarUrl"].startswith(
        "https://avatars.test.cloudfront.net/avatars/user-1/"
    )
    assert data["avatarUrl"].endswith(".webp")
    assert data["expiresIn"] == 300


def test_create_avatar_upload_url_rejects_unsupported_content_type(table):
    response = handler._create_avatar_upload_url(
        "user-1", api_event(body={"contentType": "application/pdf"})
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "PROFILE_VALIDATION_ERROR"


def _create_avatar_bucket_with_object(avatar_key):
    s3 = boto3.client("s3", region_name=os.environ["AWS_DEFAULT_REGION"])
    s3.create_bucket(
        Bucket=os.environ["AVATAR_BUCKET_NAME"],
        CreateBucketConfiguration={
            "LocationConstraint": os.environ["AWS_DEFAULT_REGION"]
        },
    )
    s3.put_object(Bucket=os.environ["AVATAR_BUCKET_NAME"], Key=avatar_key, Body=b"dummy")
    return s3


def test_delete_avatar_clears_icon_and_deletes_s3_object(table):
    avatar_key = "avatars/user-1/original.webp"
    icon_url = f"https://{os.environ['AVATAR_CLOUDFRONT_DOMAIN']}/{avatar_key}"
    put_profile(table, "user-1", icon=icon_url)
    s3 = _create_avatar_bucket_with_object(avatar_key)

    response = handler._delete_avatar("user-1")

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["icon"] == ""
    remaining = s3.list_objects_v2(Bucket=os.environ["AVATAR_BUCKET_NAME"])
    assert remaining.get("KeyCount", 0) == 0


def test_delete_avatar_is_noop_when_icon_already_empty(table):
    put_profile(table, "user-1", icon="")

    response = handler._delete_avatar("user-1")

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["icon"] == ""


def test_delete_avatar_ignores_urls_outside_avatar_bucket(table):
    # 万一不正な外部URLがiconに入っていた場合でも、S3削除は試みず
    # DB上の参照クリアのみ行う。
    put_profile(table, "user-1", icon="https://example.com/not-an-avatar.png")

    response = handler._delete_avatar("user-1")

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["icon"] == ""


def test_delete_avatar_not_found(table):
    response = handler._delete_avatar("unknown-user")

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "USER_NOT_FOUND"


def test_post_confirmation_creates_profile_with_nickname_from_client_metadata(table):
    event = cognito_post_confirmation_event(
        user_id="user-1", email="taro@example.com", nickname="たろちゃん"
    )

    result = handler._handle_post_confirmation(event)

    assert result is event
    item = table.get_item(Key={"PK": "USER#user-1", "SK": "PROFILE"})["Item"]
    assert item["nickname"] == "たろちゃん"


def test_post_confirmation_falls_back_to_email_local_part(table):
    event = cognito_post_confirmation_event(user_id="user-1", email="taro@example.com")

    handler._handle_post_confirmation(event)

    item = table.get_item(Key={"PK": "USER#user-1", "SK": "PROFILE"})["Item"]
    assert item["nickname"] == "taro"


def test_post_confirmation_ignores_non_confirm_signup_trigger(table):
    event = cognito_post_confirmation_event(
        user_id="user-1", trigger_source="PostConfirmation_ConfirmForgotPassword"
    )

    handler._handle_post_confirmation(event)

    assert (
        table.get_item(Key={"PK": "USER#user-1", "SK": "PROFILE"}).get("Item") is None
    )


def test_post_confirmation_is_idempotent_on_cognito_retry(table):
    """Cognitoは一時的な失敗時にPost Confirmationトリガーをリトライすることが
    ある（handler.py自身のdocstring/コメント参照）。リトライ時に例外が
    発生してはならない -- ここで例外が捕捉されないと、ユーザーのサインアップ
    確認自体が失敗してしまう。
    """
    event = cognito_post_confirmation_event(user_id="user-1", nickname="たろう")
    handler._handle_post_confirmation(event)

    # 2回目（リトライ）の呼び出しで例外が発生してはならない。
    handler._handle_post_confirmation(event)

    item = table.get_item(Key={"PK": "USER#user-1", "SK": "PROFILE"})["Item"]
    assert item["nickname"] == "たろう"
