from meetflow_common import (
    count_confirmed_events_in_period,
    get_frequency_limit,
    period_bounds,
    resolve_frequency_limit,
)

from _factories import put_membership, put_profile


def test_resolve_frequency_limit_prefers_membership_value():
    assert resolve_frequency_limit(
        {"frequencyLimitCount": 1, "frequencyLimitPeriod": "WEEK"},
        {"frequencyLimitCount": 5, "frequencyLimitPeriod": "MONTH"},
    ) == (1, "WEEK")


def test_resolve_frequency_limit_falls_back_to_user_default_when_unset():
    assert resolve_frequency_limit(
        {}, {"frequencyLimitCount": 3, "frequencyLimitPeriod": "MONTH"}
    ) == (3, "MONTH")


def test_resolve_frequency_limit_none_when_both_unset():
    assert resolve_frequency_limit({}, {}) is None
    assert resolve_frequency_limit(None, None) is None


def test_get_frequency_limit_reads_membership_override(table):
    put_membership(table, "community-1", "user-1", frequency_limit_count=1, frequency_limit_period="WEEK")
    put_profile(table, "user-1", frequency_limit_count=5, frequency_limit_period="MONTH")
    assert get_frequency_limit(table, "community-1", "user-1") == (1, "WEEK")


def test_get_frequency_limit_falls_back_to_profile(table):
    put_membership(table, "community-1", "user-1")
    put_profile(table, "user-1", frequency_limit_count=2, frequency_limit_period="MONTH")
    assert get_frequency_limit(table, "community-1", "user-1") == (2, "MONTH")


def test_get_frequency_limit_none_when_unset(table):
    put_membership(table, "community-1", "user-1")
    put_profile(table, "user-1")
    assert get_frequency_limit(table, "community-1", "user-1") is None


def test_period_bounds_week():
    start, end = period_bounds("2026-08-08T00:00:00.000Z", "WEEK")
    assert end == "2026-08-08T00:00:00.000Z"
    assert start == "2026-08-01T00:00:00.000Z"


def test_period_bounds_month():
    start, end = period_bounds("2026-08-08T00:00:00.000Z", "MONTH")
    assert end == "2026-08-08T00:00:00.000Z"
    assert start == "2026-07-09T00:00:00.000Z"


def _put_participant(table, user_id, *, start_time, community_genre, status="CONFIRMED", event_id="event-1"):
    table.put_item(
        Item={
            "PK": f"EVENT#{event_id}",
            "SK": f"PARTICIPANT#{user_id}",
            "GSI1PK": f"USER#{user_id}",
            "GSI1SK": f"PARTICIPANT#{start_time}#{event_id}",
            "status": status,
            "startTime": start_time,
            "endTime": start_time,
            "communityGenre": community_genre,
        }
    )


def test_count_confirmed_events_in_period_matches_genre_and_status(table):
    _put_participant(table, "user-1", start_time="2026-08-05T19:00:00.000Z", community_genre="麻雀")
    assert (
        count_confirmed_events_in_period(
            table, "user-1", "麻雀", "2026-08-01T00:00:00.000Z", "2026-08-08T00:00:00.000Z"
        )
        == 1
    )


def test_count_confirmed_events_in_period_ignores_other_genre(table):
    _put_participant(table, "user-1", start_time="2026-08-05T19:00:00.000Z", community_genre="ボードゲーム")
    assert (
        count_confirmed_events_in_period(
            table, "user-1", "麻雀", "2026-08-01T00:00:00.000Z", "2026-08-08T00:00:00.000Z"
        )
        == 0
    )


def test_count_confirmed_events_in_period_ignores_out_of_range(table):
    _put_participant(table, "user-1", start_time="2026-07-01T19:00:00.000Z", community_genre="麻雀")
    assert (
        count_confirmed_events_in_period(
            table, "user-1", "麻雀", "2026-08-01T00:00:00.000Z", "2026-08-08T00:00:00.000Z"
        )
        == 0
    )


def test_count_confirmed_events_in_period_ignores_non_confirmed_status(table):
    _put_participant(
        table,
        "user-1",
        start_time="2026-08-05T19:00:00.000Z",
        community_genre="麻雀",
        status="AWAITING_APPROVAL",
    )
    assert (
        count_confirmed_events_in_period(
            table, "user-1", "麻雀", "2026-08-01T00:00:00.000Z", "2026-08-08T00:00:00.000Z"
        )
        == 0
    )
