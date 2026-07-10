from datetime import datetime, timezone


def now_iso_ms() -> str:
    """Millisecond-precision UTC ISO8601 timestamp.

    DynamoDB物理設計書v1.3 §3.15 requires `createdAt` at millisecond
    precision in UTC so that SKs built from it (`{createdAt}#{logId}` etc.)
    sort consistently across entities.
    """
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"
