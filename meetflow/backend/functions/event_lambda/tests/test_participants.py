from unittest.mock import patch

from handlers import events, participants

from _factories import api_event, body_of, put_candidate, put_membership, put_profile


def _create_confirmed_event(table, community_id="community-1", member_ids=None):
    member_ids = member_ids or ["user-1", "user-2", "user-3", "user-4"]
    put_membership(table, community_id, "user-1", role="OWNER")
    put_candidate(table, community_id, "candidate-1", member_ids)
    create_response = events.create_event(
        "user-1", api_event(body={"candidateId": "candidate-1"})
    )
    event_id = body_of(create_response)["data"]["eventId"]
    events.confirm_event("user-1", api_event(path_params={"eventId": event_id}))
    return event_id


def test_list_participants_success(table):
    event_id = _create_confirmed_event(table)

    response = participants.list_participants(
        "user-1", api_event(path_params={"eventId": event_id})
    )

    assert response["statusCode"] == 200
    participant_ids = {p["userId"] for p in body_of(response)["data"]["participants"]}
    assert participant_ids == {"user-1", "user-2", "user-3", "user-4"}


def test_list_participants_uses_display_name_when_set(table):
    event_id = _create_confirmed_event(table)
    put_membership(table, "community-1", "user-2", display_name="たか")
    put_profile(table, "user-2", nickname="たかし")

    response = participants.list_participants(
        "user-1", api_event(path_params={"eventId": event_id})
    )

    nicknames = {p["userId"]: p["nickname"] for p in body_of(response)["data"]["participants"]}
    assert nicknames["user-2"] == "たか"


def test_list_participants_event_not_found(table):
    response = participants.list_participants(
        "user-1", api_event(path_params={"eventId": "does-not-exist"})
    )

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "EVENT_NOT_FOUND"


def test_create_cancel_request_success(table):
    event_id = _create_confirmed_event(table)

    response = participants.create_cancel_request(
        "user-2",
        api_event(path_params={"eventId": event_id}, body={"reason": "都合が悪くなった"}),
    )

    assert response["statusCode"] == 201
    assert body_of(response)["data"]["status"] == "PENDING"
    participant = table.get_item(
        Key={"PK": f"EVENT#{event_id}", "SK": "PARTICIPANT#user-2"}
    )["Item"]
    assert participant["status"] == "CANCEL_REQUESTED"


def test_create_cancel_request_not_a_participant(table):
    event_id = _create_confirmed_event(table)

    response = participants.create_cancel_request(
        "user-999", api_event(path_params={"eventId": event_id}, body={})
    )

    assert response["statusCode"] == 403
    assert body_of(response)["error"]["code"] == "NOT_A_PARTICIPANT"


def test_create_cancel_request_already_pending(table):
    event_id = _create_confirmed_event(table)
    participants.create_cancel_request(
        "user-2", api_event(path_params={"eventId": event_id}, body={})
    )

    response = participants.create_cancel_request(
        "user-2", api_event(path_params={"eventId": event_id}, body={})
    )

    assert response["statusCode"] == 409
    assert body_of(response)["error"]["code"] == "CANCEL_REQUEST_ALREADY_PENDING"


def test_list_cancel_requests_success(table):
    event_id = _create_confirmed_event(table)
    participants.create_cancel_request(
        "user-2", api_event(path_params={"eventId": event_id}, body={"reason": "所用"})
    )

    response = participants.list_cancel_requests(
        "user-1", api_event(path_params={"eventId": event_id})
    )

    assert response["statusCode"] == 200
    requests = body_of(response)["data"]["cancelRequests"]
    assert [r["userId"] for r in requests] == ["user-2"]


def test_list_cancel_requests_event_not_found(table):
    response = participants.list_cancel_requests(
        "user-1", api_event(path_params={"eventId": "does-not-exist"})
    )

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "EVENT_NOT_FOUND"


def test_approve_cancel_request_success(table):
    event_id = _create_confirmed_event(table)
    participants.create_cancel_request(
        "user-2", api_event(path_params={"eventId": event_id}, body={})
    )

    with patch.object(participants, "put_event") as mock_put_event:
        response = participants.approve_cancel_request(
            "user-1",
            api_event(path_params={"eventId": event_id, "userId": "user-2"}),
        )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["status"] == "APPROVED"
    cancel_request = table.get_item(
        Key={"PK": f"EVENT#{event_id}", "SK": "CANCELREQ#user-2"}
    )["Item"]
    assert cancel_request["status"] == "APPROVED"
    participant = table.get_item(
        Key={"PK": f"EVENT#{event_id}", "SK": "PARTICIPANT#user-2"}
    )["Item"]
    assert participant["status"] == "CANCELLED"
    mock_put_event.assert_called_once()


def test_approve_cancel_request_not_found(table):
    event_id = _create_confirmed_event(table)

    response = participants.approve_cancel_request(
        "user-1",
        api_event(path_params={"eventId": event_id, "userId": "user-2"}),
    )

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "CANCEL_REQUEST_NOT_FOUND"


def test_approve_cancel_request_already_processed(table):
    event_id = _create_confirmed_event(table)
    participants.create_cancel_request(
        "user-2", api_event(path_params={"eventId": event_id}, body={})
    )
    with patch.object(participants, "put_event"):
        participants.approve_cancel_request(
            "user-1",
            api_event(path_params={"eventId": event_id, "userId": "user-2"}),
        )

    with patch.object(participants, "put_event"):
        response = participants.approve_cancel_request(
            "user-1",
            api_event(path_params={"eventId": event_id, "userId": "user-2"}),
        )

    assert response["statusCode"] == 409
    assert body_of(response)["error"]["code"] == "CANCEL_REQUEST_ALREADY_PROCESSED"
