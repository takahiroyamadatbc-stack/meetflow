from meetflow_common import dispatch

from handlers import availability, availability_requests

# AvailabilityLambda (Lambda設計書v1.2 §5).
_ROUTES = {
    (
        "POST",
        "/communities/{communityId}/availability",
    ): availability.create_availability,
    (
        "POST",
        "/communities/{communityId}/availability/batch",
    ): availability.create_availability_batch,
    (
        "GET",
        "/communities/{communityId}/availability",
    ): availability.list_availability,
    ("PUT", "/availability/{availabilityId}"): availability.update_availability,
    ("DELETE", "/availability/{availabilityId}"): availability.delete_availability,
    (
        "POST",
        "/communities/{communityId}/availability-requests",
    ): availability_requests.create_availability_request,
    (
        "GET",
        "/communities/{communityId}/availability-requests",
    ): availability_requests.list_availability_requests,
    (
        "GET",
        "/communities/{communityId}/availability-requests/{requestId}/pending-members",
    ): availability_requests.list_pending_members,
}


def handler(event, context):
    return dispatch(_ROUTES, event)
