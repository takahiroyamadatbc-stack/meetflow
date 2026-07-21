import os
import re
import uuid

import boto3
from boto3.dynamodb.conditions import Key

from meetflow_common import (
    error_response,
    generate_id,
    get_table,
    now_iso_ms,
    parse_body,
    require_membership,
    success_response,
    transact_write,
    write_operation_log,
)

_MAX_NAME_LENGTH = 50  # 設計書には明記されていない、MVP向け保守的な上限値
_THEME_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")

# F-806 コミュニティ内ランキング設定（Issue #40、API設計書v1.25 §4.2e）。
_RANKING_GAME_TYPES = ("MAHJONG4", "MAHJONG3")
_RANKING_PERIOD_TYPES = ("MONTH", "QUARTER", "HALF_YEAR", "YEAR", "ALL_TIME")
_RANKING_METRICS = (
    "AVERAGE_RANK",
    "TOTAL_POINTS",
    "FIRST_PLACE_RATE",
    "SECOND_PLACE_RATE",
    "TOP_TWO_RATE",
    "NON_LAST_RATE",
    "TOTAL_GAMES",
    "PARTICIPATED_EVENTS",
    "TOTAL_CHIPS",
    "AVERAGE_CHIPS",
)
_RANKING_SETTINGS_DEFAULTS = {
    "gameType": "MAHJONG4",
    "periodType": "MONTH",
    "metric": "AVERAGE_RANK",
    "minGames": 0,
}

# Issue #52: コミュニティアイコンアップロード。許可フォーマットはUserLambdaの
# アバターアップロード（user_lambda/handler.py、Issue #47）と揃える。
# 同じバケット/CloudFrontディストリビューションをキープレフィックスで
# 分けて共用する（infra/meetflow_infra/meetflow_compute_stack.py
# `_build_avatar_bucket`参照）。
_ALLOWED_ICON_CONTENT_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}
_ICON_UPLOAD_EXPIRES_IN_SECONDS = 300

_s3_client = None


def _get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


def create_community(user_id, event):
    """F-101（API設計書v1.4 §4.1）。コミュニティ作成 + owner Membershipは、
    トランザクションではなく単純な2回のPutItemである -- DynamoDB物理設計書
    v1.3 §5がTransactWriteItemsを要求するとしているのは参加リクエスト承認/
    オーナー移譲/イベント確定のみなので、意図的にそれ以上のことはしていない。
    """
    body = parse_body(event)
    name = body.get("name")
    if not isinstance(name, str) or not (1 <= len(name) <= _MAX_NAME_LENGTH):
        return _invalid_name()

    description = body.get("description", "")
    genre = body.get("genre", "")
    member_approval_required = bool(body.get("memberApprovalRequired", False))

    theme_color = body.get("themeColor")
    if theme_color is not None:
        validation_error = _validate_theme_color(theme_color)
        if validation_error:
            return validation_error

    community_id = generate_id()
    created_at = now_iso_ms()
    table = get_table()

    community_item = {
        "PK": f"COMMUNITY#{community_id}",
        "SK": "METADATA",
        "name": name,
        "description": description,
        "genre": genre,
        "memberApprovalRequired": member_approval_required,
        # MVPでは常にPERSONALコミュニティを作成する（DynamoDB物理設計書
        # v1.3 §3.2）。STORE/OFFICIALはPhase3で扱う。
        "communityType": "PERSONAL",
        "ownerId": user_id,
        "createdAt": created_at,
    }
    if theme_color:
        community_item["themeColor"] = theme_color
    table.put_item(Item=community_item)
    table.put_item(
        Item={
            "PK": f"COMMUNITY#{community_id}",
            "SK": f"MEMBER#{user_id}",
            "GSI1PK": f"USER#{user_id}",
            "GSI1SK": f"COMMUNITY#{community_id}",
            "role": "OWNER",
            "status": "ACTIVE",
            "joinedAt": created_at,
        }
    )
    write_operation_log(
        action="CREATE_COMMUNITY",
        user_id=user_id,
        community_id=community_id,
        target_type="Community",
        target_id=community_id,
    )
    return success_response(
        {
            "communityId": community_id,
            "name": name,
            "description": description,
            "genre": genre,
            "memberApprovalRequired": member_approval_required,
            "themeColor": theme_color,
        },
        status_code=201,
    )


