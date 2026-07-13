import json

from meetflow_common import now_iso_ms


def api_event(*, path_params=None, body=None, query=None):
    """Builds a minimal API Gateway (Lambda proxy integration) event, as far
    as the individual handler_fn(user_id, event) functions read it.
    """
    return {
        "pathParameters": path_params or {},
        "body": json.dumps(body) if body is not None else None,
        "queryStringParameters": query,
    }


def cognito_post_confirmation_event(
    *, user_id, email="taro@example.com", nickname=None, trigger_source="PostConfirmation_ConfirmSignUp"
):
    user_attributes = {"sub": user_id, "email": email}
    client_metadata = {"nickname": nickname} if nickname else {}
    return {
        "triggerSource": trigger_source,
        "request": {
            "userAttributes": user_attributes,
            "clientMetadata": client_metadata,
        },
    }


def put_profile(table, user_id, *, nickname="ぷれいやー"):
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
        }
    )


def body_of(response):
    return json.loads(response["body"])
