from meetflow_common import dispatch

from handlers import communities, invites, join_requests, members, places

# CommunityLambda (Lambda設計書v1.1 §4).
_ROUTES = {
    ("POST", "/communities"): communities.create_community,
    ("GET", "/communities"): communities.list_communities,
    ("GET", "/communities/{communityId}"): communities.get_community,
    ("PUT", "/communities/{communityId}"): communities.update_community,
    ("POST", "/communities/{communityId}/owner-transfer"): communities.transfer_owner,
    ("POST", "/communities/{communityId}/invite"): invites.create_invite,
    ("POST", "/invites/{token}/join"): invites.join_via_invite,
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
}


def handler(event, context):
    return dispatch(_ROUTES, event)
