"""コミュニティごとの実効自動承認設定（Membership.autoApproveが設定されて
いればそれを、無ければUser.autoApproveの全体デフォルトにフォールバック、
両方未設定ならFalse）を解決する共通ロジック（Issue #10、DynamoDB物理設計書
§3.1/§3.3）。

`display_name.py`と同じ「Membership優先・Userフォールバック」パターンを
踏襲する。
"""


def resolve_auto_approve(membership_item: dict | None, profile_item: dict | None) -> bool:
    """Membership/Userの両アイテムを既に取得済みの場合の解決ロジック
    （純粋関数、DBアクセスなし）。
    """
    membership_value = (membership_item or {}).get("autoApprove")
    if membership_value is not None:
        return bool(membership_value)
    return bool((profile_item or {}).get("autoApprove", False))


def get_auto_approve(table, community_id: str, user_id: str) -> bool:
    """Membership/Userの両アイテムをその場でget_itemして解決する。
    候補メンバーごとに呼ばれる（confirm_event）。
    """
    membership = table.get_item(
        Key={"PK": f"COMMUNITY#{community_id}", "SK": f"MEMBER#{user_id}"}
    ).get("Item")
    profile = table.get_item(Key={"PK": f"USER#{user_id}", "SK": "PROFILE"}).get("Item")
    return resolve_auto_approve(membership, profile)
