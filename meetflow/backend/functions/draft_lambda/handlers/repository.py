"""DraftTableの読み書き。

DESIGN.md §5のキー設計をここに閉じ込め、ハンドラーからは意味のある名前の
関数だけを呼ぶ。キーの組み立てが散らばると、`PICK#{round}#{wave}#{userId}`
のようなゼロ埋め依存のSKを書き間違えたときに気づきにくいため。
"""

from boto3.dynamodb.conditions import Key

from draft_table import get_draft_table

# ドラフトの進行状態（DESIGN.md §4.2）。
STATUS_SETUP = "SETUP"
STATUS_NOMINATING = "NOMINATING"
STATUS_REVEAL = "REVEAL"
STATUS_LOTTERY = "LOTTERY"
STATUS_COMPLETED = "COMPLETED"

PICK_PENDING = "PENDING"
PICK_CONFIRMED = "CONFIRMED"
PICK_LOST = "LOST"


def draft_pk(draft_id: str) -> str:
    return f"DRAFT#{draft_id}"


def pick_sk(round_no: int, wave: int, user_id: str) -> str:
    """巡・waveはSK上で辞書順に並ぶようゼロ埋めする。

    ゼロ埋めしないと `PICK#10#1#u` が `PICK#2#1#u` より前に来てしまい、
    waveごとの範囲クエリが壊れる。
    """
    return f"PICK#{round_no:02d}#{wave:02d}#{user_id}"


def lottery_sk(round_no: int, wave: int, seq: int) -> str:
    return f"LOTTERY#{round_no:02d}#{wave:02d}#{seq:02d}"


def get_draft(draft_id: str):
    resp = get_draft_table().get_item(
        Key={"PK": draft_pk(draft_id), "SK": "METADATA"}
    )
    return resp.get("Item")


def list_community_drafts(community_id: str):
    resp = get_draft_table().query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq(f"COMMUNITY#{community_id}")
        & Key("GSI1SK").begins_with("DRAFT#"),
        ScanIndexForward=False,
    )
    return resp.get("Items", [])


def _query_prefix(draft_id: str, prefix: str):
    items = []
    kwargs = {
        "KeyConditionExpression": Key("PK").eq(draft_pk(draft_id))
        & Key("SK").begins_with(prefix)
    }
    while True:
        resp = get_draft_table().query(**kwargs)
        items.extend(resp.get("Items", []))
        last = resp.get("LastEvaluatedKey")
        if not last:
            return items
        kwargs["ExclusiveStartKey"] = last


def list_participants(draft_id: str):
    return _query_prefix(draft_id, "PARTICIPANT#")


def list_players(draft_id: str):
    """ドラフト作成時に固定した選手マスタのスナップショット。

    DESIGN.md §6.2「選手マスタのスナップショット」: 本体マスタが後から
    変わってもドラフト結果が壊れないよう、作成時にコピーしたものを使う。
    """
    return _query_prefix(draft_id, "PLAYER#")


def list_locks(draft_id: str):
    return _query_prefix(draft_id, "LOCK#")


def list_rosters(draft_id: str):
    return _query_prefix(draft_id, "ROSTER#")


def list_lotteries(draft_id: str):
    return _query_prefix(draft_id, "LOTTERY#")


def list_wave_picks(draft_id: str, round_no: int, wave: int):
    return _query_prefix(draft_id, f"PICK#{round_no:02d}#{wave:02d}#")


def list_round_picks(draft_id: str, round_no: int):
    return _query_prefix(draft_id, f"PICK#{round_no:02d}#")


def list_master_players(season: str):
    """シード済みの選手マスタ（MLPlayer）。ドラフト作成時にだけ読む。"""
    items = []
    kwargs = {
        "KeyConditionExpression": Key("PK").eq(f"MLPLAYER#{season}")
        & Key("SK").begins_with("PLAYER#")
    }
    while True:
        resp = get_draft_table().query(**kwargs)
        items.extend(resp.get("Items", []))
        last = resp.get("LastEvaluatedKey")
        if not last:
            return items
        kwargs["ExclusiveStartKey"] = last


def transact_write(operations: list) -> None:
    """DraftTable版のTransactWriteItems。

    `meetflow_common.transact_write`は本体テーブル固定のため流用できない。
    シリアライズの扱いは共通レイヤー側と同じで、resource-levelのTableを
    経由することでboto3の属性値インジェクタに変換させる。
    """
    table = get_draft_table()
    items = []
    for op in operations:
        op_type, body = next(iter(op.items()))
        body = dict(body)
        body["TableName"] = table.table_name
        items.append({op_type: body})
    table.meta.client.transact_write_items(TransactItems=items)


