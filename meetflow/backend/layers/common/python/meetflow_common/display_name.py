"""コミュニティごとの実効表示名（Membership.displayNameが設定されていれば
それを、無ければUser.nicknameにフォールバック）を解決する共通ロジック
（機能要件書v1.5 F-108、DynamoDB物理設計書v1.6 §3.3）。

各ドメインLambdaが同じ「displayName ?? nickname」判定を重複実装しないよう、
ここに一元化する。
"""

from boto3.dynamodb.conditions import Key


def resolve_display_name(membership_item: dict | None, profile_item: dict | None) -> str:
    """Membership/Userの両アイテムを既に取得済みの場合の解決ロジック
    （純粋関数、DBアクセスなし）。呼び出し元が両方のアイテムをループ内で
    既に持っている場合（例：メンバー一覧）は、これを直接使うことで
    Membershipの再取得を避けられる。
    """
    display_name = (membership_item or {}).get("displayName")
    if display_name:
        return display_name
    return (profile_item or {}).get("nickname", "")


def get_display_name(table, community_id: str, user_id: str) -> str:
    """Membership/Userの両アイテムをその場でget_itemして解決する。
    呼び出し元がどちらのアイテムも保持していない箇所
    （マッチング候補・イベント参加者一覧等）向けの便宜関数。
    """
    membership = table.get_item(
        Key={"PK": f"COMMUNITY#{community_id}", "SK": f"MEMBER#{user_id}"}
    ).get("Item")
    profile = table.get_item(Key={"PK": f"USER#{user_id}", "SK": "PROFILE"}).get("Item")
    return resolve_display_name(membership, profile)


def is_display_name_taken(
    table, community_id: str, candidate: str, *, exclude_user_id: str
) -> bool:
    """同一コミュニティ内で、exclude_user_id以外のメンバーの実効表示名と
    candidateが重複していないかをチェックする（なりすまし・混同防止）。
    displayName同士だけでなく、displayName未設定メンバーのUser.nicknameとの
    重複も対象にする。コミュニティ規模（10〜30人想定）ではメンバー一覧取得+
    アプリケーション側比較で十分軽い処理のため、専用GSIは用意しない
    （DynamoDB物理設計書v1.6 §3.3）。

    比較は完全一致のみで、大文字小文字・全角半角の正規化は行わない
    （MVPスコープ外）。
    """
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"COMMUNITY#{community_id}")
        & Key("SK").begins_with("MEMBER#")
    )
    for item in resp.get("Items", []):
        member_user_id = item["SK"].split("#", 1)[1]
        if member_user_id == exclude_user_id:
            continue
        display_name = item.get("displayName")
        if not display_name:
            profile = (
                table.get_item(
                    Key={"PK": f"USER#{member_user_id}", "SK": "PROFILE"}
                ).get("Item")
                or {}
            )
            display_name = profile.get("nickname", "")
        if display_name == candidate:
            return True
    return False
