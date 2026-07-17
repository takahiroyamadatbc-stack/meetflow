from meetflow_common import dispatch

from handlers import events, participants

# EventLambda (Lambda設計書v1.1 §7).
_ROUTES = {
    ("POST", "/events"): events.create_event,
    ("GET", "/users/me/events"): events.list_my_events,
    ("GET", "/events/{eventId}"): events.get_event,
    ("POST", "/events/{eventId}/confirm"): events.confirm_event,
    ("POST", "/events/{eventId}/cancel"): events.cancel_event,
    ("GET", "/communities/{communityId}/events"): events.list_community_events,
    ("GET", "/events/{eventId}/participants"): participants.list_participants,
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
    return dispatch(_ROUTES, event)
