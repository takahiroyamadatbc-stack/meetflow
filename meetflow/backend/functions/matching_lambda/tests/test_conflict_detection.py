from unittest.mock import patch

from meetflow_common import EVENT_CONFIRMED

from handlers import conflict_detection

from _factories import domain_event, put_candidate_member


def test_handle_event_confirmed_flags_overlapping_pending_candidates(table):
    put_candidate_member(
        table,
        "community-1",
        "candidate-1",
        "user-1",
        start_time="2026-08-05T10:00:00.000Z",
        end_time="2026-08-05T14:00:00.000Z",
        status="PENDING",
    )

    with patch.object(conflict_detection, "put_event") as mock_put_event:
        conflict_detection.handle_event_confirmed(
            domain_event(
                EVENT_CONFIRMED,
                {
                    "eventId": "event-1",
                    "communityId": "community-2",
                    "participantIds": ["user-1"],
                    "startTime": "2026-08-05T09:00:00.000Z",
                    "endTime": "2026-08-05T15:00:00.000Z",
                },
            )
        )

    item = table.get_item(
        Key={
            "PK": "COMMUNITY#community-1",
            "SK": "CANDIDATE#candidate-1#MEMBER#user-1",
        }
    )["Item"]
    assert item["conflictWarning"] is True
    mock_put_event.assert_called_once()
    assert mock_put_event.call_args[0][1] == {"communityId": "community-1"}


def test_handle_event_confirmed_ignores_non_pending_candidates(table):
    put_candidate_member(
        table,
        "community-1",
        "candidate-1",
        "user-1",
        start_time="2026-08-05T10:00:00.000Z",
        end_time="2026-08-05T14:00:00.000Z",
        status="CONFIRMED",
    )

    with patch.object(conflict_detection, "put_event") as mock_put_event:
        conflict_detection.handle_event_confirmed(
            domain_event(
                EVENT_CONFIRMED,
                {
                    "eventId": "event-1",
                    "communityId": "community-2",
                    "participantIds": ["user-1"],
                    "startTime": "2026-08-05T09:00:00.000Z",
                    "endTime": "2026-08-05T15:00:00.000Z",
                },
            )
        )

    item = table.get_item(
        Key={
            "PK": "COMMUNITY#community-1",
            "SK": "CANDIDATE#candidate-1#MEMBER#user-1",
        }
    )["Item"]
    assert item["conflictWarning"] is False
    mock_put_event.assert_not_called()


def test_handle_event_confirmed_no_op_on_incomplete_detail(table):
    with patch.object(conflict_detection, "put_event") as mock_put_event:
        conflict_detection.handle_event_confirmed(
            domain_event(EVENT_CONFIRMED, {"eventId": "event-1", "participantIds": []})
        )

    mock_put_event.assert_not_called()
