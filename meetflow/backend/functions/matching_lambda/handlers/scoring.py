"""F-403 scoring (機能要件書v1.1 §8/F-403, 要件定義書v1.2 §13.2).

孤立した純粋関数として実装しているのは、ドキュメントがこの重み付けを
規定しているから（実際には定性的な加点要素のみが示されており、点数配分
は示されていない）ではなく、Lambda設計書v1.1 §6.4がスコア計算の分離を
明示的に推奨しているためである。これにより、Phase2の信頼スコア/NG設定
要素を、マッチングフローを再構築することなく後から追加できる。以下の
重みは、要件定義書v1.2 §13.2の定性的要素を0-100のスコアに落とし込むために
考案したMVPのヒューリスティックである（要件定義書v1.2 §13.4のサンプル
候補は92点のスコアを示している）-- ドキュメントに正典となる点数配分は
存在しないため、これらの重みは権威あるものではなく調整可能な値として
扱うこと。
"""

_CONDITION_MATCH_WEIGHT = 30
_BEGINNER_WEIGHT = 20
_RECENCY_WEIGHT = 30
_PRIORITY_WEIGHT = 20
_RECENCY_CAP_DAYS = 30
_FREQUENCY_LIMIT_PENALTY_WEIGHT = 25


def calculate_score(
    *,
    template,
    members_profiles,
    members_days_since_last_played,
    members_frequency_status=None,
):
    """
    template: EventTemplateアイテム（dict）-- `conditions`（Map）と
        `priority`（0-100）が必要。
    members_profiles: 候補メンバーのUserプロフィールdictのリスト。
    members_days_since_last_played: メンバーごとのint値のリスト -- 各人の
        直近のCONFIRMED Participantレコードからの経過日数。参加履歴が
        一件も無い場合はNone（最大限「新鮮」として扱う）。
    members_frequency_status: メンバーごとの参加頻度上限の状態リスト
        （Issue #19、要件定義書v1.7 §30）。各要素は上限未設定/未達なら
        None、上限に達していれば{"name", "period", "limit", "count"}の
        dict。候補からの機械的な除外はせず、超過メンバーの割合に応じて
        スコアを減点し、成立理由に個別に明記するのみに留める
        （ヒューマン・イン・ザ・ループ原則、要件定義書§19）。

    戻り値: (score: int 0-100, reasons: list[str])。
    """
    reasons = ["全員予定一致"]  # F-402の必須条件（日時一致）を満たした候補
    conditions = template.get("conditions") or {}
    wants_beginner_ok = bool(conditions.get("beginnerOk"))

    if wants_beginner_ok and members_profiles:
        beginner_fraction = sum(
            1 for p in members_profiles if p.get("beginnerOk")
        ) / len(members_profiles)
    else:
        beginner_fraction = 1.0  # 要件が無い場合は自明に満たされる
    if beginner_fraction == 1.0:
        reasons.append("初心者対応可能" if wants_beginner_ok else "条件一致")

    if members_days_since_last_played:
        normalized = [
            1.0 if days is None else min(days, _RECENCY_CAP_DAYS) / _RECENCY_CAP_DAYS
            for days in members_days_since_last_played
        ]
        recency_fraction = sum(normalized) / len(normalized)
    else:
        recency_fraction = 0.0
    if recency_fraction > 0.5:
        reasons.append("最近参加していない人を含む")

    # EventTemplateアイテムをDynamoDB経由で読み込んだ場合、
    # template.get("priority")はdecimal.Decimalとして返ってくる（boto3の
    # Table resourceは全てのNumber属性をDecimalにデシリアライズし、
    # int/floatにはならない）-- これを下の浮動小数点演算に混ぜるとTypeError
    # になるため、各呼び出し箇所ではなくここでintにキャストする。
    priority = min(max(int(template.get("priority", 0) or 0), 0), 100)

    total = (
        _CONDITION_MATCH_WEIGHT * beginner_fraction
        + _BEGINNER_WEIGHT * beginner_fraction
        + _RECENCY_WEIGHT * recency_fraction
        + _PRIORITY_WEIGHT * (priority / 100)
    )

    exceeded_statuses = [s for s in (members_frequency_status or []) if s is not None]
    if members_frequency_status:
        exceeded_fraction = len(exceeded_statuses) / len(members_frequency_status)
    else:
        exceeded_fraction = 0.0
    total -= _FREQUENCY_LIMIT_PENALTY_WEIGHT * exceeded_fraction
    for status in exceeded_statuses:
        period_label = "週" if status["period"] == "WEEK" else "月"
        reasons.append(
            f"{status['name']}さんは{period_label}の上限（{status['limit']}回）に"
            "すでに達している"
        )

    return round(min(max(total, 0), 100)), reasons
