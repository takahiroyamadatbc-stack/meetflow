from unittest.mock import patch

from meetflow_common import AVAILABILITY_UPDATED

from handlers import availability

from _factories import (
    api_event,
    body_of,
    put_availability,
    put_community,
    put_membership,
)

_ENTRY = {
    "startTime": "2026-08-01T10:00:00.000Z",
    "endTime": "2026-08-01T12:00:00.000Z",
    "gameTypes": ["MAHJONG4"],
    "comment": "",
}


def test_create_availability_success(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1")

    response = availability.create_availability(
        "user-1",
        api_event(path_params={"communityId": "community-1"}, body=_ENTRY),
    )

    assert response["statusCode"] == 201
    data = body_of(response)["data"]
    assert data["startTime"] == _ENTRY["startTime"]


def test_list_availability_returns_only_own_entries(table):
    """相互非公開型マッチング（要件定義書v1.4 §29）の実装レベルの担保:
    GET /communities/{communityId}/availabilityは呼び出し元自身の分のみを
    返し、他メンバーの空き予定は一切含まれないこと。
    """
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1")
    put_membership(table, "community-1", "user-2")
    put_availability(
        table,
        "community-1",
        "user-1",
        start_time="2026-08-01T10:00:00.000Z",
        end_time="2026-08-01T12:00:00.000Z",
        availability_id="avail-own",
    )
    put_availability(
        table,
        "community-1",
        "user-2",
        start_time="2026-08-02T10:00:00.000Z",
        end_time="2026-08-02T12:00:00.000Z",
        availability_id="avail-other",
    )

    response = availability.list_availability(
        "user-1",
        api_event(path_params={"communityId": "community-1"}),
    )

    assert response["statusCode"] == 200
    entries = body_of(response)["data"]["availabilities"]
    assert [e["availabilityId"] for e in entries] == ["avail-own"]


def test_list_availability_excludes_other_community(table):
    """GSI1PK=USER#{user_id}は全コミュニティ横断でヒットするため、
    パスパラメータのcommunityIdでの絞り込みが効いていることも確認する。
    """
    put_community(table, "community-1", owner_id="user-1")
    put_community(table, "community-2", owner_id="user-1")
    put_membership(table, "community-1", "user-1")
    put_membership(table, "community-2", "user-1")
    put_availability(
        table,
        "community-1",
        "user-1",
        start_time="2026-08-01T10:00:00.000Z",
        end_time="2026-08-01T12:00:00.000Z",
        availability_id="avail-c1",
    )
    put_availability(
        table,
        "community-2",
        "user-1",
        start_time="2026-08-03T10:00:00.000Z",
        end_time="2026-08-03T12:00:00.000Z",
        availability_id="avail-c2",
    )

    response = availability.list_availability(
        "user-1",
        api_event(path_params={"communityId": "community-1"}),
    )

    entries = body_of(response)["data"]["availabilities"]
    assert [e["availabilityId"] for e in entries] == ["avail-c1"]


def test_create_availability_publishes_availability_updated(table):
    """Issue #97専用の狭い例外：登録の都度AVAILABILITY_UPDATEDを発行する
    （F-401マッチング自動実行のトリガーにはしない、という既存方針とは別物）。
    """
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1")

    with patch.object(availability, "put_event") as mock_put_event:
        availability.create_availability(
            "user-1",
            api_event(path_params={"communityId": "community-1"}, body=_ENTRY),
        )

    mock_put_event.assert_called_once()
    detail_type, detail = mock_put_event.call_args.args
    assert detail_type == AVAILABILITY_UPDATED
    assert detail["communityId"] == "community-1"
    assert detail["userId"] == "user-1"
    assert detail["startTime"] == _ENTRY["startTime"]
    assert detail["endTime"] == _ENTRY["endTime"]


def test_create_availability_batch_publishes_one_event_per_entry(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1")

    with patch.object(availability, "put_event") as mock_put_event:
        availability.create_availability_batch(
            "user-1",
            api_event(
                path_params={"communityId": "community-1"},
                body={
                    "availabilities": [
                        _ENTRY,
                        {**_ENTRY, "startTime": "2026-08-02T10:00:00.000Z", "endTime": "2026-08-02T12:00:00.000Z"},
                    ]
                },
            ),
        )

    assert mock_put_event.call_count == 2


def test_update_availability_publishes_availability_updated(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1")
    created = availability.create_availability(
        "user-1",
        api_event(path_params={"communityId": "community-1"}, body=_ENTRY),
    )
    availability_id = body_of(created)["data"]["availabilityId"]

    with patch.object(availability, "put_event") as mock_put_event:
        availability.update_availability(
            "user-1",
            api_event(
                path_params={"availabilityId": availability_id},
                body={**_ENTRY, "comment": "変更後"},
            ),
        )

    mock_put_event.assert_called_once()
    detail_type, _detail = mock_put_event.call_args.args
    assert detail_type == AVAILABILITY_UPDATED
