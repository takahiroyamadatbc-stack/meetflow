"""チップ記録（Issue #116）。

チップを半荘（GameSession）に紐付けず、イベント単位で好きなタイミングで
何回でも記録できるようにする。1回の記録（ChipRecord）は、その時点で
精算したチップ枚数を参加者ごとに持つ。

    ChipRecord（記録本体）: PK=EVENT#{eventId}, SK=CHIPREC#{recordNo}
    ChipRecordChip（参加者ごとの行）: PK=EVENT#{eventId}, SK=CHIPREC#{recordNo}#CHIP#{userId}

参加者ごとの行はGameResultChip（SESSION#{sessionNo}#CHIP#{userId}）と同じ
GSI1/GSI2のキー形式・属性（chipCount/playedAt/gameType）で保存する。個人成績
（get_user_results）・ランキング（get_community_ranking）はSKに`#CHIP#`を含む
行をチップとして集計するため、既存の半荘ごとのチップと同じ扱いで自動的に
集計対象になる。

チップの合計が±0でない記録も登録できる（警告はフロントで表示する）。
登録はコミュニティのアクティブなメンバーなら誰でも、編集・削除はOWNER/ADMIN
限定（半荘の登録・編集・削除と同じ権限方針）。
"""

from boto3.dynamodb.conditions import Key

from meetflow_common import (
    error_response,
    get_table,
    now_iso_ms,
    parse_body,
    require_membership,
    success_response,
    transact_write,
    write_operation_log,
)

_GAME_TYPES = ("MAHJONG4", "MAHJONG3")


def create_chip_record(user_id, event):
    """POST /events/{eventId}/chip-records"""
    event_id = event["pathParameters"]["eventId"]
    table = get_table()
    community_id, error = _event_community_id(table, event_id)
    if error:
        return error
    require_membership(table, community_id, user_id)

    body = parse_body(event)
    validation_error = _validate_body(body)
    if validation_error:
        return validation_error

    record_no = _next_record_no(table, event_id)
    record_item, chip_items = _build_items(
        event_id, community_id, record_no, body, recorded_at=now_iso_ms(), user_id=user_id
    )
    transact_write([{"Put": {"Item": item}} for item in [record_item, *chip_items]])

    write_operation_log(
        action="CREATE_CHIP_RECORD",
        user_id=user_id,
        community_id=community_id,
        target_type="ChipRecord",
        target_id=record_no,
    )
    return success_response(
        _build_response(event_id, record_item, chip_items), status_code=201
    )


def list_chip_records(user_id, event):
    """GET /events/{eventId}/chip-records（記録順）"""
    event_id = event["pathParameters"]["eventId"]
    table = get_table()
    community_id, error = _event_community_id(table, event_id)
    if error:
        return error
    require_membership(table, community_id, user_id)

    items = _query_all(table, event_id, "CHIPREC#")
    records = {}
    for item in items:
        parts = item["SK"].split("#")
        bucket = records.setdefault(parts[1], {"meta": None, "chips": []})
        if len(parts) == 2:
            bucket["meta"] = item
        elif len(parts) == 4 and parts[2] == "CHIP":
            bucket["chips"].append(item)

    return success_response(
        {
            "records": [
                _build_response(event_id, records[no]["meta"], records[no]["chips"])
                for no in sorted(records)
                if records[no]["meta"] is not None
            ]
        }
    )


def update_chip_record(user_id, event):
    """PUT /events/{eventId}/chip-records/{recordNo}（OWNER/ADMIN）。

    記録の内容（種目・参加者ごとの枚数）をまとめて置き換える。記録日時
    （recordedAt）は登録時のまま変えない（期間指定のランキング集計が
    編集で別の期間に移らないようにするため）。外された参加者の行は削除する。
    """
    event_id = event["pathParameters"]["eventId"]
    record_no = event["pathParameters"]["recordNo"]
    table = get_table()
    community_id, error = _event_community_id(table, event_id)
    if error:
        return error
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    existing_items = _record_items(table, event_id, record_no)
    existing_meta = next(
        (item for item in existing_items if item["SK"] == f"CHIPREC#{record_no}"), None
    )
    if existing_meta is None:
        return _not_found()

    body = parse_body(event)
    validation_error = _validate_body(body)
    if validation_error:
        return validation_error

    record_item, chip_items = _build_items(
        event_id,
        community_id,
        record_no,
        body,
        recorded_at=existing_meta["recordedAt"],
        user_id=existing_meta.get("createdBy"),
    )
    new_sks = {item["SK"] for item in chip_items}
    operations = [{"Put": {"Item": item}} for item in [record_item, *chip_items]]
    operations += [
        {"Delete": {"Key": {"PK": item["PK"], "SK": item["SK"]}}}
        for item in existing_items
        if item["SK"] != record_item["SK"] and item["SK"] not in new_sks
    ]
    transact_write(operations)

    write_operation_log(
        action="UPDATE_CHIP_RECORD",
        user_id=user_id,
        community_id=community_id,
        target_type="ChipRecord",
        target_id=record_no,
    )
    return success_response(_build_response(event_id, record_item, chip_items))


