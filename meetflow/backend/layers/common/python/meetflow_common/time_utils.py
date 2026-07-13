from datetime import datetime, timedelta, timezone


def now_iso_ms() -> str:
    """Millisecond-precision UTC ISO8601 timestamp.

    DynamoDB物理設計書v1.3 §3.15 requires `createdAt` at millisecond
    precision in UTC so that SKs built from it (`{createdAt}#{logId}` etc.)
    sort consistently across entities.
    """
    return _format(datetime.now(timezone.utc))


def add_days_iso(base_iso: str, days: int) -> str:
    """Add `days` (may be negative) to an ISO8601 timestamp, returning the
    same millisecond-precision UTC format as `now_iso_ms` -- used to build
    time-range query bounds (e.g. MatchingLambda's search window, fairness
    window).
    """
    dt = datetime.fromisoformat(base_iso.replace("Z", "+00:00")) + timedelta(days=days)
    return _format(dt)


def _format(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"
