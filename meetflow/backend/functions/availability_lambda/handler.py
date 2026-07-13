from meetflow_common import dispatch

from handlers import availability

# AvailabilityLambda (Lambda設計書v1.1 §5).
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
}


def handler(event, context):
    return dispatch(_ROUTES, event)
