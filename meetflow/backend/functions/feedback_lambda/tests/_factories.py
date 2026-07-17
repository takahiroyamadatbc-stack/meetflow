import json


def api_event(*, path_params=None, body=None, query=None, groups=None):
    """Builds a minimal API Gateway (Lambda proxy integration) event.

    Unlike most other domains' handler_fn(user_id, event), FeedbackLambdaの
    運営者限定ハンドラーはevent自体からcognito:groupsクレームを読む
    (handlers/operators.py)ため、他ドメインの`api_event`と異なり
    requestContext.authorizer.claimsも組み立てる。
    """
    event = {
        "pathParameters": path_params or {},
        "body": json.dumps(body) if body is not None else None,
        "queryStringParameters": query,
    }
    if groups is not None:
        event["requestContext"] = {
            "authorizer": {"claims": {"cognito:groups": ",".join(groups)}}
        }
    return event


def body_of(response):
    return json.loads(response["body"])
