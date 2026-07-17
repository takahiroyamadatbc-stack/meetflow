"""コミュニティごとの実効参加頻度上限（Membership.frequencyLimitCount/
frequencyLimitPeriodが設定されていればそれを、無ければUser側の全体
デフォルトにフォールバック）を解決する共通ロジック（Issue #19、要件定義書
v1.7 §30、DynamoDB物理設計書v1.10 §3.1/§3.3）。

`display_name.py`/`auto_approve.py`と同じ「Membership優先・Userフォール
バック」パターンを踏襲する。
"""

from boto3.dynamodb.conditions import Key

from .time_utils import add_days_iso

_PERIOD_DAYS = {"WEEK": 7, "MONTH": 30}


def resolve_frequency_limit(membership_item: dict | None, profile_item: dict | None):
    """Membership/Userの両アイテムを既に取得済みの場合の解決ロジック
    （純粋関数、DBアクセスなし）。戻り値は(count, period)のタプル、
    両方未設定ならNone。countとperiodは書き込み側API（community_lambda/
    user_lambda）が常にセットで設定・解除する不変条件を前提にしており、
    ここでは片方だけが設定されているケースは扱わない。
    """
    membership = membership_item or {}
    if membership.get("frequencyLimitCount") is not None:
        return int(membership["frequencyLimitCount"]), membership["frequencyLimitPeriod"]
    profile = profile_item or {}
    if profile.get("frequencyLimitCount") is not None:
        return int(profile["frequencyLimitCount"]), profile["frequencyLimitPeriod"]
    return None


def get_frequency_limit(table, community_id: str, user_id: str):
    """Membership/Userの両アイテムをその場でget_itemして解決する。
    候補メンバーごとに呼ばれる（matching_lambdaの_create_candidate）。
    """
    membership = table.get_item(
        Key={"PK": f"COMMUNITY#{community_id}", "SK": f"MEMBER#{user_id}"}
    ).get("Item")
    profile = table.get_item(Key={"PK": f"USER#{user_id}", "SK": "PROFILE"}).get("Item")
    return resolve_frequency_limit(membership, profile)


def period_bounds(reference_iso: str, period: str) -> tuple[str, str]:
    """集計期間の境界を算出する（基準時刻からのローリングN日遡り。
    WEEK=7日、MONTH=30日）。暦週/暦月ではなくローリング期間を採用する
    理由は要件定義書に明記が無いため実装判断だが、既存のMatchingLambdaの
    期間計算（_MATCHING_WINDOW_DAYS等）と同じパターンに揃えている。
    """
    return add_days_iso(reference_iso, -_PERIOD_DAYS[period]), reference_iso


def count_confirmed_events_in_period(
    table, user_id: str, genre: str, period_start: str, period_end: str
) -> int:
    """参加頻度上限のコミュニティ横断・ジャンル単位カウント（要件定義書
    §30.4）。ダブルブッキング検知と同一のGSI1レンジクエリを応用する
    （DynamoDB物理設計書v1.10 アクセスパターン31）。CONFIRMED以外（承認
    待ち・キャンセル済み等）はまだ「確定」ではないためカウントしない。
    """
    resp = table.query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq(f"USER#{user_id}")
        & Key("GSI1SK").between(f"PARTICIPANT#{period_start}", f"PARTICIPANT#{period_end}"),
    )
    return sum(
        1
        for item in resp.get("Items", [])
        if item.get("status") == "CONFIRMED" and item.get("communityGenre") == genre
    )