def get_community(user_id, event):
    """GET /communities/{communityId}（API設計書には未記載だが、フロント
    エンド実装時にコミュニティ詳細画面(S-05)が単体取得手段を持たないことが
    判明したため追加。DynamoDB物理設計書のキー設計(PK/SK)からは逸脱せず、
    METADATA項目への単純なGetItemのみで完結する。呼び出し元自身の
    Membership（require_membershipの戻り値）からroleを取得できるため、
    一覧(list_communities)には無いroleとmemberApprovalRequiredの両方を
    レスポンスに含められる。

    `pendingRequestCount`（Issue #29）：JOINREQ#プレフィックスをクエリし
    PENDING件数をカウントする。管理者向けのバッジ表示用の値だが、
    `list_join_requests`と同じクエリ+クライアント側フィルタパターンを
    踏襲し、ロールを問わず常に計算・返却する（フロント側でisAdminの
    場合のみバッジとして描画する）。
    """
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    membership = require_membership(table, community_id, user_id)

    community = table.get_item(
        Key={"PK": f"COMMUNITY#{community_id}", "SK": "METADATA"}
    ).get("Item")
    if community is None:
        return error_response("COMMUNITY_NOT_FOUND", "コミュニティが見つかりません")

    join_requests_resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"COMMUNITY#{community_id}")
        & Key("SK").begins_with("JOINREQ#")
    )
    pending_request_count = sum(
        1
        for item in join_requests_resp.get("Items", [])
        if item.get("status") == "PENDING"
    )

    return success_response(
        {
            "communityId": community_id,
            "name": community.get("name"),
            "description": community.get("description", ""),
            "genre": community.get("genre", ""),
            "memberApprovalRequired": community.get("memberApprovalRequired", False),
            "themeColor": community.get("themeColor"),
            "icon": community.get("icon"),
            "role": membership.get("role"),
            "pendingRequestCount": pending_request_count,
            "rankingDefaultGameType": community.get(
                "rankingDefaultGameType", _RANKING_SETTINGS_DEFAULTS["gameType"]
            ),
            "rankingDefaultPeriodType": community.get(
                "rankingDefaultPeriodType", _RANKING_SETTINGS_DEFAULTS["periodType"]
            ),
            "rankingDefaultMetric": community.get(
                "rankingDefaultMetric", _RANKING_SETTINGS_DEFAULTS["metric"]
            ),
            "rankingDefaultMinGames": community.get(
                "rankingDefaultMinGames", _RANKING_SETTINGS_DEFAULTS["minGames"]
            ),
        }
    )


def list_communities(user_id, event):
    """GET /communities（API設計書v1.4 §4.2）: 呼び出し元が所属する
    コミュニティ一覧を、GSI1（`USER#{userId}` / `COMMUNITY#`）経由で取得する。
    このプロジェクトの規模（コミュニティあたり10〜30メンバー）では
    ユーザーあたりのコミュニティ数は少ないため、ここではバッチ処理より
    コミュニティごとにGetItemする方がシンプルである。

    表示順（Issue #16）はMembership.sortOrder（ユーザーごとの並び替えAPI
    reorder_communitiesが書き込む）昇順。未設定（新規参加直後等）は末尾に
    回す。
    """
    table = get_table()
    resp = table.query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq(f"USER#{user_id}")
        & Key("GSI1SK").begins_with("COMMUNITY#"),
    )

    communities = []
    for membership in resp.get("Items", []):
        community_id = membership["GSI1SK"].split("#", 1)[1]
        community = table.get_item(
            Key={"PK": f"COMMUNITY#{community_id}", "SK": "METADATA"}
        ).get("Item")
        if community is None:
            continue
        communities.append(
            {
                "communityId": community_id,
                "name": community.get("name"),
                "description": community.get("description", ""),
                "genre": community.get("genre", ""),
                "role": membership.get("role"),
                "themeColor": community.get("themeColor"),
                "_sortOrder": membership.get("sortOrder"),
            }
        )
    communities.sort(
        key=lambda c: (c["_sortOrder"] is None, c["_sortOrder"], c["communityId"])
    )
    for community in communities:
        del community["_sortOrder"]
    return success_response({"communities": communities})


