from boto3.dynamodb.conditions import Key

from meetflow_common import (
    error_response,
    get_display_name,
    get_table,
    require_membership,
    success_response,
)


def list_community_logs(user_id, event):
    """GET /communities/{communityId}/logs（API設計書v1.7 §12.1）。管理者向け
    （要件定義書 §19 F-1302）のため、OWNER/ADMINのみ閲覧可能とする。
    DynamoDB物理設計書v1.6 §3.15のPK=LOG#{communityId}に対する単純なQueryで
    完結する。
    """
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"LOG#{community_id}"),
        ScanIndexForward=False,
    )
    logs = [
        _to_api_log(table, item, community_id, item["GSI1PK"].split("#", 1)[1])
        for item in resp.get("Items", [])
    ]
    return success_response({"logs": logs})


def get_user_logs(user_id, event):
    """GET /users/{userId}/logs（API設計書v1.7 §12.2）。

    本人、または対象ユーザーと同じコミュニティでOWNER/ADMINロールを持つ
    ユーザーのみ閲覧可能（§12.2補足）。本人以外の場合は、閲覧者がOWNER/ADMIN
    ロールを持つコミュニティに紐づくログのみを返す -- コミュニティに紐づかない
    ログイン等の`LOG#GLOBAL#`ログや、権限の無い他コミュニティのログは対象外
    （どのコミュニティに対しても権限が無ければFORBIDDEN）。

    URLパスは`/users/`始まりだが、権限判定の主体がコミュニティのMembership/
    roleであるため、それらを扱うCommunityLambda側に置いている
    （`/users/{userId}/results`がResultLambdaにあるのと同種の判断）。
    """
    target_user_id = event["pathParameters"]["userId"]
    table = get_table()
    is_self = user_id == target_user_id

    admin_community_ids = None
    if not is_self:
        admin_community_ids = _admin_community_ids(table, user_id)
        if not admin_community_ids:
            return error_response(
                "FORBIDDEN", "このユーザーの操作ログを閲覧する権限がありません"
            )

    resp = table.query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq(f"USER#{target_user_id}")
        & Key("GSI1SK").begins_with("LOG#"),
        ScanIndexForward=False,
    )

    logs = []
    for item in resp.get("Items", []):
        community_id = _community_id_from_log_pk(item["PK"])
        if not is_self and community_id not in admin_community_ids:
            continue
        logs.append(_to_api_log(table, item, community_id, target_user_id))
    return success_response({"logs": logs})


def _admin_community_ids(table, user_id):
    """呼び出し元がOWNER/ADMINロールを持つコミュニティidの集合
    （GSI1経由、list_communitiesと同じアクセスパターン）。"""
    resp = table.query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq(f"USER#{user_id}")
        & Key("GSI1SK").begins_with("COMMUNITY#"),
    )
    return {
        item["GSI1SK"].split("#", 1)[1]
        for item in resp.get("Items", [])
        if item.get("role") in ("OWNER", "ADMIN")
    }


def _community_id_from_log_pk(pk):
    # LOG#{communityId} または LOG#GLOBAL#{userId}（DynamoDB物理設計書v1.6
    # §3.15）。communityIdに紐づかない操作（ログイン等）はGLOBAL。
    rest = pk.split("#", 1)[1]
    if rest.startswith("GLOBAL#"):
        return None
    return rest


def _to_api_log(table, item, community_id, actor_user_id):
    log_id = item["SK"].split("#", 1)[1]
    return {
        "logId": log_id,
        "communityId": community_id,
        "userId": actor_user_id,
        "displayName": _resolve_actor_name(table, community_id, actor_user_id),
        "action": item.get("action"),
        "targetType": item.get("targetType"),
        "targetId": item.get("targetId"),
        "before": item.get("before"),
        "after": item.get("after"),
        "createdAt": item.get("createdAt"),
    }


def _resolve_actor_name(table, community_id, actor_user_id):
    # Lambda設計書v1.3 §2の指針通り、ログ自体にはuserIdのみを保持し表示名の
    # スナップショットは持たないため、閲覧のたびに解決する。
    if community_id is None:
        profile = (
            table.get_item(Key={"PK": f"USER#{actor_user_id}", "SK": "PROFILE"}).get(
                "Item"
            )
            or {}
        )
        return profile.get("nickname", "")
    return get_display_name(table, community_id, actor_user_id)
