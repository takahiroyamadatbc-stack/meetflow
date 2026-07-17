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
    """F-102（API設計書v1.13 §4.3）: コミュニティの全メンバーが招待URLを
    発行できる（Issue #22でOWNER/ADMIN限定から開放）。推測不可能な
    トークンを直接キーとする（DynamoDB物理設計書v1.11 §3.4）ため、
    参加処理はGetItem1回で済む。発行時点の発行者ロールを`createdByRole`
    としてスナップショット保持し、`join_via_invite`の承認要否分岐
    （MEMBER発行分は強制的に承認制）に使う。
    """
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    membership = require_membership(table, community_id, user_id)

    token = generate_invite_token()
    table.put_item(
        Item={
            "PK": f"INVITE#{token}",
            "SK": "METADATA",
            "communityId": community_id,
            "createdBy": user_id,
            "createdByRole": membership.get("role"),
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


def revoke_invite(user_id, event):
    """POST /invites/{token}/revoke（API設計書v1.13 §4.3b）: OWNER/ADMIN、
    または発行者本人（`invite.createdBy == user_id`）が発行済み招待URLを
    無効化する（Issue #22で発行者本人にも開放）。発行者本人であれば現在
    の所属状況・ロールを問わず許可する。それ以外は招待発行と同じく
    コミュニティ単位の権限（require_membership）で判定するため、tokenから
    Invite.communityIdを引いた上でチェックする。

    NotificationLambdaのプッシュ購読解除（Lambda設計書v1.2 §9.2）と同様、
    既に無効化済みの招待に対する再実行はエラーにせず冪等に成功として扱う。
    """
    token = event["pathParameters"]["token"]
    table = get_table()
    invite = table.get_item(Key={"PK": f"INVITE#{token}", "SK": "METADATA"}).get("Item")
    if invite is None:
        return error_response("INVITE_NOT_FOUND", "招待URLが存在しません", status_code=404)

    community_id = invite["communityId"]
    if invite.get("createdBy") != user_id:
        require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    if not invite.get("revoked"):
        table.update_item(
            Key={"PK": f"INVITE#{token}", "SK": "METADATA"},
            UpdateExpression="SET revoked = :true",
            ExpressionAttributeValues={":true": True},
        )
        write_operation_log(
            action="REVOKE_INVITE",
            user_id=user_id,
            community_id=community_id,
            target_type="Invite",
            target_id=token,
        )
    return success_response({"token": token, "communityId": community_id, "revoked": True})


def join_via_invite(user_id, event):
    """F-103（API設計書v1.13 §4.4）: コミュニティの`memberApprovalRequired`
    フラグ（要件定義書v1.2 §10.1）、または招待発行者がMEMBERロールだった
    こと（`invite.createdByRole == "MEMBER"`、Issue #22）のいずれかに
    よって、即時のMembership作成とPENDING JoinRequestのどちらになるかが
    分岐する。管理者以外が発行した招待は、コミュニティ側の設定に関わらず
    強制的に承認制になる。
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
    # expiresAt（DynamoDB物理設計書v1.3 §3.4）は、期限付き招待のための
    # 将来的/任意のフィールドである。MVPでは常に無期限の招待を作成するため、
    # ここではまだ強制していない。

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

    if community.get("memberApprovalRequired") or invite.get("createdByRole") == "MEMBER":
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
