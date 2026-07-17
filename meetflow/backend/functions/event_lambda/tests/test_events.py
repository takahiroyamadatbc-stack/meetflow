from unittest.mock import patch

from meetflow_common import EVENT_AWAITING_APPROVAL, EVENT_CONFIRMED

from handlers import events

from _factories import (
    api_event,
    body_of,
    put_availability,
    put_candidate,
    put_community,
    put_confirmed_participant,
    put_event_status,
    put_membership,
    put_place,
    put_profile,
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
    """Issue #10: 候補メンバーが誰も自動承認をONにしていない場合、confirm_event
    (仮確定)はAWAITING_MEMBER_APPROVALへ遷移し、Participant行もAWAITING_APPROVAL
    になる。本確定(CONFIRMED)はparticipants.approve_participation経由で全員が
    個別に承認した時点で初めて起きる。
    """
    event_id = _create_pending_event(table)

    response = events.confirm_event(
        "user-1", api_event(path_params={"eventId": event_id})
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["status"] == "AWAITING_MEMBER_APPROVAL"
    for uid in ("user-1", "user-2", "user-3", "user-4"):
        participant = table.get_item(
            Key={"PK": f"EVENT#{event_id}", "SK": f"PARTICIPANT#{uid}"}
        )["Item"]
        assert participant["status"] == "AWAITING_APPROVAL"


def test_confirm_event_all_auto_approve_finalizes_immediately(table):
    """候補メンバー全員が自動承認ONの場合、AWAITING_MEMBER_APPROVALを経由
    せず直接CONFIRMEDになり、EventConfirmedのみが発行される
    （EventAwaitingApprovalは発行されない -- 不要な中間通知を作らない）。
    """
    event_id = _create_pending_event(table)
    for uid in ("user-1", "user-2", "user-3", "user-4"):
        put_profile(table, uid, auto_approve=True)

    with patch.object(events, "put_event") as mock_put_event:
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
        assert participant["autoApproved"] is True

    mock_put_event.assert_called_once()
    detail_type = mock_put_event.call_args[0][0]
    assert detail_type == EVENT_CONFIRMED


def test_confirm_event_mixed_auto_approve(table):
    """一部のメンバーのみ自動承認ONの場合、AWAITING_MEMBER_APPROVALへ遷移
    し、自動承認ONのメンバーだけCONFIRMED・それ以外はAWAITING_APPROVALに
    なる。EventAwaitingApprovalのawaitingUserIdsには自動承認OFFのメンバー
    のみが含まれる。
    """
    event_id = _create_pending_event(table)
    put_profile(table, "user-1", auto_approve=True)
    put_profile(table, "user-2", auto_approve=True)
    # user-3, user-4は自動承認未設定（既定false）

    with patch.object(events, "put_event") as mock_put_event:
        response = events.confirm_event(
            "user-1", api_event(path_params={"eventId": event_id})
        )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["status"] == "AWAITING_MEMBER_APPROVAL"

    for uid in ("user-1", "user-2"):
        participant = table.get_item(
            Key={"PK": f"EVENT#{event_id}", "SK": f"PARTICIPANT#{uid}"}
        )["Item"]
        assert participant["status"] == "CONFIRMED"
        assert participant["autoApproved"] is True
    for uid in ("user-3", "user-4"):
        participant = table.get_item(
            Key={"PK": f"EVENT#{event_id}", "SK": f"PARTICIPANT#{uid}"}
        )["Item"]
        assert participant["status"] == "AWAITING_APPROVAL"

    mock_put_event.assert_called_once()
    detail_type, detail = mock_put_event.call_args[0]
    assert detail_type == EVENT_AWAITING_APPROVAL
    assert set(detail["awaitingUserIds"]) == {"user-3", "user-4"}


def test_confirm_event_membership_auto_approve_overrides_user_default(table):
    """自動承認の実効値解決は displayName/frequencyLimit と同じ
    「Membership優先・Userフォールバック」パターンに従うこと。
    """
    event_id = _create_pending_event(table)
    put_membership(table, "community-1", "user-2")
    put_profile(table, "user-2", auto_approve=True)
    table.update_item(
        Key={"PK": "COMMUNITY#community-1", "SK": "MEMBER#user-2"},
        UpdateExpression="SET autoApprove = :v",
        ExpressionAttributeValues={":v": False},
    )

    response = events.confirm_event(
        "user-1", api_event(path_params={"eventId": event_id})
    )

    assert body_of(response)["data"]["status"] == "AWAITING_MEMBER_APPROVAL"
    participant = table.get_item(
        Key={"PK": f"EVENT#{event_id}", "SK": "PARTICIPANT#user-2"}
    )["Item"]
    assert participant["status"] == "AWAITING_APPROVAL"


def test_confirm_event_blocks_on_awaiting_approval_conflict(table):
    """他イベントの参加者が「承認待ち」(AWAITING_APPROVAL)状態でも
    ダブルブッキングとしてブロックされること。仮確定の時点で参加者の時間枠
    は事実上「予約済み」になるため、判定対象をCONFIRMEDだけでなく
    AWAITING_APPROVALにも広げている（RESERVED_PARTICIPANT_STATUSES）。
    """
    put_membership(table, "community-1", "user-1", role="OWNER")
    start_time, end_time = put_candidate(
        table, "community-1", "candidate-1", ["user-1", "user-2"]
    )
    put_confirmed_participant(
        table,
        "user-2",
        start_time=start_time,
        end_time=end_time,
        status="AWAITING_APPROVAL",
    )
    create_response = events.create_event(
        "user-1", api_event(body={"candidateId": "candidate-1"})
    )
    event_id = body_of(create_response)["data"]["eventId"]

    response = events.confirm_event(
        "user-1", api_event(path_params={"eventId": event_id})
    )

    assert response["statusCode"] == 409
    assert body_of(response)["error"]["code"] == "PARTICIPANT_SCHEDULE_CONFLICT"


def test_confirm_event_copies_community_genre_to_participant(table):
    """Issue #19: 仮確定時、Community METADATAのgenreがParticipant.
    communityGenreへ非正規化コピーされること(参加頻度上限のジャンル横断
    カウントで使用)。
    """
    put_community(table, "community-1", genre="麻雀")
    event_id = _create_pending_event(table)

    response = events.confirm_event(
        "user-1", api_event(path_params={"eventId": event_id})
    )

    assert response["statusCode"] == 200
    for uid in ("user-1", "user-2", "user-3", "user-4"):
        participant = table.get_item(
            Key={"PK": f"EVENT#{event_id}", "SK": f"PARTICIPANT#{uid}"}
        )["Item"]
        assert participant["communityGenre"] == "麻雀"


def test_confirm_event_deletes_overlapping_availability(table):
    """#14: イベント確定時、候補元となった参加者の空き予定のうち、確定した
    イベント時間帯と重複するものが削除されること。マッチングは複数人の
    交差区間をイベント時間として採用するため、本人の元の登録（例:
    18:00-23:00）がイベント時間帯（19:00-23:00）より広いケースも扱う。
    """
    put_membership(table, "community-1", "user-1", role="OWNER")
    start_time, end_time = put_candidate(
        table, "community-1", "candidate-1", ["user-1", "user-2"]
    )
    put_availability(
        table,
        "community-1",
        "user-1",
        "avail-overlap",
        start_time="2026-08-05T18:00:00.000Z",
        end_time="2026-08-05T23:00:00.000Z",
    )
    put_availability(
        table,
        "community-1",
        "user-2",
        "avail-non-overlap",
        start_time="2026-08-06T10:00:00.000Z",
        end_time="2026-08-06T12:00:00.000Z",
    )
    create_response = events.create_event(
        "user-1", api_event(body={"candidateId": "candidate-1"})
    )
    event_id = body_of(create_response)["data"]["eventId"]

    response = events.confirm_event(
        "user-1", api_event(path_params={"eventId": event_id})
    )

    assert response["statusCode"] == 200
    overlap_item = table.get_item(
        Key={
            "PK": "COMMUNITY#community-1",
            "SK": "AVAIL#2026-08-05T18:00:00.000Z#avail-overlap",
        }
    ).get("Item")
    assert overlap_item is None

    non_overlap_item = table.get_item(
        Key={
            "PK": "COMMUNITY#community-1",
            "SK": "AVAIL#2026-08-06T10:00:00.000Z#avail-non-overlap",
        }
    ).get("Item")
    assert non_overlap_item is not None


def test_confirm_event_already_confirmed(table):
    event_id = _create_pending_event(table)
    put_event_status(table, event_id, "CONFIRMED")

    response = events.confirm_event(
        "user-1", api_event(path_params={"eventId": event_id})
    )

    assert response["statusCode"] == 409
    assert body_of(response)["error"]["code"] == "EVENT_ALREADY_CONFIRMED"


def test_confirm_event_awaiting_member_approval_blocks_reconfirm(table):
    """仮確定後(AWAITING_MEMBER_APPROVAL)は、全員承認が完了するまで
    confirm_eventを再度呼んでも本確定はされない(INVALID_STATUS_TRANSITION)。
    本確定はparticipants.approve_participation経由でのみ行われる。
    """
    event_id = _create_pending_event(table)
    events.confirm_event("user-1", api_event(path_params={"eventId": event_id}))

    response = events.confirm_event(
        "user-1", api_event(path_params={"eventId": event_id})
    )

    assert response["statusCode"] == 409
    assert body_of(response)["error"]["code"] == "INVALID_STATUS_TRANSITION"


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


def test_cancel_event_reopens_candidate_for_reuse(table):
    """#15: イベント全体を中止したら、元のMatchCandidateがPENDINGへ戻り、
    同じ候補から再度イベントを作成できること（CANDIDATE_ALREADY_USEDで
    永久にブロックされていた回帰バグの再発防止）。
    """
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_candidate(table, "community-1", "candidate-1", ["user-1", "user-2"])
    create_response = events.create_event(
        "user-1", api_event(body={"candidateId": "candidate-1"})
    )
    event_id = body_of(create_response)["data"]["eventId"]

    response = events.cancel_event(
        "user-1", api_event(path_params={"eventId": event_id})
    )
    assert response["statusCode"] == 200

    candidate = table.get_item(
        Key={
            "PK": "COMMUNITY#community-1",
            "SK": "CANDIDATE#2026-08-05T19:00:00.000Z#candidate-1",
        }
    )["Item"]
    assert candidate["status"] == "PENDING"
    for uid in ("user-1", "user-2"):
        candidate_member = table.get_item(
            Key={
                "PK": "COMMUNITY#community-1",
                "SK": f"CANDIDATE#candidate-1#MEMBER#{uid}",
            }
        )["Item"]
        assert candidate_member["status"] == "PENDING"

    retry_response = events.create_event(
        "user-1", api_event(body={"candidateId": "candidate-1"})
    )
    assert retry_response["statusCode"] == 201


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


def test_list_my_events_success(table):
    """#12: 予定タブのカレンダー表示用に、自分が参加者の確定イベントを
    コミュニティ横断で取得できること。"""
    event_id = _create_pending_event(table)
    for uid in ("user-1", "user-2", "user-3", "user-4"):
        put_profile(table, uid, auto_approve=True)
    events.confirm_event("user-1", api_event(path_params={"eventId": event_id}))

    response = events.list_my_events("user-1", api_event())

    assert response["statusCode"] == 200
    my_events = body_of(response)["data"]["events"]
    assert len(my_events) == 1
    assert my_events[0]["eventId"] == event_id
    assert my_events[0]["communityId"] == "community-1"


def test_list_my_events_excludes_pending_approval(table):
    event_id = _create_pending_event(table)

    response = events.list_my_events("user-1", api_event(path_params={"eventId": event_id}))

    assert body_of(response)["data"]["events"] == []


def test_list_my_events_excludes_cancelled_event(table):
    """#15と関連: イベント全体が中止された場合、Participant行自体は残る
    ため、Event側のstatusも見て除外する必要がある。"""
    event_id = _create_pending_event(table)
    for uid in ("user-1", "user-2", "user-3", "user-4"):
        put_profile(table, uid, auto_approve=True)
    events.confirm_event("user-1", api_event(path_params={"eventId": event_id}))
    events.cancel_event("user-1", api_event(path_params={"eventId": event_id}))

    response = events.list_my_events("user-1", api_event())

    assert body_of(response)["data"]["events"] == []


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
