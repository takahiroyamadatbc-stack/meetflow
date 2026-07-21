from datetime import datetime, timedelta

import pytest
from meetflow_common import AuthError, add_days_iso, now_iso_ms

from handlers import matching

from _factories import (
    api_event,
    body_of,
    put_availability,
    put_community,
    put_membership,
    put_participant,
    put_profile,
    put_template,
)


def _add_hours_iso(base_iso, hours):
    dt = datetime.fromisoformat(base_iso.replace("Z", "+00:00")) + timedelta(hours=hours)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


_START = add_days_iso(now_iso_ms(), 5)
_END = _add_hours_iso(_START, 4)  # #9: 交差区間計算が意味を持つよう、開始より後の時刻にする


def _seed_matching_group(table, community_id, user_ids, *, game_type="MAHJONG4"):
    """空き予定の登録のみを行う -- 呼び出し元は既に自分でmembershipを
    セットアップ済みであることを期待する（例: generate_candidatesを呼び
    出すOWNERは別途put_membershipを呼んでおく）。ここでmembershipを
    再登録すると、既にMEMBER以外のroleを持つユーザーの場合、それを
    黙って上書きしてしまうため。
    """
    for uid in user_ids:
        put_availability(
            table,
            community_id,
            uid,
            start_time=_START,
            end_time=_END,
            game_types=[game_type],
            availability_id=f"avail-{uid}",
        )


def test_generate_candidates_success(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_template(table, "community-1", "template-1", min_players=4, max_players=4)
    _seed_matching_group(table, "community-1", ["user-1", "user-2", "user-3", "user-4"])

    response = matching.generate_candidates(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"templateId": "template-1"}
        ),
    )

    assert response["statusCode"] == 201
    candidates = body_of(response)["data"]["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["status"] == "PENDING"
    assert candidates[0]["startTime"] == _START
    assert candidates[0]["endTime"] == _END
    member_ids = {m["userId"] for m in candidates[0]["members"]}
    assert member_ids == {"user-1", "user-2", "user-3", "user-4"}


def test_generate_candidates_ignores_stale_min_players_1_template(table):
    """Issue #57: `_validate`はminPlayers>=2を強制するが、既に保存済みの
    minPlayers=1のテンプレート（過去データ）が万一残っていても、1人だけの
    空き区間が候補化されない（下限2のガードがマッチング処理側にもある）
    ことを確認する二重防御のテスト。"""
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_template(table, "community-1", "template-1", min_players=1, max_players=1)
    _seed_matching_group(table, "community-1", ["user-1"])

    response = matching.generate_candidates(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"templateId": "template-1"}
        ),
    )

    assert response["statusCode"] == 201
    assert body_of(response)["data"]["candidates"] == []


def test_generate_candidates_with_overlapping_but_not_identical_times(table):
    """#9: 全員の空き予定が寸分違わず一致しなくても、共通する時間帯が
    存在すれば候補が成立すること（例：Aは11:00〜13:00、Bは12:00〜14:00
    なら12:00〜13:00が共通区間として候補になる）。
    """
    day = _START[:10]
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_template(table, "community-1", "template-1", min_players=2, max_players=2)
    put_availability(
        table,
        "community-1",
        "user-1",
        start_time=f"{day}T11:00:00.000Z",
        end_time=f"{day}T13:00:00.000Z",
        game_types=["MAHJONG4"],
        availability_id="avail-user-1",
    )
    put_availability(
        table,
        "community-1",
        "user-2",
        start_time=f"{day}T12:00:00.000Z",
        end_time=f"{day}T14:00:00.000Z",
        game_types=["MAHJONG4"],
        availability_id="avail-user-2",
    )

    response = matching.generate_candidates(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"templateId": "template-1"}
        ),
    )

    assert response["statusCode"] == 201
    candidates = body_of(response)["data"]["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["startTime"] == f"{day}T12:00:00.000Z"
    assert candidates[0]["endTime"] == f"{day}T13:00:00.000Z"
    member_ids = {m["userId"] for m in candidates[0]["members"]}
    assert member_ids == {"user-1", "user-2"}


def test_generate_candidates_no_overlap_no_candidate(table):
    """空き予定同士に共通区間が全く無ければ候補は生成されない。"""
    day = _START[:10]
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_template(table, "community-1", "template-1", min_players=2, max_players=2)
    put_availability(
        table,
        "community-1",
        "user-1",
        start_time=f"{day}T11:00:00.000Z",
        end_time=f"{day}T12:00:00.000Z",
        game_types=["MAHJONG4"],
        availability_id="avail-user-1",
    )
    put_availability(
        table,
        "community-1",
        "user-2",
        start_time=f"{day}T12:00:00.000Z",
        end_time=f"{day}T13:00:00.000Z",
        game_types=["MAHJONG4"],
        availability_id="avail-user-2",
    )

    response = matching.generate_candidates(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"templateId": "template-1"}
        ),
    )

    assert response["statusCode"] == 201
    assert body_of(response)["data"]["candidates"] == []


