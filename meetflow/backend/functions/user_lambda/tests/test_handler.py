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
    """Cognito can retry the Post Confirmation trigger on transient failure
    (handler.py's own docstring/comment). A retry must not raise -- an
    uncaught exception here would fail the user's sign-up confirmation.
    """
    event = cognito_post_confirmation_event(user_id="user-1", nickname="たろう")
    handler._handle_post_confirmation(event)

    # Must not raise on the second (retried) invocation.
    handler._handle_post_confirmation(event)

    item = table.get_item(Key={"PK": "USER#user-1", "SK": "PROFILE"})["Item"]
    assert item["nickname"] == "たろう"
