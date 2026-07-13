import pytest

from handlers import places

from _factories import api_event, body_of, put_community, put_membership


def test_list_places_success(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    places.create_place(
        "user-1",
        api_event(path_params={"communityId": "community-1"}, body={"name": "雀荘A"}),
    )

    response = places.list_places(
        "user-1", api_event(path_params={"communityId": "community-1"})
    )

    assert response["statusCode"] == 200
    places_list = body_of(response)["data"]["places"]
    assert len(places_list) == 1
    assert places_list[0]["name"] == "雀荘A"


def test_create_place_success(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = places.create_place(
        "user-1",
        api_event(
            path_params={"communityId": "community-1"},
            body={"name": "雀荘A", "address": "東京都渋谷区"},
        ),
    )

    assert response["statusCode"] == 201
    data = body_of(response)["data"]
    assert data["name"] == "雀荘A"
    assert data["address"] == "東京都渋谷区"
    place_id = data["placeId"]

    stored = table.get_item(Key={"PK": f"PLACE#{place_id}", "SK": "METADATA"})["Item"]
    assert stored["ownerType"] == "COMMUNITY"
    assert stored["ownerId"] == "community-1"


@pytest.mark.parametrize("name", ["", "a" * 51])
def test_create_place_invalid_name(table, name):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = places.create_place(
        "user-1",
        api_event(path_params={"communityId": "community-1"}, body={"name": name}),
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "INVALID_PARAMETER"