def test_generate_candidates_with_timezone_naive_past_participation(table):
    """dev環境で実際に発生した回帰テスト: ユーザーの空き予定startTimeは
    タイムゾーン表記を伴わない文字列（例："2026-07-25T19:00"）がそのまま
    Participant.GSI1SKに使われる。そのユーザーについて再度候補生成する際、
    _days_since_last_participationがoffset-naive/offset-awareの減算で
    TypeErrorになり、候補生成API全体が500になっていた。
    """
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_template(table, "community-1", "template-1", min_players=4, max_players=4)
    _seed_matching_group(table, "community-1", ["user-1", "user-2", "user-3", "user-4"])
    put_participant(
        table, "past-event-1", "user-1", start_time="2020-01-01T19:00", end_time="2020-01-01T23:00"
    )

    response = matching.generate_candidates(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"templateId": "template-1"}
        ),
    )

    assert response["statusCode"] == 201


def test_generate_candidates_uses_display_name_when_set(table):
    put_membership(table, "community-1", "user-1", role="OWNER", display_name="たか")
    put_template(table, "community-1", "template-1", min_players=4, max_players=4)
    _seed_matching_group(table, "community-1", ["user-1", "user-2", "user-3", "user-4"])

    response = matching.generate_candidates(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"templateId": "template-1"}
        ),
    )

    candidates = body_of(response)["data"]["candidates"]
    nicknames = {m["userId"]: m["nickname"] for m in candidates[0]["members"]}
    assert nicknames["user-1"] == "たか"


def test_generate_candidates_penalizes_member_over_frequency_limit(table):
    """Issue #19: 参加頻度上限に達しているメンバーがいる場合、成立理由に
    その旨が明記されること。カウントはコミュニティ横断で行われるため
    （要件定義書v1.7 §30.4）、過去の参加履歴のイベントは候補生成対象の
    コミュニティとは無関係なIDでも判定に含まれる。
    """
    put_community(table, "community-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_template(table, "community-1", "template-1", min_players=4, max_players=4)
    _seed_matching_group(table, "community-1", ["user-1", "user-2", "user-3", "user-4"])
    put_profile(table, "user-1", frequency_limit_count=1, frequency_limit_period="WEEK")
    put_participant(
        table,
        "past-event-in-other-community",
        "user-1",
        start_time=add_days_iso(_START, -1),
        end_time=add_days_iso(_START, -1),
        status="CONFIRMED",
        community_genre="麻雀",
    )

    response = matching.generate_candidates(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"templateId": "template-1"}
        ),
    )

    candidate = body_of(response)["data"]["candidates"][0]
    assert any("上限" in r for r in candidate["reasons"])


def test_generate_candidates_frequency_limit_not_exceeded_when_under_count(table):
    put_community(table, "community-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_template(table, "community-1", "template-1", min_players=4, max_players=4)
    _seed_matching_group(table, "community-1", ["user-1", "user-2", "user-3", "user-4"])
    put_profile(table, "user-1", frequency_limit_count=2, frequency_limit_period="WEEK")
    put_participant(
        table,
        "past-event-1",
        "user-1",
        start_time=add_days_iso(_START, -1),
        end_time=add_days_iso(_START, -1),
        status="CONFIRMED",
        community_genre="麻雀",
    )

    response = matching.generate_candidates(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"templateId": "template-1"}
        ),
    )

    candidate = body_of(response)["data"]["candidates"][0]
    assert not any("上限" in r for r in candidate["reasons"])


