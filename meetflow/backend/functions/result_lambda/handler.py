from meetflow_common import dispatch

from handlers import results

# ResultLambda (Lambda設計書v1.1 §8).
_ROUTES = {
    ("POST", "/events/{eventId}/sessions"): results.create_session,
    ("GET", "/users/{userId}/results"): results.get_user_results,
}


def handler(event, context):
    return dispatch(_ROUTES, event)