def reorder_communities(user_id, event):
    """PUT /communities/order（Issue #16。API設計書には無い新規エンドポイント
    -- GET /communities/{communityId}と同様、フロント実装時の追加として扱う）。

    bodyのcommunityIds配列の並び順どおりに、呼び出し元のMembership.sortOrder
    を0,1,2...と書き換える。他人のMembershipは操作できないよう、各IDに
    ついてrequire_membershipで所属確認する。
    """
    body = parse_body(event)
    community_ids = body.get("communityIds")
    if (
        not isinstance(community_ids, list)
        or not community_ids
        or not all(isinstance(c, str) for c in community_ids)
    ):
        return error_response("INVALID_PARAMETER", "communityIdsが不正です")

    table = get_table()
    for community_id in community_ids:
        require_membership(table, community_id, user_id)

    for index, community_id in enumerate(community_ids):
        table.update_item(
            Key={"PK": f"COMMUNITY#{community_id}", "SK": f"MEMBER#{user_id}"},
            UpdateExpression="SET sortOrder = :order",
            ExpressionAttributeValues={":order": index},
        )

    return success_response({"communityIds": community_ids})


def update_community(user_id, event):
    """PUT /communities/{communityId}（要件定義書v1.2 §10.1: 管理者は情報編集
    を実施できる -> OWNER/ADMIN）。"""
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    body = parse_body(event)
    names = {}
    values = {}
    set_clauses = []

    if "name" in body:
        name = body["name"]
        if not isinstance(name, str) or not (1 <= len(name) <= _MAX_NAME_LENGTH):
            return _invalid_name()
        names["#name"] = "name"
        values[":name"] = name
        set_clauses.append("#name = :name")
    if "description" in body:
        names["#description"] = "description"
        values[":description"] = body["description"]
        set_clauses.append("#description = :description")
    if "genre" in body:
        names["#genre"] = "genre"
        values[":genre"] = body["genre"]
        set_clauses.append("#genre = :genre")
    if "memberApprovalRequired" in body:
        names["#mar"] = "memberApprovalRequired"
        values[":mar"] = bool(body["memberApprovalRequired"])
        set_clauses.append("#mar = :mar")
    if "icon" in body:
        icon = body["icon"]
        if icon is not None and not isinstance(icon, str):
            return error_response("INVALID_PARAMETER", "iconが不正です")
        names["#icon"] = "icon"
        values[":icon"] = icon
        set_clauses.append("#icon = :icon")

    if not set_clauses:
        return _no_fields_to_update()

    table.update_item(
        Key={"PK": f"COMMUNITY#{community_id}", "SK": "METADATA"},
        UpdateExpression="SET " + ", ".join(set_clauses),
        ConditionExpression="attribute_exists(PK)",
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )
    write_operation_log(
        action="UPDATE_COMMUNITY",
        user_id=user_id,
        community_id=community_id,
        target_type="Community",
        target_id=community_id,
        after=body,
    )
    community = table.get_item(
        Key={"PK": f"COMMUNITY#{community_id}", "SK": "METADATA"}
    ).get("Item")
    return success_response(
        {
            "communityId": community_id,
            "name": community.get("name"),
            "description": community.get("description", ""),
            "genre": community.get("genre", ""),
            "memberApprovalRequired": community.get("memberApprovalRequired", False),
            "icon": community.get("icon"),
        }
    )


