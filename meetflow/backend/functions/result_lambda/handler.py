from meetflow_common import dispatch

from handlers import chip_records, results

# ResultLambda (Lambda設計書v1.1 §8).
_ROUTES = {
    ("POST", "/events/{eventId}/sessions"): results.create_session,
    ("GET", "/events/{eventId}/sessions"): results.list_event_sessions,
    ("PUT", "/events/{eventId}/sessions/{sessionNo}"): results.update_session,
    ("DELETE", "/events/{eventId}/sessions/{sessionNo}"): results.delete_session,
    # Issue #116: 半荘に紐付けないチップ記録
    ("POST", "/events/{eventId}/chip-records"): chip_records.create_chip_record,
    ("GET", "/events/{eventId}/chip-records"): chip_records.list_chip_records,
    (
        "PUT",
        "/events/{eventId}/chip-records/{recordNo}",
    ): chip_records.update_chip_record,
    (
        "DELETE",
        "/events/{eventId}/chip-records/{recordNo}",
    ): chip_records.delete_chip_record,
    (
        "GET",
        "/communities/{communityId}/game-sessions/last-settings",
    ): results.get_last_game_settings,
    ("GET", "/users/{userId}/results"): results.get_user_results,
    ("GET", "/communities/{communityId}/rankings"): results.get_community_ranking,
}


def handler(event, context):
    return dispatch(_ROUTES, event)
