import json

from meetflow_common import now_iso_ms


def api_event(*, path_params=None, body=None, query=None):
    return {
        "pathParameters": path_params or {},
        "body": json.dumps(body) if body is not None else None,
        "queryStringParameters": query,
    }


def domain_event(detail_type, detail):
    return {"detail-type": detail_type, "source": "meetflow.events", "detail": detail}


def put_community(table, community_id, *, owner_id="user-1", genre="麻雀"):
    table.put_item(
        Item={
            "PK": f"COMMUNITY#{community_id}",
            "SK": "METADATA",
            "name": "テストコミュニティ",
            "description": "",
            "genre": genre,
            "memberApprovalRequired": False,
            "communityType": "PERSONAL",
            "ownerId": owner_id,
            "createdAt": now_iso_ms(),
        }
    )


def put_membership(
    table,
    community_id,
    user_id,
    *,
    role="MEMBER",
    status="ACTIVE",
    display_name=None,
    frequency_limit_count=None,
    frequency_limit_period=None,
):
    item = {
        "PK": f"COMMUNITY#{community_id}",
        "SK": f"MEMBER#{user_id}",
        "GSI1PK": f"USER#{user_id}",
        "GSI1SK": f"COMMUNITY#{community_id}",
        "role": role,
        "status": status,
        "joinedAt": now_iso_ms(),
    }
    if display_name:
        item["displayName"] = display_name
    if frequency_limit_count is not None:
        item["frequencyLimitCount"] = frequency_limit_count
        item["frequencyLimitPeriod"] = frequency_limit_period
    table.put_item(Item=item)


def put_profile(
    table,
    user_id,
    *,
    nickname="ぷれいやー",
    beginner_ok=False,
    frequency_limit_count=None,
    frequency_limit_period=None,
):
    item = {
        "PK": f"USER#{user_id}",
        "SK": "PROFILE",
        "nickname": nickname,
        "bio": "",
        "beginnerOk": beginner_ok,
    }
    if frequency_limit_count is not None:
        item["frequencyLimitCount"] = frequency_limit_count
        item["frequencyLimitPeriod"] = frequency_limit_period
    table.put_item(Item=item)


def put_template(
    table,
    community_id,
    template_id,
    *,
    game_type="MAHJONG4",
    min_players=4,
    max_players=4,
    priority=50,
    conditions=None,
):
    table.put_item(
        Item={
            "PK": f"COMMUNITY#{community_id}",
            "SK": f"TEMPLATE#{template_id}",
            "gameType": game_type,
            "minPlayers": min_players,
            "maxPlayers": max_players,
            "priority": priority,
            "conditions": conditions or {},
            "createdAt": now_iso_ms(),
        }
    )


def put_availability(
    table, community_id, user_id, *, start_time, end_time, game_types=None, availability_id="avail-1"
):
    item = {
        "PK": f"COMMUNITY#{community_id}",
        "SK": f"AVAIL#{start_time}#{availability_id}",
        "GSI1PK": f"USER#{user_id}",
        "GSI1SK": f"AVAIL#{start_time}",
        "userId": user_id,
        "endTime": end_time,
        "comment": "",
        "createdAt": now_iso_ms(),
    }
    if game_types:
        item["gameTypes"] = set(game_types)
    table.put_item(Item=item)


def put_candidate_member(
    table,
    community_id,
    candidate_id,
    user_id,
    *,
    start_time,
    end_time,
    status="PENDING",
):
    table.put_item(
        Item={
            "PK": f"COMMUNITY#{community_id}",
            "SK": f"CANDIDATE#{candidate_id}#MEMBER#{user_id}",
            "GSI1PK": f"USER#{user_id}",
            "GSI1SK": f"CANDIDATE#{start_time}#{candidate_id}",
            "candidateId": candidate_id,
            "startTime": start_time,
            "endTime": end_time,
            "status": status,
            "conflictWarning": False,
            "createdAt": now_iso_ms(),
        }
    )


def put_participant(
    table,
    event_id,
    user_id,
    *,
    start_time,
    end_time,
    status="CONFIRMED",
    community_genre=None,
):
    item = {
        "PK": f"EVENT#{event_id}",
        "SK": f"PARTICIPANT#{user_id}",
        "GSI1PK": f"USER#{user_id}",
        "GSI1SK": f"PARTICIPANT#{start_time}#{event_id}",
        "status": status,
        "startTime": start_time,
        "endTime": end_time,
        "joinedAt": now_iso_ms(),
    }
    if community_genre is not None:
        item["communityGenre"] = community_genre
    table.put_item(Item=item)


def body_of(response):
    return json.loads(response["body"])
