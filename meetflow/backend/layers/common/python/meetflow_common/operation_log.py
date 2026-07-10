import secrets
import time

from .dynamodb import get_table
from .time_utils import now_iso_ms

# ~2 years, per DynamoDB物理設計書v1.3 §3.15's suggestion ("例えば2年経過後
# に自動削除する"). Data needed for longer-term analysis is expected to be
# exported to S3 before TTL deletes it (AWSシステム構成設計書v1.2 §17).
_DEFAULT_TTL_DAYS = 730


def _generate_log_id() -> str:
    """Time-sortable log id: zero-padded epoch-ms + random suffix.

    Not a full ULID (Crockford base32) implementation -- avoids pulling in
    an extra dependency for an MVP-scale personal project. It sorts
    identically to a real ULID for this table's access patterns (SK begins
    with a lexicographically sortable timestamp), so it can be swapped for a
    real `ulid` library later without a schema change (物理設計書v1.3 §3.15).
    """
    epoch_ms = int(time.time() * 1000)
    return f"{epoch_ms:013d}{secrets.token_hex(5)}"


def write_operation_log(
    *,
    action: str,
    user_id: str,
    community_id: str = None,
    target_type: str = None,
    target_id: str = None,
    before: dict = None,
    after: dict = None,
    ttl_days: int = _DEFAULT_TTL_DAYS,
) -> None:
    """F-1301 / DynamoDB物理設計書v1.3 §3.15 OperationLog writer, shared by
    every domain Lambda (Lambda設計書v1.1 §12.1).

    `community_id=None` covers operations not tied to a community (e.g.
    login, profile update) -- stored under `LOG#GLOBAL#{userId}` so they are
    excluded from community-scoped log aggregation, per §3.15.
    """
    created_at = now_iso_ms()
    log_id = _generate_log_id()
    pk = f"LOG#{community_id}" if community_id else f"LOG#GLOBAL#{user_id}"

    item = {
        "PK": pk,
        "SK": f"{created_at}#{log_id}",
        "GSI1PK": f"USER#{user_id}",
        "GSI1SK": f"LOG#{created_at}#{log_id}",
        "action": action,
        "createdAt": created_at,
        "ttl": int(time.time()) + ttl_days * 86400,
    }
    if target_type:
        item["targetType"] = target_type
    if target_id:
        item["targetId"] = target_id
    if before:
        item["before"] = before
    if after:
        item["after"] = after

    get_table().put_item(Item=item)
