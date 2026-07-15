from meetflow_common import dispatch

from handlers import communities, invites, join_requests, logs, members, places

# CommunityLambda (Lambda設計書v1.1 §4).
_ROUTES = {
    ("POST", "/communities"): communities.create_community,
    ("GET", "/communities"): communities.list_communities,
    ("GET", "/communities/{communityId}"): communities.get_community,
    ("PUT", "/communities/{communityId}"): communities.update_community,
    ("DELETE", "/communities/{communityId}"): communities.delete_community,
    ("PUT", "/communities/{communityId}/theme-color"): communities.update_theme_color,
    ("POST", "/communities/{communityId}/owner-transfer"): communities.transfer_owner,
    ("POST", "/communities/{communityId}/invite"): invites.create_invite,
    ("POST", "/invites/{token}/join"): invites.join_via_invite,
    ("POST", "/invites/{token}/revoke"): invites.revoke_invite,
    ("GET", "/communities/{communityId}/members"): members.list_members,
    ("PUT", "/communities/{communityId}/members/{userId}"): members.update_member,
    (
        "PUT",
        "/communities/{communityId}/members/me/display-name",
    ): members.update_my_display_name,
    (
        "GET",
        "/communities/{communityId}/join-requests",
    ): join_requests.list_join_requests,
    (
        "POST",
        "/communities/{communityId}/join-requests/{requestId}/approve",
    ): join_requests.approve_join_request,
    (
        "POST",
        "/communities/{communityId}/join-requests/{requestId}/reject",
    ): join_requests.reject_join_request,
    ("GET", "/communities/{communityId}/locations"): places.list_places,
    ("POST", "/communities/{communityId}/locations"): places.create_place,
    ("GET", "/communities/{communityId}/logs"): logs.list_community_logs,
    # URLパスは/users/だが、権限判定がコミュニティのMembership/roleに依存する
    # ためCommunityLambdaが担当する（handlers/logs.pyのget_user_logs docstring参照）。
    ("GET", "/users/{userId}/logs"): logs.get_user_logs,
}


def handler(event, context):
    return dispatch(_ROUTES, event)
