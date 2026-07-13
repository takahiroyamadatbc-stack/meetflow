import pytest
from meetflow_common import AuthError, add_days_iso, now_iso_ms

from handlers import matching

from _factories import api_event, body_of, put_availability, put_membership, put_template

_START = add_days_iso(now_iso_ms(), 5)
_END = add_days_iso(now_iso_ms(), 5)  # 同日枠。厳密な値はグルーピングロジックで使用しない


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
    member_ids = {m["userId"] for m in candidates[0]["members"]}
    assert member_ids == {"user-1", "user-2", "user-3", "user-4"}


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


def test_get_candidate_detail_not_found(table):
    response = matching.get_candidate_detail(
        "user-1", api_event(path_params={"candidateId": "does-not-exist"})
    )

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "CANDIDATE_NOT_FOUND"