def test_generate_candidates_frequency_limit_ignores_other_genre(table):
    put_community(table, "community-1", genre="麻雀")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_template(table, "community-1", "template-1", min_players=4, max_players=4)
    _seed_matching_group(table, "community-1", ["user-1", "user-2", "user-3", "user-4"])
    put_profile(table, "user-1", frequency_limit_count=1, frequency_limit_period="WEEK")
    put_participant(
        table,
        "past-event-1",
        "user-1",
        start_time=add_days_iso(_START, -1),
        end_time=add_days_iso(_START, -1),
        status="CONFIRMED",
        community_genre="ボードゲーム",
    )

    response = matching.generate_candidates(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"templateId": "template-1"}
        ),
    )

    candidate = body_of(response)["data"]["candidates"][0]
    assert not any("上限" in r for r in candidate["reasons"])


def test_generate_candidates_template_not_found(table):
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = matching.generate_candidates(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"templateId": "no-such"}
        ),
    )

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "EVENT_TEMPLATE_NOT_FOUND"


def test_generate_candidates_missing_template_id(table):
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = matching.generate_candidates(
        "user-1", api_event(path_params={"communityId": "community-1"}, body={})
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "INVALID_PARAMETER"


def test_generate_candidates_forbidden_for_plain_member(table):
    put_membership(table, "community-1", "user-2", role="MEMBER")

    with pytest.raises(AuthError) as exc_info:
        matching.generate_candidates(
            "user-2",
            api_event(
                path_params={"communityId": "community-1"},
                body={"templateId": "template-1"},
            ),
        )
    assert exc_info.value.code == "FORBIDDEN"


def _get_candidate_item(table, candidate_id):
    from boto3.dynamodb.conditions import Key

    resp = table.query(
        IndexName="GSI2",
        KeyConditionExpression=Key("GSI2PK").eq(f"CANDIDATE#{candidate_id}"),
        Limit=1,
    )
    return resp["Items"][0]


def test_generate_candidates_reuses_identical_candidate_on_regeneration(table):
    """Issue #84: 内容(開始/終了時刻・メンバー構成)が完全一致する再生成では、
    新規レコードを作らず既存候補をPENDINGへ復活させ、candidateIdを使い回す。
    """
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_template(table, "community-1", "template-1", min_players=4, max_players=4)
    _seed_matching_group(table, "community-1", ["user-1", "user-2", "user-3", "user-4"])

    first_response = matching.generate_candidates(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"templateId": "template-1"}
        ),
    )
    first_candidate = body_of(first_response)["data"]["candidates"][0]
    first_candidate_id = first_candidate["candidateId"]
    first_created_at = first_candidate["createdAt"]

    second_response = matching.generate_candidates(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"templateId": "template-1"}
        ),
    )
    second_candidates = body_of(second_response)["data"]["candidates"]
    assert len(second_candidates) == 1
    assert second_candidates[0]["candidateId"] == first_candidate_id
    # 復活時にcreatedAtを今回の再生成時刻へ更新する（Issue #84のQ&Aで確認済み）。
    assert second_candidates[0]["createdAt"] > first_created_at

    revived_item = _get_candidate_item(table, first_candidate_id)
    assert revived_item["status"] == "PENDING"

    for user_id in [m["userId"] for m in first_candidate["members"]]:
        member_item = table.get_item(
            Key={
                "PK": "COMMUNITY#community-1",
                "SK": f"CANDIDATE#{first_candidate_id}#MEMBER#{user_id}",
            }
        )["Item"]
        assert member_item["status"] == "PENDING"


