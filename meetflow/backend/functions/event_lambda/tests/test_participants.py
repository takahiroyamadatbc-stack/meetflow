from unittest.mock import patch

from meetflow_common import EVENT_CONFIRMED, EVENT_PARTICIPANT_REJECTED

from handlers import events, participants

from _factories import api_event, body_of, put_candidate, put_membership, put_profile


def _create_confirmed_event(table, community_id="community-1", member_ids=None):
    """全員が自動承認ONの状態でconfirm_eventを呼び、AWAITING_MEMBER_APPROVAL
    を経由せず直接CONFIRMEDなイベントを作る（cancel-request系の既存テストが
    前提とする「即CONFIRMED」を維持するためのヘルパー。承認フロー自体の
    テストはtest_participants.pyの各approve/reject系テストを参照）。
    """
    member_ids = member_ids or ["user-1", "user-2", "user-3", "user-4"]
    put_membership(table, community_id, "user-1", role="OWNER")
    for uid in member_ids:
        put_profile(table, uid, auto_approve=True)
    put_candidate(table, community_id, "candidate-1", member_ids)
    create_response = events.create_event(
        "user-1", api_event(body={"candidateId": "candidate-1"})
    )
    event_id = body_of(create_response)["data"]["eventId"]
    events.confirm_event("user-1", api_event(path_params={"eventId": event_id}))
    return event_id


def _create_awaiting_approval_event(table, community_id="community-1", member_ids=None):
    """誰も自動承認をONにしていない状態でconfirm_eventを呼び、
    AWAITING_MEMBER_APPROVAL(承認待ち)なイベントを作る。approve/reject系
    テストの前提として使う。
    """
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


def test_approve_participation_success_not_last(table):
    event_id = _create_awaiting_approval_event(table)

    with patch.object(participants, "put_event") as mock_put_event:
        response = participants.approve_participation(
            "user-2", api_event(path_params={"eventId": event_id})
        )

    assert response["statusCode"] == 200
    data = body_of(response)["data"]
    assert data["status"] == "CONFIRMED"
    assert data["eventStatus"] == "AWAITING_MEMBER_APPROVAL"
    participant = table.get_item(
        Key={"PK": f"EVENT#{event_id}", "SK": "PARTICIPANT#user-2"}
    )["Item"]
    assert participant["status"] == "CONFIRMED"
    event_item = table.get_item(Key={"PK": f"EVENT#{event_id}", "SK": "METADATA"})[
        "Item"
    ]
    assert event_item["status"] == "AWAITING_MEMBER_APPROVAL"
    mock_put_event.assert_not_called()


def test_approve_participation_last_one_finalizes(table):
    event_id = _create_awaiting_approval_event(table)
    for uid in ("user-1", "user-2", "user-3"):
        participants.approve_participation(
            uid, api_event(path_params={"eventId": event_id})
        )

    with patch.object(participants, "put_event") as mock_put_event:
        response = participants.approve_participation(
            "user-4", api_event(path_params={"eventId": event_id})
        )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["eventStatus"] == "CONFIRMED"
    event_item = table.get_item(Key={"PK": f"EVENT#{event_id}", "SK": "METADATA"})[
        "Item"
    ]
    assert event_item["status"] == "CONFIRMED"
    mock_put_event.assert_called_once()
    detail_type, detail = mock_put_event.call_args[0]
    assert detail_type == EVENT_CONFIRMED
    assert set(detail["participantIds"]) == {"user-1", "user-2", "user-3", "user-4"}


def test_approve_participation_not_a_participant(table):
    event_id = _create_awaiting_approval_event(table)

    response = participants.approve_participation(
        "user-999", api_event(path_params={"eventId": event_id})
    )

    assert response["statusCode"] == 403
    assert body_of(response)["error"]["code"] == "NOT_A_PARTICIPANT"


def test_approve_participation_already_responded(table):
    event_id = _create_awaiting_approval_event(table)
    participants.approve_participation(
        "user-2", api_event(path_params={"eventId": event_id})
    )

    response = participants.approve_participation(
        "user-2", api_event(path_params={"eventId": event_id})
    )

    assert response["statusCode"] == 409
    assert body_of(response)["error"]["code"] == "PARTICIPANT_ALREADY_RESPONDED"


