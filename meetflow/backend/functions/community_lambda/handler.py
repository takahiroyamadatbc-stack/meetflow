from meetflow_common import dispatch

from handlers import communities, invites, join_requests, logs, members, places

# CommunityLambda (Lambda設計書v1.1 §4).
_ROUTES = {
    ("POST", "/communities"): communities.create_community,
    ("GET", "/communities"): communities.list_communities,
    ("PUT", "/communities/order"): communities.reorder_communities,
    ("GET", "/communities/{communityId}"): communities.get_community,
    ("PUT", "/communities/{communityId}"): communities.update_community,
    ("DELETE", "/communities/{communityId}"): communities.delete_community,
    ("PUT", "/communities/{communityId}/theme-color"): communities.update_theme_color,
    (
        "PUT",
        "/communities/{communityId}/ranking-settings",
    ): communities.update_ranking_settings,
    (
        "POST",
        "/communities/{communityId}/icon/upload-url",
    ): communities.create_icon_upload_url,
    ("POST", "/communities/{communityId}/owner-transfer"): communities.transfer_owner,
    ("POST", "/communities/{communityId}/invite"): invites.create_invite,
    ("GET", "/invites/{token}"): invites.get_invite_preview,
    ("POST", "/invites/{token}/join"): invites.join_via_invite,
    ("POST", "/invites/{token}/revoke"): invites.revoke_invite,
    ("GET", "/communities/{communityId}/members"): members.list_members,
    ("PUT", "/communities/{communityId}/members/{userId}"): members.update_member,
    (
        "POST",
        "/communities/{communityId}/members/me/leave",
    ): members.leave_community,
    (
        "PUT",
        "/communities/{communityId}/members/me/display-name",
    ): members.update_my_display_name,
    (
        "PUT",
        "/communities/{communityId}/members/me/auto-approve",
    ): members.update_my_auto_approve,
    (
        "PUT",
        "/communities/{communityId}/members/me/frequency-limit",
    ): members.update_my_frequency_limit,
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
