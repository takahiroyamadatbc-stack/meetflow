from meetflow_common import AuthError

# コミュニティ単位のMembership.roleとは別軸の、システム全体の運営者ロール
# (Lambda設計書v1.7 §9b.4)。判定軸が他ドメインの権限チェック(コミュニティ
# 所属・role確認)と全く異なるため、meetflow_common.require_membershipとは
# 別に、FeedbackLambda内に閉じた小さな判定関数として実装する(無理に共通化
# しない、という設計書の方針通り)。
_OPERATORS_GROUP = "Operators"


def require_operator(event: dict) -> None:
    """呼び出し元のJWTクレームにOperatorsグループが含まれていることを確認する。

    API GatewayのCognito User Poolsオーソライザーは、REST API(このプロジェクト
    が使うペイロード形式1.0)では`cognito:groups`をカンマ区切りの文字列として
    渡す(HTTP APIのv2形式のようなJSON配列にはならない)。
    """
    claims = (event.get("requestContext") or {}).get("authorizer", {}).get(
        "claims", {}
    ) or {}
    groups_raw = claims.get("cognito:groups") or ""
    groups = [g for g in groups_raw.split(",") if g]
    if _OPERATORS_GROUP not in groups:
        raise AuthError("FORBIDDEN", "運営者権限が必要です")