def test_generate_candidates_discards_stale_pending_when_content_changes(table):
    """Issue #27: 完全一致しない（内容が変わった）場合は、従来通り既存
    PENDING候補をDISCARDEDにする。Issue #84の再利用ロジック導入後も、
    元の重複防止機能自体は維持されていることを確認する。
    """
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_template(table, "community-1", "template-1", min_players=4, max_players=4)
    _seed_matching_group(table, "community-1", ["user-1", "user-2", "user-3", "user-4"])

    first_response = matching.generate_candidates(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"templateId": "template-1"}
        ),
    )
    first_candidate_id = body_of(first_response)["data"]["candidates"][0]["candidateId"]

    # 空き予定の終了時刻を延長し、次の生成結果が完全一致しなくなるようにする。
    extended_end = _add_hours_iso(_END, 1)
    for uid in ["user-1", "user-2", "user-3", "user-4"]:
        put_availability(
            table,
            "community-1",
            uid,
            start_time=_START,
            end_time=extended_end,
            game_types=["MAHJONG4"],
            availability_id=f"avail-{uid}",
        )

    second_response = matching.generate_candidates(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"templateId": "template-1"}
        ),
    )
    second_candidates = body_of(second_response)["data"]["candidates"]
    assert len(second_candidates) == 1
    assert second_candidates[0]["candidateId"] != first_candidate_id
    assert second_candidates[0]["endTime"] == extended_end

    stale_item = _get_candidate_item(table, first_candidate_id)
    assert stale_item["status"] == "DISCARDED"

    for user_id in ["user-1", "user-2", "user-3", "user-4"]:
        member_item = table.get_item(
            Key={
                "PK": "COMMUNITY#community-1",
                "SK": f"CANDIDATE#{first_candidate_id}#MEMBER#{user_id}",
            }
        )["Item"]
        assert member_item["status"] == "DISCARDED"


def test_generate_candidates_does_not_discard_confirmed_candidate(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_template(table, "community-1", "template-1", min_players=4, max_players=4)
    _seed_matching_group(table, "community-1", ["user-1", "user-2", "user-3", "user-4"])

    first_response = matching.generate_candidates(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"templateId": "template-1"}
        ),
    )
    first_candidate_id = body_of(first_response)["data"]["candidates"][0]["candidateId"]
    stale_item = _get_candidate_item(table, first_candidate_id)
    table.update_item(
        Key={"PK": stale_item["PK"], "SK": stale_item["SK"]},
        UpdateExpression="SET #status = :confirmed",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={":confirmed": "CONFIRMED"},
    )

    matching.generate_candidates(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"templateId": "template-1"}
        ),
    )

    confirmed_item = _get_candidate_item(table, first_candidate_id)
    assert confirmed_item["status"] == "CONFIRMED"


def test_generate_candidates_discard_scoped_to_template(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_template(table, "community-1", "template-1", min_players=4, max_players=4)
    put_template(
        table, "community-1", "template-2", min_players=4, max_players=4, game_type="MAHJONG3"
    )
    _seed_matching_group(table, "community-1", ["user-1", "user-2", "user-3", "user-4"])
    _seed_matching_group(
        table,
        "community-1",
        ["user-1", "user-2", "user-3", "user-4"],
        game_type="MAHJONG3",
    )

    response_1 = matching.generate_candidates(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"templateId": "template-1"}
        ),
    )
    response_2 = matching.generate_candidates(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"templateId": "template-2"}
        ),
    )
    candidate_2_id = body_of(response_2)["data"]["candidates"][0]["candidateId"]

    # template-1のみ再生成。template-2の候補はPENDINGのまま影響を受けない。
    matching.generate_candidates(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"templateId": "template-1"}
        ),
    )

    unaffected_item = _get_candidate_item(table, candidate_2_id)
    assert unaffected_item["status"] == "PENDING"


def test_list_candidates_success(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_template(table, "community-1", "template-1", min_players=4, max_players=4)
    _seed_matching_group(table, "community-1", ["user-1", "user-2", "user-3", "user-4"])
    matching.generate_candidates(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"templateId": "template-1"}
        ),
    )

    response = matching.list_candidates(
        "user-1", api_event(path_params={"communityId": "community-1"})
    )

    assert response["statusCode"] == 200
    candidates = body_of(response)["data"]["candidates"]
    assert len(candidates) == 1


