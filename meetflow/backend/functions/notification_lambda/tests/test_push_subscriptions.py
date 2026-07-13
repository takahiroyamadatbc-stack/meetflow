import hashlib

from boto3.dynamodb.conditions import Key

from handlers import push_subscriptions

from _factories import api_event, body_of

_ENDPOINT = "https://fcm.googleapis.com/fcm/send/xxxxx"
_ENDPOINT_HASH = hashlib.sha256(_ENDPOINT.encode("utf-8")).hexdigest()


def test_register_push_subscription_success(table):
    response = push_subscriptions.register_push_subscription(
        "user-1",
        api_event(
            body={
                "endpoint": _ENDPOINT,
                "keys": {"p256dh": "p256dh-value", "auth": "auth-value"},
                "userAgent": "Mozilla/5.0",
            }
        ),
    )

    assert response["statusCode"] == 201
    assert body_of(response)["data"]["endpointHash"] == _ENDPOINT_HASH
    item = table.get_item(
        Key={"PK": "USER#user-1", "SK": f"PUSHSUB#{_ENDPOINT_HASH}"}
    )["Item"]
    assert item["endpoint"] == _ENDPOINT
    assert item["p256dh"] == "p256dh-value"
    assert item["auth"] == "auth-value"
    assert item["userAgent"] == "Mozilla/5.0"


def test_register_push_subscription_overwrites_same_endpoint(table):
    body = {
        "endpoint": _ENDPOINT,
        "keys": {"p256dh": "old-key", "auth": "old-auth"},
    }
    push_subscriptions.register_push_subscription("user-1", api_event(body=body))

    body["keys"] = {"p256dh": "new-key", "auth": "new-auth"}
    push_subscriptions.register_push_subscription("user-1", api_event(body=body))

    resp = table.query(KeyConditionExpression=Key("PK").eq("USER#user-1"))
    assert len(resp["Items"]) == 1
    assert resp["Items"][0]["p256dh"] == "new-key"


def test_register_push_subscription_missing_endpoint(table):
    response = push_subscriptions.register_push_subscription(
        "user-1",
        api_event(body={"keys": {"p256dh": "p256dh-value", "auth": "auth-value"}}),
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "INVALID_PARAMETER"


def test_register_push_subscription_missing_keys(table):
    response = push_subscriptions.register_push_subscription(
        "user-1", api_event(body={"endpoint": _ENDPOINT})
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "INVALID_PARAMETER"


def test_unregister_push_subscription_success(table):
    push_subscriptions.register_push_subscription(
        "user-1",
        api_event(
            body={
                "endpoint": _ENDPOINT,
                "keys": {"p256dh": "p256dh-value", "auth": "auth-value"},
            }
        ),
    )

    response = push_subscriptions.unregister_push_subscription(
        "user-1", api_event(body={"endpoint": _ENDPOINT})
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["unregistered"] is True
    assert (
        table.get_item(
            Key={"PK": "USER#user-1", "SK": f"PUSHSUB#{_ENDPOINT_HASH}"}
        ).get("Item")
        is None
    )


def test_unregister_push_subscription_is_idempotent_when_not_found(table):
    response = push_subscriptions.unregister_push_subscription(
        "user-1", api_event(body={"endpoint": "https://never-registered.example/x"})
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["unregistered"] is True


def test_unregister_push_subscription_missing_endpoint(table):
    response = push_subscriptions.unregister_push_subscription(
        "user-1", api_event(body={})
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "INVALID_PARAMETER"