def transfer_owner(user_id, event):
    """F-106（Lambda設計書v1.1 §4.2）: OWNERがオーナー権を移譲する。移譲元の
    OWNERはMEMBERに戻る（要件定義書v1.2 §9、ADMINへの降格ではない）。
    両方のロール変更 + Community.ownerIdは1回のTransactWriteItems呼び出しに
    まとめる（DynamoDB物理設計書v1.3 §5）ため、部分的な失敗によって2人の
    メンバーが同時にOWNERロールを持つ/持たない状態になることはない。
    """
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    require_membership(table, community_id, user_id, roles=("OWNER",))

    body = parse_body(event)
    new_owner_id = body.get("newOwnerId")
    if not isinstance(new_owner_id, str) or not new_owner_id or new_owner_id == user_id:
        return error_response("INVALID_PARAMETER", "移譲先のuserIdが不正です")

    new_owner_membership = table.get_item(
        Key={"PK": f"COMMUNITY#{community_id}", "SK": f"MEMBER#{new_owner_id}"}
    ).get("Item")
    if new_owner_membership is None or new_owner_membership.get("status") == "SUSPENDED":
        return error_response(
            "INVALID_PARAMETER", "移譲先はアクティブなメンバーである必要があります"
        )

    transact_write(
        [
            {
                "Update": {
                    "Key": {
                        "PK": f"COMMUNITY#{community_id}",
                        "SK": f"MEMBER#{new_owner_id}",
                    },
                    "UpdateExpression": "SET #role = :owner",
                    "ExpressionAttributeNames": {"#role": "role"},
                    "ExpressionAttributeValues": {":owner": "OWNER"},
                }
            },
            {
                "Update": {
                    "Key": {"PK": f"COMMUNITY#{community_id}", "SK": f"MEMBER#{user_id}"},
                    "UpdateExpression": "SET #role = :member",
                    "ExpressionAttributeNames": {"#role": "role"},
                    "ExpressionAttributeValues": {":member": "MEMBER"},
                }
            },
            {
                "Update": {
                    "Key": {"PK": f"COMMUNITY#{community_id}", "SK": "METADATA"},
                    "UpdateExpression": "SET ownerId = :new_owner",
                    "ExpressionAttributeValues": {":new_owner": new_owner_id},
                }
            },
        ]
    )
    write_operation_log(
        action="TRANSFER_OWNER",
        user_id=user_id,
        community_id=community_id,
        target_type="Community",
        target_id=community_id,
        before={"ownerId": user_id},
        after={"ownerId": new_owner_id},
    )
    return success_response({"communityId": community_id, "ownerId": new_owner_id})


def update_theme_color(user_id, event):
    """PUT /communities/{communityId}/theme-color（API設計書v1.9 §4.2c）。

    OWNER/ADMINがコミュニティのテーマカラーを設定・変更する。空文字列/null
    送信は解除（アプリの既定色へのフォールバック表示に戻す）を意味する
    -- F-108の表示名解除（update_my_display_name）と同じパターン。名称・
    説明文等の編集APIがまだ無い中でこの1属性だけ専用エンドポイントに
    切り出しているのは、汎用的な`PUT /communities/{communityId}`
    （update_community）とは別に4.5bと同様の単機能エンドポイントとして
    設計されているため（API設計書同節の解説を参照）。
    """
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    body = parse_body(event)
    raw = body.get("themeColor")
    if raw is not None and not isinstance(raw, str):
        return error_response("INVALID_PARAMETER", "themeColorが不正です")

    theme_color = (raw or "").strip()
    if theme_color:
        validation_error = _validate_theme_color(theme_color)
        if validation_error:
            return validation_error

    key = {"PK": f"COMMUNITY#{community_id}", "SK": "METADATA"}
    if theme_color:
        table.update_item(
            Key=key,
            UpdateExpression="SET themeColor = :v",
            ConditionExpression="attribute_exists(PK)",
            ExpressionAttributeValues={":v": theme_color},
        )
    else:
        table.update_item(
            Key=key,
            UpdateExpression="REMOVE themeColor",
            ConditionExpression="attribute_exists(PK)",
        )

    write_operation_log(
        action="UPDATE_THEME_COLOR",
        user_id=user_id,
        community_id=community_id,
        target_type="Community",
        target_id=community_id,
        after={"themeColor": theme_color or None},
    )
    return success_response({"communityId": community_id, "themeColor": theme_color or None})


