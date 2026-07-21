from meetflow_common import dispatch

from handlers import results

# ResultLambda (Lambda設計書v1.1 §8).
_ROUTES = {
    ("POST", "/events/{eventId}/sessions"): results.create_session,
    ("GET", "/events/{eventId}/sessions"): results.list_event_sessions,
    ("PUT", "/events/{eventId}/sessions/{sessionNo}"): results.update_session,
    ("DELETE", "/events/{eventId}/sessions/{sessionNo}"): results.delete_session,
    (
        "GET",
        "/communities/{communityId}/game-sessions/last-settings",
    ): results.get_last_game_settings,
    ("GET", "/users/{userId}/results"): results.get_user_results,
    ("GET", "/communities/{communityId}/rankings"): results.get_community_ranking,
}


def handler(event, context):
    return dispatch(_ROUTES, event)
