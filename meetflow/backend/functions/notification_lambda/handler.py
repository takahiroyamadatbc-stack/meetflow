from meetflow_common import dispatch

from handlers import event_subscriber, notifications

# NotificationLambda (Lambda設計書v1.1 §9).
_ROUTES = {
    ("GET", "/notifications"): notifications.list_notifications,
    ("PUT", "/notifications/{notificationId}/read"): notifications.mark_read,
}


def handler(event, context):
    # EventBridge events (EventConfirmed/EventCancelled/CancelApproved/
    # CandidateConflictDetected, §9.1) carry `detail-type`/`source`, never
    # `httpMethod`.
    if "detail-type" in event:
        return event_subscriber.handle_domain_event(event)
    return dispatch(_ROUTES, event)