def update_ranking_settings(user_id, event):
    """PUT /communities/{communityId}/ranking-settings（API設計書v1.25
    §4.2e、F-806）。

    コミュニティ内ランキング（F-805、ResultLambda `get_community_ranking`）
    のデフォルト表示条件（種目・集計期間プリセット・指標・足切り件数）を
    OWNER/ADMINが設定する。update_theme_colorと同じ「単機能PUTエンドポイント、
    未指定/nullでシステムデフォルトに解除」パターンを踏襲するが、4項目は
    テーマカラーと異なり常にまとめて1回で更新する（部分更新は設けない、
    Issue #40コメント決定事項）。
    """
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    body = parse_body(event)
    validation_error = _validate_ranking_settings(body)
    if validation_error:
        return validation_error

    game_type = body.get("gameType") or _RANKING_SETTINGS_DEFAULTS["gameType"]
    period_type = body.get("periodType") or _RANKING_SETTINGS_DEFAULTS["periodType"]
    metric = body.get("metric") or _RANKING_SETTINGS_DEFAULTS["metric"]
    min_games = body.get("minGames")
    if min_games is None:
        min_games = _RANKING_SETTINGS_DEFAULTS["minGames"]

    table.update_item(
        Key={"PK": f"COMMUNITY#{community_id}", "SK": "METADATA"},
        UpdateExpression=(
            "SET rankingDefaultGameType = :gt, rankingDefaultPeriodType = :pt, "
            "rankingDefaultMetric = :m, rankingDefaultMinGames = :mg"
        ),
        ConditionExpression="attribute_exists(PK)",
        ExpressionAttributeValues={
            ":gt": game_type,
            ":pt": period_type,
            ":m": metric,
            ":mg": min_games,
        },
    )

    write_operation_log(
        action="UPDATE_RANKING_SETTINGS",
        user_id=user_id,
        community_id=community_id,
        target_type="Community",
        target_id=community_id,
        after={
            "rankingDefaultGameType": game_type,
            "rankingDefaultPeriodType": period_type,
            "rankingDefaultMetric": metric,
            "rankingDefaultMinGames": min_games,
        },
    )
    return success_response(
        {
            "communityId": community_id,
            "gameType": game_type,
            "periodType": period_type,
            "metric": metric,
            "minGames": min_games,
        }
    )