def delete_chip_record(user_id, event):
    """DELETE /events/{eventId}/chip-records/{recordNo}（OWNER/ADMIN）"""
    event_id = event["pathParameters"]["eventId"]
    record_no = event["pathParameters"]["recordNo"]
    table = get_table()
    community_id, error = _event_community_id(table, event_id)
    if error:
        return error
    require_membership(table, community_id, user_id, roles=("OWNER", "ADMIN"))

    items = _record_items(table, event_id, record_no)
    if not any(item["SK"] == f"CHIPREC#{record_no}" for item in items):
        return _not_found()

    transact_write(
        [{"Delete": {"Key": {"PK": item["PK"], "SK": item["SK"]}}} for item in items]
    )

    write_operation_log(
        action="DELETE_CHIP_RECORD",
        user_id=user_id,
        community_id=community_id,
        target_type="ChipRecord",
        target_id=record_no,
    )
    return success_response({"eventId": event_id, "recordNo": record_no})


def _event_community_id(table, event_id):
    event_item = table.get_item(Key={"PK": f"EVENT#{event_id}", "SK": "METADATA"}).get(
        "Item"
    )
    if event_item is None:
        return None, error_response("EVENT_NOT_FOUND", "指定したイベントが見つかりません")
    return event_item["GSI1PK"].split("#", 1)[1], None


def _validate_body(body):
    if not isinstance(body, dict):
        return error_response("RESULT_VALIDATION_ERROR", "リクエスト内容が不正です")
    if body.get("gameType") not in _GAME_TYPES:
        return error_response("RESULT_VALIDATION_ERROR", "gameTypeが不正です")

    chips = body.get("chips")
    if not isinstance(chips, list) or not chips:
        return error_response("RESULT_VALIDATION_ERROR", "chipsが不正です")
    user_ids = []
    for c in chips:
        if (
            not isinstance(c, dict)
            or not isinstance(c.get("userId"), str)
            or not isinstance(c.get("chipCount"), int)
            or isinstance(c.get("chipCount"), bool)
        ):
            return error_response("RESULT_VALIDATION_ERROR", "chipsの形式が不正です")
        user_ids.append(c["userId"])
    if len(user_ids) != len(set(user_ids)):
        return error_response("RESULT_VALIDATION_ERROR", "参加者が重複しています")
    return None


def _build_items(event_id, community_id, record_no, body, recorded_at, user_id):
    game_type = body["gameType"]
    record_item = {
        "PK": f"EVENT#{event_id}",
        "SK": f"CHIPREC#{record_no}",
        "gameType": game_type,
        "recordedAt": recorded_at,
    }
    if user_id:
        record_item["createdBy"] = user_id
    chip_items = [
        {
            "PK": f"EVENT#{event_id}",
            "SK": f"CHIPREC#{record_no}#CHIP#{c['userId']}",
            # GameResultChipと同じキー形式（DynamoDB物理設計書v1.25 §3.13b）
            "GSI1PK": f"USER#{c['userId']}",
            "GSI1SK": f"COMMUNITY#{community_id}#{recorded_at}",
            "GSI2PK": f"COMMUNITY#{community_id}#{game_type}",
            "GSI2SK": recorded_at,
            "chipCount": c["chipCount"],
            "playedAt": recorded_at,
            "gameType": game_type,
        }
        for c in body["chips"]
    ]
    return record_item, chip_items


def _build_response(event_id, record_item, chip_items):
    chips = [
        {"userId": c["SK"].rsplit("#", 1)[1], "chipCount": int(c["chipCount"])}
        for c in chip_items
    ]
    return {
        "eventId": event_id,
        "recordNo": record_item["SK"].split("#")[1],
        "gameType": record_item["gameType"],
        "recordedAt": record_item["recordedAt"],
        "chips": chips,
        "chipTotal": sum(c["chipCount"] for c in chips),
    }


def _record_items(table, event_id, record_no):
    # begins_with(CHIPREC#{recordNo})だけだと桁違いの番号（0001と00011）も
    # 拾いうるため、本体と`#`区切りの子行だけに絞る。
    return [
        item
        for item in _query_all(table, event_id, f"CHIPREC#{record_no}")
        if item["SK"] == f"CHIPREC#{record_no}"
        or item["SK"].startswith(f"CHIPREC#{record_no}#")
    ]


def _query_all(table, event_id, sk_prefix):
    key_condition = Key("PK").eq(f"EVENT#{event_id}") & Key("SK").begins_with(sk_prefix)
    resp = table.query(KeyConditionExpression=key_condition)
    items = resp.get("Items", [])
    while "LastEvaluatedKey" in resp:
        resp = table.query(
            KeyConditionExpression=key_condition,
            ExclusiveStartKey=resp["LastEvaluatedKey"],
        )
        items.extend(resp.get("Items", []))
    return items


def _next_record_no(table, event_id):
    existing_nos = {
        int(item["SK"].split("#")[1])
        for item in _query_all(table, event_id, "CHIPREC#")
        if len(item["SK"].split("#")) == 2
    }
    return f"{max(existing_nos, default=0) + 1:04d}"


def _not_found():
    return error_response("CHIP_RECORD_NOT_FOUND", "指定したチップ記録が見つかりません")