def test_get_candidate_detail_success(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_template(table, "community-1", "template-1", min_players=4, max_players=4)
    _seed_matching_group(table, "community-1", ["user-1", "user-2", "user-3", "user-4"])
    create_response = matching.generate_candidates(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"templateId": "template-1"}
        ),
    )
    candidate_id = body_of(create_response)["data"]["candidates"][0]["candidateId"]

    response = matching.get_candidate_detail(
        "user-1", api_event(path_params={"candidateId": candidate_id})
    )

    assert response["statusCode"] == 200
    assert body_of(response)["data"]["candidateId"] == candidate_id


def test_list_candidates_includes_created_at(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_template(table, "community-1", "template-1", min_players=4, max_players=4)
    _seed_matching_group(table, "community-1", ["user-1", "user-2", "user-3", "user-4"])
    matching.generate_candidates(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"templateId": "template-1"}
        ),
    )

    response = matching.list_candidates(
        "user-1", api_event(path_params={"communityId": "community-1"})
    )

    candidates = body_of(response)["data"]["candidates"]
    assert len(candidates) == 1
    assert isinstance(candidates[0]["createdAt"], str)
    assert candidates[0]["createdAt"]


def test_get_candidate_detail_includes_created_at(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_template(table, "community-1", "template-1", min_players=4, max_players=4)
    _seed_matching_group(table, "community-1", ["user-1", "user-2", "user-3", "user-4"])
    create_response = matching.generate_candidates(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"}, body={"templateId": "template-1"}
        ),
    )
    candidate_id = body_of(create_response)["data"]["candidates"][0]["candidateId"]

    response = matching.get_candidate_detail(
        "user-1", api_event(path_params={"candidateId": candidate_id})
    )

    data = body_of(response)["data"]
    assert isinstance(data["createdAt"], str)
    assert data["createdAt"]


def test_get_candidate_detail_not_found(table):
    response = matching.get_candidate_detail(
        "user-1", api_event(path_params={"candidateId": "does-not-exist"})
    )

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "CANDIDATE_NOT_FOUND"


def test_create_manual_candidate_success(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")

    response = matching.create_manual_candidate(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"},
            body={
                "memberIds": ["user-1", "user-2"],
                "startTime": _START,
                "endTime": _END,
                "gameType": "MAHJONG4",
            },
        ),
    )

    assert response["statusCode"] == 201
    data = body_of(response)["data"]
    assert data["templateId"] is None
    assert data["score"] is None
    assert data["status"] == "PENDING"
    assert data["startTime"] == _START
    assert data["endTime"] == _END
    assert data["gameType"] == "MAHJONG4"
    assert {m["userId"] for m in data["members"]} == {"user-1", "user-2"}

    # 一覧・詳細取得の両方から手動作成候補が取得できること
    list_response = matching.list_candidates(
        "user-1", api_event(path_params={"communityId": "community-1"})
    )
    assert len(body_of(list_response)["data"]["candidates"]) == 1

    detail_response = matching.get_candidate_detail(
        "user-1", api_event(path_params={"candidateId": data["candidateId"]})
    )
    assert body_of(detail_response)["data"]["templateId"] is None


def test_create_manual_candidate_invalid_member_ids(table):
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = matching.create_manual_candidate(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"},
            body={"memberIds": [], "startTime": _START, "endTime": _END},
        ),
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "INVALID_PARAMETER"


def test_create_manual_candidate_rejects_non_active_member(table):
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER", status="SUSPENDED")

    response = matching.create_manual_candidate(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"},
            body={
                "memberIds": ["user-1", "user-2"],
                "startTime": _START,
                "endTime": _END,
            },
        ),
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "INVALID_PARAMETER"


def test_create_manual_candidate_invalid_time_range(table):
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = matching.create_manual_candidate(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"},
            body={"memberIds": ["user-1"], "startTime": _END, "endTime": _START},
        ),
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "INVALID_TIME_RANGE"


def test_create_manual_candidate_forbidden_for_plain_member(table):
    put_membership(table, "community-1", "user-1", role="MEMBER")

    with pytest.raises(AuthError) as exc_info:
        matching.create_manual_candidate(
            "user-1",
            api_event(
                path_params={"communityId": "community-1"},
                body={"memberIds": ["user-1"], "startTime": _START, "endTime": _END},
            ),
        )
    assert exc_info.value.code == "FORBIDDEN"
