from handlers import events

from _factories import (
    api_event,
    body_of,
    put_candidate,
    put_confirmed_participant,
    put_event_status,
    put_membership,
    put_place,
)


def test_create_event_success(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    start_time, end_time = put_candidate(
        table, "community-1", "candidate-1", ["user-1", "user-2", "user-3", "user-4"]
    )

    response = events.create_event(
        "user-1", api_event(body={"candidateId": "candidate-1"})
    )

    assert response["statusCode"] == 201
    data = body_of(response)["data"]
    assert data["status"] == "PENDING_APPROVAL"
    assert data["startTime"] == start_time
    assert data["endTime"] == end_time

    candidate = table.get_item(
        Key={
            "PK": "COMMUNITY#community-1",
            "SK": f"CANDIDATE#{start_time}#candidate-1",
        }
    )["Item"]
    assert candidate["status"] == "CONFIRMED"


def test_create_event_missing_candidate_id(table):
    response = events.create_event("user-1", api_event(body={}))

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "INVALID_PARAMETER"


def test_create_event_candidate_not_found(table):
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = events.create_event(
        "user-1", api_event(body={"candidateId": "no-such"})
    )

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "CANDIDATE_NOT_FOUND"


def test_create_event_candidate_already_used(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_candidate(
        table,
        "community-1",
        "candidate-1",
        ["user-1", "user-2"],
        status="CONFIRMED",
    )

    response = events.create_event(
        "user-1", api_event(body={"candidateId": "candidate-1"})
    )

    assert response["statusCode"] == 409
    assert body_of(response)["error"]["code"] == "CANDIDATE_ALREADY_USED"


def test_create_event_location_not_found(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_candidate(table, "community-1", "candidate-1", ["user-1", "user-2"])

    response = events.create_event(
        "user-1",
        api_event(body={"candidateId": "candidate-1", "locationId": "no-such"}),
    )

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "LOCATION_NOT_FOUND"


def test_get_event_success(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_place(table, "community-1", "place-1")
    put_candidate(table, "community-1", "candidate-1", ["user-1", "user-2"])
    create_response = events.create_event(
        "user-1",
        api_event(body={"candidateId": "candidate-1", "locationId": "place-1"}),
    )
    event_id = body_of(create_response)["data"]["eventId"]

    response = events.get_event(
        "user-1", api_event(path_params={"eventId": event_id})
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["location"]["placeId"] == "place-1"


def test_get_event_not_found(table):
    response = events.get_event(
        "user-1", api_event(path_params={"eventId": "does-not-exist"})
    )

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "EVENT_NOT_FOUND"


def _create_pending_event(table, community_id="community-1", member_ids=None):
    member_ids = member_ids or ["user-1", "user-2", "user-3", "user-4"]
    put_membership(table, community_id, "user-1", role="OWNER")
    put_candidate(table, community_id, "candidate-1", member_ids)
    create_response = events.create_event(
        "user-1", api_event(body={"candidateId": "candidate-1"})
    )
    return body_of(create_response)["data"]["eventId"]


def test_confirm_event_success(table):
    event_id = _create_pending_event(table)

    response = events.confirm_event(
        "user-1", api_event(path_params={"eventId": event_id})
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["status"] == "CONFIRMED"
    for uid in ("user-1", "user-2", "user-3", "user-4"):
        participant = table.get_item(
            Key={"PK": f"EVENT#{event_id}", "SK": f"PARTICIPANT#{uid}"}
        )["Item"]
        assert participant["status"] == "CONFIRMED"


def test_confirm_event_already_confirmed(table):
    event_id = _create_pending_event(table)
    events.confirm_event("user-1", api_event(path_params={"eventId": event_id}))

    response = events.confirm_event(
        "user-1", api_event(path_params={"eventId": event_id})
    )

    assert response["statusCode"] == 409
    assert body_of(response)["error"]["code"] == "EVENT_ALREADY_CONFIRMED"


def test_confirm_event_already_cancelled(table):
    event_id = _create_pending_event(table)
    events.cancel_event("user-1", api_event(path_params={"eventId": event_id}))

    response = events.confirm_event(
        "user-1", api_event(path_params={"eventId": event_id})
    )

    assert response["statusCode"] == 409
    assert body_of(response)["error"]["code"] == "EVENT_ALREADY_CANCELLED"


def test_confirm_event_participant_schedule_conflict(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    start_time, end_time = put_candidate(
        table, "community-1", "candidate-1", ["user-1", "user-2"]
    )
    put_confirmed_participant(table, "user-2", start_time=start_time, end_time=end_time)
    create_response = events.create_event(
        "user-1", api_event(body={"candidateId": "candidate-1"})
    )
    event_id = body_of(create_response)["data"]["eventId"]

    response = events.confirm_event(
        "user-1", api_event(path_params={"eventId": event_id})
    )

    assert response["statusCode"] == 409
    assert body_of(response)["error"]["code"] == "PARTICIPANT_SCHEDULE_CONFLICT"


def test_cancel_event_success(table):
    event_id = _create_pending_event(table)

    response = events.cancel_event(
        "user-1", api_event(path_params={"eventId": event_id})
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["status"] == "CANCELLED"


def test_cancel_event_already_cancelled(table):
    event_id = _create_pending_event(table)
    events.cancel_event("user-1", api_event(path_params={"eventId": event_id}))

    response = events.cancel_event(
        "user-1", api_event(path_params={"eventId": event_id})
    )

    assert response["statusCode"] == 409
    assert body_of(response)["error"]["code"] == "EVENT_ALREADY_CANCELLED"


def test_cancel_event_completed_cannot_be_cancelled(table):
    event_id = _create_pending_event(table)
    events.confirm_event("user-1", api_event(path_params={"eventId": event_id}))
    put_event_status(table, event_id, "COMPLETED")

    response = events.cancel_event(
        "user-1", api_event(path_params={"eventId": event_id})
    )

    assert response["statusCode"] == 409
    assert body_of(response)["error"]["code"] == "INVALID_STATUS_TRANSITION"


def test_list_community_events_success(table):
    event_id = _create_pending_event(table)

    response = events.list_community_events(
        "user-1", api_event(path_params={"communityId": "community-1"})
    )

    assert response["statusCode"] == 200
    events_out = body_of(response)["data"]["events"]
    assert [e["eventId"] for e in events_out] == [event_id]


def test_list_community_events_status_filter(table):
    event_id = _create_pending_event(table)

    response = events.list_community_events(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, query={"status": "CONFIRMED"}
        ),
    )

    assert body_of(response)["data"]["events"] == []
