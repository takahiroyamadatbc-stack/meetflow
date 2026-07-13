import os

from meetflow_common import (
    error_response,
    generate_invite_token,
    get_table,
    now_iso_ms,
    parse_body,
    require_membership,
    success_response,
    write_operation_log,
)

_DEFAULT_INVITE_BASE_URL = "https://meetflow.jp/invite"


def create_invite(user_id, event):
    """F-102 (API設計書v1.4 §4.3): OWNER/ADMIN issue an invite URL, keyed
    directly by an unguessable token (DynamoDB物理設計書v1.3 §3.4) so
    joining is a single GetItem.
    """
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    token = generate_invite_token()
    table.put_item(
        Item={
            "PK": f"INVITE#{token}",
            "SK": "METADATA",
            "communityId": community_id,
            "createdBy": user_id,
            "revoked": False,
            "createdAt": now_iso_ms(),
        }
    )
    write_operation_log(
        action="CREATE_INVITE",
        user_id=user_id,
        community_id=community_id,
        target_type="Invite",
        target_id=token,
    )
    base_url = os.environ.get("INVITE_BASE_URL", _DEFAULT_INVITE_BASE_URL)
    return success_response({"url": f"{base_url}/{token}"}, status_code=201)


def join_via_invite(user_id, event):
    """F-103 (API設計書v1.4 §4.4): branches on the community's
    `memberApprovalRequired` flag (要件定義書v1.2 §10.1) between immediate
    Membership creation and a PENDING JoinRequest.
    """
    token = event["pathParameters"]["token"]
    body = parse_body(event)
    message = body.get("message")

    table = get_table()
    invite = table.get_item(Key={"PK": f"INVITE#{token}", "SK": "METADATA"}).get("Item")
    if invite is None:
        return error_response("INVITE_NOT_FOUND", "招待URLが存在しません", status_code=404)
    if invite.get("revoked"):
        return error_response(
            "INVITE_REVOKED", "招待URLが無効化されています", status_code=410
        )
    # expiresAt (DynamoDB物理設計書v1.3 §3.4) is a future/optional field for
    # time-limited invites; MVP always creates non-expiring invites so it's
    # not enforced here yet.

    community_id = invite["communityId"]
    if table.get_item(
        Key={"PK": f"COMMUNITY#{community_id}", "SK": f"MEMBER#{user_id}"}
    ).get("Item"):
        return error_response(
            "ALREADY_MEMBER", "既にこのコミュニティのメンバーです", status_code=409
        )

    community = table.get_item(
        Key={"PK": f"COMMUNITY#{community_id}", "SK": "METADATA"}
    ).get("Item")
    if community is None:
        return error_response("COMMUNITY_NOT_FOUND", "コミュニティが見つかりません")

    if community.get("memberApprovalRequired"):
        return _create_join_request(table, community_id, user_id, message)
    return _add_member_immediately(table, community_id, user_id)


def _create_join_request(table, community_id, user_id, message):
    existing = table.get_item(
        Key={"PK": f"COMMUNITY#{community_id}", "SK": f"JOINREQ#{user_id}"}
    ).get("Item")
    if existing is not None and existing.get("status") == "PENDING":
        return error_response(
            "JOIN_REQUEST_ALREADY_PENDING",
            "既に参加リクエスト済みです",
            status_code=409,
        )

    item = {
        "PK": f"COMMUNITY#{community_id}",
        "SK": f"JOINREQ#{user_id}",
        "GSI1PK": f"USER#{user_id}",
        "GSI1SK": f"JOINREQ#{community_id}",
        "status": "PENDING",
        "requestedAt": now_iso_ms(),
    }
    if message:
        item["message"] = message
    table.put_item(Item=item)
    write_operation_log(
        action="CREATE_JOIN_REQUEST",
        user_id=user_id,
        community_id=community_id,
        target_type="JoinRequest",
        target_id=user_id,
    )
    return success_response(
        {"communityId": community_id, "status": "PENDING"}, status_code=201
    )


def _add_member_immediately(table, community_id, user_id):
    table.put_item(
        Item={
            "PK": f"COMMUNITY#{community_id}",
            "SK": f"MEMBER#{user_id}",
            "GSI1PK": f"USER#{user_id}",
            "GSI1SK": f"COMMUNITY#{community_id}",
            "role": "MEMBER",
            "status": "ACTIVE",
            "joinedAt": now_iso_ms(),
        }
    )
    write_operation_log(
        action="ADD_MEMBER",
        user_id=user_id,
        community_id=community_id,
        target_type="Membership",
        target_id=user_id,
    )
    return success_response(
        {"communityId": community_id, "status": "ACTIVE"}, status_code=201
    )