def draft_state_update(
    *,
    draft_id: str,
    status: str,
    round_no: int,
    wave: int,
    version: int,
    expected_version: int,
    updated_at: str,
    female_surplus_remaining: int = None,
):
    """Draftの進行状態を1つ進めるUpdate操作（TransactWriteItems用のdict）。

    `version`の一致を条件にしているため、主催者がボタンを二度押ししたり
    2画面から同時に操作したりしても、後発は条件チェックで弾かれる
    （DESIGN.md §4.12のリビジョン番号をそのまま楽観ロックに使う）。

    `status` `round` はDynamoDBの予約語なのでExpressionAttributeNames経由で
    参照する。
    """
    names = {
        "#status": "status",
        "#round": "round",
        "#wave": "wave",
        "#version": "version",
    }
    values = {
        ":status": status,
        ":round": round_no,
        ":wave": wave,
        ":version": version,
        ":expectedVersion": expected_version,
        ":updatedAt": updated_at,
    }
    sets = [
        "#status = :status",
        "#round = :round",
        "#wave = :wave",
        "#version = :version",
        "updatedAt = :updatedAt",
    ]
    if female_surplus_remaining is not None:
        sets.append("femaleSurplusRemaining = :surplus")
        values[":surplus"] = female_surplus_remaining
    return {
        "Update": {
            "Key": {"PK": draft_pk(draft_id), "SK": "METADATA"},
            "UpdateExpression": "SET " + ", ".join(sets),
            "ConditionExpression": "#version = :expectedVersion",
            "ExpressionAttributeNames": names,
            "ExpressionAttributeValues": values,
        }
    }


def update_draft_state(**kwargs) -> None:
    """`draft_state_update`を単体で実行する（他の書き込みと束ねない場合）。"""
    transact_write([draft_state_update(**kwargs)])


# --- 成績追跡（DESIGN.md §4.8〜§4.10） ---------------------------------------

# 対局日の状態（DESIGN.md §4.10の3状態）。
#   PLAYED    … 結果を取得済み
#   SCHEDULED … 日程には載っているがまだ消化していない
#   （「対局なし」はアイテムが存在しないことで表す）
GAMEDAY_PLAYED = "PLAYED"
GAMEDAY_SCHEDULED = "SCHEDULED"

SOURCE_OFFICIAL = "OFFICIAL"
SOURCE_MANUAL = "MANUAL"


def season_pk(season: str) -> str:
    return f"MLPLAYER#{season}"


def gameday_sk(date: str, no, seq: int = 0) -> str:
    """節のSK。

    **同じ日付に2節入る日がある**（SCRAPING.md §2.2）ため、日付だけでは
    一意にならない。節番号まで含める。

    未消化日は公式サイトが節番号を載せていない（`data-target`属性ごと無い）
    ため、節番号の代わりに**その日の中での出現順`seq`**を使い、消化済みの
    節番号と混ざらないよう`S`を前置する。ここを未消化なら一律"000"にして
    いたせいで、同じ日に2節ある未消化日でPK/SKが完全に重複し、
    BatchWriteItemがValidationExceptionで全件巻き戻していた。

    未消化のうちに書いた`S`付きのSKは、その日が消化されると節番号側のSKに
    移る。残された`S`付きの行は`_store_results`が消す。
    """
    if no:
        return f"GAMEDAY#{date}#{int(no):03d}"
    return f"GAMEDAY#{date}#S{seq:03d}"


def list_gamedays(season: str) -> list:
    items = []
    kwargs = {
        "KeyConditionExpression": Key("PK").eq(season_pk(season))
        & Key("SK").begins_with("GAMEDAY#")
    }
    while True:
        resp = get_draft_table().query(**kwargs)
        items.extend(resp.get("Items", []))
        last = resp.get("LastEvaluatedKey")
        if not last:
            return items
        kwargs["ExclusiveStartKey"] = last


def get_fetch_state(season: str):
    return get_draft_table().get_item(
        Key={"PK": season_pk(season), "SK": "FETCH_STATE"}
    ).get("Item")


def put_fetch_state(season: str, state: dict) -> None:
    get_draft_table().put_item(
        Item={"PK": season_pk(season), "SK": "FETCH_STATE", "season": season, **state}
    )