def create_icon_upload_url(user_id, event):
    """POST /communities/{communityId}/icon/upload-url（Issue #52）。

    コミュニティアイコン画像アップロード用の署名付きPUT URLを発行する。
    UserLambdaのアバターアップロード（Issue #47、user_lambda/handler.py
    `_create_avatar_upload_url`）と同じバケット・CloudFrontディストリ
    ビューションを、キープレフィックス（`communities/{communityId}/...`）
    で分けて共用する。OWNER/ADMIN限定（テーマカラー変更等と同じ権限）。
    """
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    body = parse_body(event)
    content_type = body.get("contentType")
    if content_type not in _ALLOWED_ICON_CONTENT_TYPES:
        return error_response(
            "INVALID_PARAMETER", "画像形式はPNG/JPEG/WebPのいずれかにしてください"
        )

    ext = _ALLOWED_ICON_CONTENT_TYPES[content_type]
    icon_key = f"communities/{community_id}/{uuid.uuid4().hex}.{ext}"
    upload_url = _get_s3_client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": os.environ["AVATAR_BUCKET_NAME"],
            "Key": icon_key,
            "ContentType": content_type,
        },
        ExpiresIn=_ICON_UPLOAD_EXPIRES_IN_SECONDS,
    )
    icon_url = f"https://{os.environ['AVATAR_CLOUDFRONT_DOMAIN']}/{icon_key}"

    return success_response(
        {
            "uploadUrl": upload_url,
            "iconUrl": icon_url,
            "expiresIn": _ICON_UPLOAD_EXPIRES_IN_SECONDS,
        }
    )


def delete_community(user_id, event):
    """DELETE /communities/{communityId}（Issue #2）。

    API設計書には未記載のMVP追加API。コミュニティ作成時のフロント表示だけが
    失敗しバックエンドでは実際に作成されていた等の理由で残った、実質空の
    コミュニティを片付ける手段としてUIから削除できるようにする。
    自分以外のメンバーが1人でも所属している場合は削除を拒否する
    （他メンバーの空き予定・成績等のデータを巻き込む削除は、相互非公開型
    マッチングの原則（要件定義書v1.4 §29）やデータ整合性の観点から行わない）。
    """
    community_id = event["pathParameters"]["communityId"]
    table = get_table()
    require_membership(table, community_id, user_id, roles=("OWNER",))

    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"COMMUNITY#{community_id}")
        & Key("SK").begins_with("MEMBER#")
    )
    members = resp.get("Items", [])
    if any(member["SK"] != f"MEMBER#{user_id}" for member in members):
        return error_response(
            "COMMUNITY_NOT_EMPTY", "他のメンバーが在籍しているコミュニティは削除できません"
        )

    transact_write(
        [
            {"Delete": {"Key": {"PK": f"COMMUNITY#{community_id}", "SK": "METADATA"}}},
            {
                "Delete": {
                    "Key": {"PK": f"COMMUNITY#{community_id}", "SK": f"MEMBER#{user_id}"}
                }
            },
        ]
    )
    write_operation_log(
        action="DELETE_COMMUNITY",
        user_id=user_id,
        community_id=community_id,
        target_type="Community",
        target_id=community_id,
    )
    return success_response({"communityId": community_id, "deleted": True})


def _invalid_name():
    return error_response("INVALID_PARAMETER", "コミュニティ名が不正です")


def _validate_theme_color(value):
    if not isinstance(value, str) or not _THEME_COLOR_PATTERN.match(value):
        return error_response(
            "INVALID_PARAMETER", "themeColorは#RRGGBB形式で指定してください"
        )
    return None


def _validate_ranking_settings(body):
    if not isinstance(body, dict):
        return error_response("INVALID_PARAMETER", "リクエスト内容が不正です")

    game_type = body.get("gameType")
    if game_type is not None and game_type not in _RANKING_GAME_TYPES:
        return error_response("INVALID_PARAMETER", "gameTypeが不正です")

    period_type = body.get("periodType")
    if period_type is not None and period_type not in _RANKING_PERIOD_TYPES:
        return error_response("INVALID_PARAMETER", "periodTypeが不正です")

    metric = body.get("metric")
    if metric is not None and metric not in _RANKING_METRICS:
        return error_response("INVALID_PARAMETER", "metricが不正です")

    min_games = body.get("minGames")
    if min_games is not None and (
        not isinstance(min_games, int)
        or isinstance(min_games, bool)
        or min_games < 0
    ):
        return error_response("INVALID_PARAMETER", "minGamesが不正です")

    return None


def _no_fields_to_update():
    return error_response("INVALID_PARAMETER", "更新項目がありません")
