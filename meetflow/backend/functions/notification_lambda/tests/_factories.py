import json

from meetflow_common import now_iso_ms


def api_event(*, path_params=None, body=None, query=None):
    """Builds a minimal API Gateway (Lambda proxy integration) event, as far
    as the individual handler_fn(user_id, event) functions read it -- they
    never touch requestContext/httpMethod/resource themselves, that's
    dispatch()'s job.
    """
    return {
        "pathParameters": path_params or {},
        "body": json.dumps(body) if body is not None else None,
        "queryStringParameters": query,
    }


def put_membership(table, community_id, user_id, *, role="MEMBER", status="ACTIVE"):
    table.put_item(
        Item={
            "PK": f"COMMUNITY#{community_id}",
            "SK": f"MEMBER#{user_id}",
            "GSI1PK": f"USER#{user_id}",
            "GSI1SK": f"COMMUNITY#{community_id}",
            "role": role,
            "status": status,
            "joinedAt": now_iso_ms(),
        }
    )


def domain_event(detail_type, detail):
    """EventBridge event shape as delivered to a Lambda target -- only the
    fields event_subscriber.handle_domain_event reads.
    """
    return {"detail-type": detail_type, "source": "meetflow.events", "detail": detail}


def body_of(response):
    return json.loads(response["body"])
