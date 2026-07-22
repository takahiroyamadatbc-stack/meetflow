from unittest.mock import patch

from meetflow_common import CONFIRMED_EVENT_CANDIDATE_AVAILABLE

from handlers import availability_subscriber

from _factories import (
    domain_event,
    put_confirmed_event,
    put_confirmed_participant,
    put_event_template,
)

_START = "2026-08-05T19:00:00.000Z"
_END = "2026-08-05T23:00:00.000Z"


def _availability_updated(*, user_id="user-9", start_time=_START, end_time=_END, game_types=None):
    return domain_event(
        "AvailabilityUpdated",
        {
            "communityId": "community-1",
            "userId": user_id,
            "startTime": start_time,
            "endTime": end_time,
            "gameTypes": game_types or [],
        },
    )


def test_notifies_when_confirmed_event_has_room(table):
    """Issue #97: 確定済み・定員未充足・時間帯/ゲーム種別一致のイベントが
    あれば、追加候補が見つかったことを通知するイベントを発行する。"""
    put_event_template(table, "community-1", "template-1", min_players=4, max_players=4)
    put_confirmed_event(table, "community-1", "event-1", template_id="template-1")
    # 定員4に対して現在3人（席が1つ空いている）。
    for uid in ("user-1", "user-2", "user-3"):
        put_confirmed_participant(
            table, uid, start_time=_START, end_time=_END, event_id="event-1"
        )

    with patch.object(availability_subscriber, "put_event") as mock_put_event:
        availability_subscriber.handle_availability_updated(_availability_updated())

    mock_put_event.assert_called_once()
    detail_type, detail = mock_put_event.call_args.args
    assert detail_type == CONFIRMED_EVENT_CANDIDATE_AVAILABLE
    assert detail == {
        "eventId": "event-1",
        "communityId": "community-1",
        "candidateUserId": "user-9",
    }


def test_skips_when_event_already_full(table):
    put_event_template(table, "community-1", "template-1", min_players=4, max_players=4)
    put_confirmed_event(table, "community-1", "event-1", template_id="template-1")
    for uid in ("user-1", "user-2", "user-3", "user-4"):
        put_confirmed_participant(
            table, uid, start_time=_START, end_time=_END, event_id="event-1"
        )

    with patch.object(availability_subscriber, "put_event") as mock_put_event:
        availability_subscriber.handle_availability_updated(_availability_updated())

    mock_put_event.assert_not_called()


def test_skips_when_user_already_a_participant(table):
    put_event_template(table, "community-1", "template-1", min_players=4, max_players=4)
    put_confirmed_event(table, "community-1", "event-1", template_id="template-1")
    put_confirmed_participant(
        table, "user-9", start_time=_START, end_time=_END, event_id="event-1"
    )

    with patch.object(availability_subscriber, "put_event") as mock_put_event:
        availability_subscriber.handle_availability_updated(
            _availability_updated(user_id="user-9")
        )

    mock_put_event.assert_not_called()


def test_skips_when_event_not_confirmed(table):
    put_event_template(table, "community-1", "template-1", min_players=4, max_players=4)
    put_confirmed_event(
        table, "community-1", "event-1", template_id="template-1", status="AWAITING_MEMBER_APPROVAL"
    )

    with patch.object(availability_subscriber, "put_event") as mock_put_event:
        availability_subscriber.handle_availability_updated(_availability_updated())

    mock_put_event.assert_not_called()


def test_skips_when_no_time_overlap(table):
    put_event_template(table, "community-1", "template-1", min_players=4, max_players=4)
    put_confirmed_event(table, "community-1", "event-1", template_id="template-1")

    with patch.object(availability_subscriber, "put_event") as mock_put_event:
        availability_subscriber.handle_availability_updated(
            _availability_updated(
                start_time="2026-09-01T10:00:00.000Z", end_time="2026-09-01T12:00:00.000Z"
            )
        )

    mock_put_event.assert_not_called()


def test_skips_when_game_type_mismatch(table):
    put_event_template(table, "community-1", "template-1", min_players=4, max_players=4)
    put_confirmed_event(table, "community-1", "event-1", template_id="template-1")

    with patch.object(availability_subscriber, "put_event") as mock_put_event:
        availability_subscriber.handle_availability_updated(
            _availability_updated(game_types=["MAHJONG3"])
        )

    mock_put_event.assert_not_called()


def test_skips_when_event_has_no_template(table):
    """Issue #56の手動作成候補由来イベントはgameType/定員の判断材料が無い
    ため対象外（安全側の判断）。"""
    put_confirmed_event(table, "community-1", "event-1", template_id=None)

    with patch.object(availability_subscriber, "put_event") as mock_put_event:
        availability_subscriber.handle_availability_updated(_availability_updated())

    mock_put_event.assert_not_called()
