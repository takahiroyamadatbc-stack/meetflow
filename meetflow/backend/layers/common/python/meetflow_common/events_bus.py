import json

import boto3

# Lambda設計書v1.1 §7.3: EventBridge detail-type names every publishing/
# subscribing domain Lambda needs to agree on. Centralized here rather than
# duplicated as string literals in EventLambda/MatchingLambda/
# NotificationLambda.
EVENT_SOURCE = "meetflow.events"

EVENT_CONFIRMED = "EventConfirmed"
EVENT_CANCELLED = "EventCancelled"
CANCEL_APPROVED = "CancelApproved"
CANDIDATE_CONFLICT_DETECTED = "CandidateConflictDetected"
EVENT_STATUS_CHANGED = "EventStatusChanged"

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("events")
    return _client


def put_event(detail_type: str, detail: dict) -> None:
    """Publish a MeetFlow domain event to the account's default EventBridge
    bus (AWSシステム構成設計書v1.2 §9: used for notification/conflict-
    detection fan-out only, never to auto-trigger matching).
    """
    _get_client().put_events(
        Entries=[
            {
                "Source": EVENT_SOURCE,
                "DetailType": detail_type,
                "Detail": json.dumps(detail, ensure_ascii=False),
            }
        ]
    )
