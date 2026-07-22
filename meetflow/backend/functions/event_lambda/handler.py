from meetflow_common import dispatch

from handlers import availability_subscriber, events, participants

# EventLambda (Lambda設計書v1.1 §7).
_ROUTES = {
    ("POST", "/events"): events.create_event,
    ("GET", "/users/me/events"): events.list_my_events,
    ("GET", "/events/{eventId}"): events.get_event,
    ("PUT", "/events/{eventId}"): events.update_event,
    ("POST", "/events/{eventId}/confirm"): events.confirm_event,
    ("POST", "/events/{eventId}/cancel"): events.cancel_event,
    ("POST", "/events/{eventId}/complete"): events.complete_event,
    ("POST", "/events/{eventId}/reopen"): events.reopen_event,
    ("GET", "/communities/{communityId}/events"): events.list_community_events,
    ("GET", "/events/{eventId}/participants"): participants.list_participants,
    ("POST", "/events/{eventId}/participants"): participants.add_participant,
    (
        "POST",
        "/events/{eventId}/participants/{userId}/remove",
    ): participants.remove_participant,
    (
        "GET",
        "/events/{eventId}/cancel-requests",
    ): participants.list_cancel_requests,
    (
        "POST",
        "/events/{eventId}/cancel-request",
    ): participants.create_cancel_request,
    (
        "POST",
        "/events/{eventId}/cancel-requests/{userId}/approve",
    ): participants.approve_cancel_request,
    (
        "POST",
        "/events/{eventId}/participants/me/approve",
    ): participants.approve_participation,
    (
        "POST",
        "/events/{eventId}/participants/me/reject",
    ): participants.reject_participation,
}


def handler(event, context):
    # EventBridgeイベント（Issue #97: `AvailabilityUpdated`購読）は
    # `detail-type`/`source`を持つが、`httpMethod`は持たない
    # （matching_lambda/handler.pyの`EventConfirmed`購読と同じ判定パターン）。
    if "detail-type" in event:
        return availability_subscriber.handle_availability_updated(event)
    return dispatch(_ROUTES, event)
