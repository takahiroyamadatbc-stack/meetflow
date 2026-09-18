"""ドラフト企画固有のエラーコード表。

共通レイヤーの`meetflow_common.errors`にもコード→HTTPステータスの表があるが、
そちらに追記すると全ドメインLambdaが乗る共通Layerを変更することになり、
DESIGN.md §4.11の「既存5スタックを1行も触らない」に反する。
ドラフト固有のコードはこちらで持ち、`status_code=`を明示して共通の
`error_response`に渡す。
"""

from meetflow_common import error_response

_DRAFT_STATUS_BY_CODE = {
    # ドラフト本体
    "DRAFT_NOT_FOUND": 404,
    "DRAFT_INVALID_STATUS": 409,
    "DRAFT_VALIDATION_ERROR": 400,
    "NOT_DRAFT_HOST": 403,
    "NOT_DRAFT_PARTICIPANT": 403,
    # 指名
    "PICK_NOT_ALLOWED": 403,
    "PICK_ALREADY_SUBMITTED": 409,
    "PICKS_NOT_COMPLETE": 409,
    "PLAYER_NOT_FOUND": 404,
    "PLAYER_ALREADY_TAKEN": 409,
    # 女性枠ルール（DESIGN.md §4.3）
    "FEMALE_REQUIRED": 409,
    "FEMALE_SURPLUS_EXHAUSTED": 409,
    # 選手マスタ
    "ML_PLAYERS_NOT_SEEDED": 500,
    # 成績追跡（DESIGN.md §4.8）
    "MLEAGUE_FETCH_FAILED": 502,
    "REFRESH_IN_PROGRESS": 409,
}


def draft_error(code: str, message: str) -> dict:
    return error_response(code, message, status_code=_DRAFT_STATUS_BY_CODE[code])


class DraftError(Exception):
    """ハンドラーの深いところから中断するための例外。

    `handler.py`のディスパッチャで`draft_error`に変換する。
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