def test_approve_participation_after_event_cancelled(table):
    """承認待ち中に管理者がイベント全体を中止した場合、残りメンバーが承認
    してもEVENT_CONFIRMEDは発行されず、Eventはcancelledのままになること。
    自分自身の承認自体は既に成功しているため、呼び出し元には200を返す。
    """
    event_id = _create_awaiting_approval_event(table)
    for uid in ("user-1", "user-2", "user-3"):
        participants.approve_participation(
            uid, api_event(path_params={"eventId": event_id})
        )
    events.cancel_event("user-1", api_event(path_params={"eventId": event_id}))

    with patch.object(participants, "put_event") as mock_put_event:
        response = participants.approve_participation(
            "user-4", api_event(path_params={"eventId": event_id})
        )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["eventStatus"] == "CANCELLED"
    mock_put_event.assert_not_called()


def test_reject_participation_success(table):
    event_id = _create_awaiting_approval_event(table)

    with patch.object(participants, "put_event") as mock_put_event:
        response = participants.reject_participation(
            "user-2",
            api_event(
                path_params={"eventId": event_id}, body={"reason": "都合が悪い"}
            ),
        )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["status"] == "REJECTED"
    participant = table.get_item(
        Key={"PK": f"EVENT#{event_id}", "SK": "PARTICIPANT#user-2"}
    )["Item"]
    assert participant["status"] == "REJECTED"
    assert participant["rejectReason"] == "都合が悪い"
    mock_put_event.assert_called_once_with(
        EVENT_PARTICIPANT_REJECTED,
        {"eventId": event_id, "communityId": "community-1", "userId": "user-2"},
    )


def test_reject_participation_not_a_participant(table):
    event_id = _create_awaiting_approval_event(table)

    response = participants.reject_participation(
        "user-999", api_event(path_params={"eventId": event_id}, body={})
    )

    assert response["statusCode"] == 403
    assert body_of(response)["error"]["code"] == "NOT_A_PARTICIPANT"


def test_reject_participation_already_responded(table):
    event_id = _create_awaiting_approval_event(table)
    participants.reject_participation(
        "user-2", api_event(path_params={"eventId": event_id}, body={})
    )

    response = participants.reject_participation(
        "user-2", api_event(path_params={"eventId": event_id}, body={})
    )

    assert response["statusCode"] == 409
    assert body_of(response)["error"]["code"] == "PARTICIPANT_ALREADY_RESPONDED"


def test_approve_participation_after_reject_already_responded(table):
    event_id = _create_awaiting_approval_event(table)
    participants.reject_participation(
        "user-2", api_event(path_params={"eventId": event_id}, body={})
    )

    response = participants.approve_participation(
        "user-2", api_event(path_params={"eventId": event_id})
    )

    assert response["statusCode"] == 409
    assert body_of(response)["error"]["code"] == "PARTICIPANT_ALREADY_RESPONDED"


def test_reject_participation_blocks_finalize(table):
    """拒否者が残っている限り、他メンバー全員が承認してもイベントは
    自動的には本確定しない(要件定義書§17/§19のヒューマン・イン・ザ・ループ
    原則。欠員補充による自動的な代替メンバー差し込みはMVP対象外)。
    """
    event_id = _create_awaiting_approval_event(table)
    participants.reject_participation(
        "user-2", api_event(path_params={"eventId": event_id}, body={})
    )

    with patch.object(participants, "put_event") as mock_put_event:
        for uid in ("user-1", "user-3", "user-4"):
            participants.approve_participation(
                uid, api_event(path_params={"eventId": event_id})
            )

    event_item = table.get_item(Key={"PK": f"EVENT#{event_id}", "SK": "METADATA"})[
        "Item"
    ]
    assert event_item["status"] == "AWAITING_MEMBER_APPROVAL"
    mock_put_event.assert_not_called()
