import json
from decimal import Decimal

# エラーコード一覧v1.1（§1-8）の全コードをここに集約している。各呼び出し元に
# `status_code=` を覚えさせておくのではなく、ここで一元管理する方式にした
# -- 以前のバージョンではこのdictに共通（§1）コードといくつかの追加分しか
# 無く、ドメインLambda各所の呼び出し元が自ドメインのコード用に`status_code`を
# 明示的に渡し忘れていた（例：EVENT_NOT_FOUNDが、ドキュメント通りの404では
# なく、この関数のデフォルトである400に黙ってフォールバックしていた）。
# 全コードの表をここに保持しておけば、呼び出し元が`status_code=`を渡す必要が
# あるのは、NO_CANDIDATES_FOUNDのように「エラー」が実質的には正常レスポンス
# として扱われるような稀なケースだけになる。
_STATUS_BY_CODE = {
    # §1 共通エラー
    "USER_NOT_FOUND": 404,
    "COMMUNITY_NOT_FOUND": 404,
    "FORBIDDEN": 403,
    "UNAUTHORIZED": 401,
    "INVALID_PARAMETER": 400,
    "INTERNAL_ERROR": 500,
    # §2 User
    "PROFILE_VALIDATION_ERROR": 400,
    # §3 Community
    "INVITE_NOT_FOUND": 404,
    "INVITE_REVOKED": 410,
    "INVITE_EXPIRED": 410,
    "ALREADY_MEMBER": 409,
    "JOIN_REQUEST_ALREADY_PENDING": 409,
    "JOIN_REQUEST_NOT_FOUND": 404,
    "JOIN_REQUEST_ALREADY_PROCESSED": 409,
    "LAST_OWNER_CANNOT_LEAVE": 409,
    "MEMBER_SUSPENDED": 403,
    "LOCATION_NOT_FOUND": 404,
    "DISPLAY_NAME_ALREADY_TAKEN": 409,
    # §4 Availability
    "INVALID_TIME_RANGE": 400,
    "AVAILABILITY_NOT_FOUND": 404,
    "AVAILABILITY_OVERLAP": 409,
    "BATCH_SIZE_EXCEEDED": 400,
    "AVAILABILITY_REQUEST_NOT_FOUND": 404,
    # §5 Matching (EventTemplate / MatchCandidate)
    "INVALID_PLAYER_RANGE": 400,
    "EVENT_TEMPLATE_NOT_FOUND": 404,
    "NO_CANDIDATES_FOUND": 200,
    "CANDIDATE_NOT_FOUND": 404,
    "CANDIDATE_ALREADY_USED": 409,
    # §6 Event (イベント・参加者・キャンセル)
    "EVENT_NOT_FOUND": 404,
    "INVALID_STATUS_TRANSITION": 409,
    "EVENT_ALREADY_CONFIRMED": 409,
    "EVENT_ALREADY_CANCELLED": 409,
    "PARTICIPANT_NOT_FOUND": 404,
    "CANCEL_REQUEST_ALREADY_PENDING": 409,
    "CANCEL_REQUEST_NOT_FOUND": 404,
    "CANCEL_REQUEST_ALREADY_PROCESSED": 409,
    "NOT_A_PARTICIPANT": 403,
    "PARTICIPANT_SCHEDULE_CONFLICT": 409,
    # §7 Result
    "EVENT_NOT_COMPLETED": 409,
    "RESULT_VALIDATION_ERROR": 400,
    "RESULT_ACCESS_DENIED": 403,
    # §8 Notification
    "NOTIFICATION_NOT_FOUND": 404,
}


def _json_default(value):
    # boto3のTable resourceは、DynamoDBのNumber属性を常に
    # decimal.Decimalとしてデシリアライズする（int/floatにはならない）。
    # そのため、DynamoDBから読み込んだ値をそのままレスポンスにエコーバックする
    # ハンドラー（すでに素のint/floatになっている、パース直後のリクエスト
    # ボディとは異なる）は、事前に変換しないと
    # `TypeError: Object of type Decimal is not JSON serializable`に
    # ぶつかる。ここに一元化しておくことで、各呼び出し元がキャストを
    # 覚えておかなくても全ドメインがこの恩恵を受けられる。
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def error_response(code: str, message: str, *, status_code: int = None) -> dict:
    """API Gateway（Lambdaプロキシ統合）向けのエラーレスポンスを組み立てる。

    エンベロープはAPI設計書v1.4 §2に準拠。`status_code`は、上のテーブルを
    上書きする必要がある場合にのみ明示的に渡せばよい（例：
    NO_CANDIDATES_FOUNDはこの関数を通さず、通常の空リストレスポンスとして
    扱われる -- MatchingLambda参照）。
    """
    return {
        "statusCode": status_code or _STATUS_BY_CODE.get(code, 400),
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(
            {"success": False, "error": {"code": code, "message": message}},
            ensure_ascii=False,
            default=_json_default,
        ),
    }


def success_response(data, *, status_code: int = 200) -> dict:
    """API Gateway（Lambdaプロキシ統合）向けの成功レスポンスを組み立てる。"""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(
            {"success": True, "data": data}, ensure_ascii=False, default=_json_default
        ),
    }
