from meetflow_common import dispatch

from handlers import event_subscriber, notifications, push_subscriptions

# NotificationLambda (Lambda設計書v1.2 §9).
_ROUTES = {
    ("GET", "/notifications"): notifications.list_notifications,
    ("PUT", "/notifications/{notificationId}/read"): notifications.mark_read,
    (
        "POST",
        "/users/me/push-subscriptions",
    ): push_subscriptions.register_push_subscription,
    (
        "DELETE",
        "/users/me/push-subscriptions",
    ): push_subscriptions.unregister_push_subscription,
}


def handler(event, context):
    # EventBridgeイベント（EventConfirmed/EventCancelled/CancelApproved/
    # CandidateConflictDetected、§9.1）は`detail-type`/`source`を持つが、
    # `httpMethod`は持たない。
    if "detail-type" in event:
        return event_subscriber.handle_domain_event(event)
    return dispatch(_ROUTES, event)
