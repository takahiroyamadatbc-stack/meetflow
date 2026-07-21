import pytest

from meetflow_common import AuthError, now_iso_ms

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


def _create_place(table, community_id, user_id, **body):
    response = places.create_place(
        user_id,
        api_event(path_params={"communityId": community_id}, body={"name": "雀荘A", **body}),
    )
    return body_of(response)["data"]["placeId"]


def _put_event(table, community_id, place_id, event_id, *, status):
    table.put_item(
        Item={
            "PK": f"EVENT#{event_id}",
            "SK": "METADATA",
            "GSI1PK": f"COMMUNITY#{community_id}",
            "GSI1SK": f"EVENT#{event_id}",
            "locationId": place_id,
            "status": status,
            "startTime": now_iso_ms(),
        }
    )


def test_update_place_success(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    place_id = _create_place(table, "community-1", "user-1")

    response = places.update_place(
        "user-1",
        api_event(
            path_params={"communityId": "community-1", "placeId": place_id},
            body={"name": "雀荘B", "address": "大阪府大阪市", "note": "駅近"},
        ),
    )

    assert response["statusCode"] == 200
    data = body_of(response)["data"]
    assert data["name"] == "雀荘B"
    assert data["address"] == "大阪府大阪市"
    assert data["note"] == "駅近"


def test_update_place_not_found(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = places.update_place(
        "user-1",
        api_event(
            path_params={"communityId": "community-1", "placeId": "unknown"},
            body={"name": "雀荘B"},
        ),
    )

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "LOCATION_NOT_FOUND"


def test_update_place_forbidden_for_member(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    put_membership(table, "community-1", "user-2", role="MEMBER")
    place_id = _create_place(table, "community-1", "user-1")

    with pytest.raises(AuthError):
        places.update_place(
            "user-2",
            api_event(
                path_params={"communityId": "community-1", "placeId": place_id},
                body={"name": "雀荘B"},
            ),
        )


def test_update_place_invalid_name(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    place_id = _create_place(table, "community-1", "user-1")

    response = places.update_place(
        "user-1",
        api_event(
            path_params={"communityId": "community-1", "placeId": place_id},
            body={"name": ""},
        ),
    )

    assert response["statusCode"] == 400
    assert body_of(response)["error"]["code"] == "INVALID_PARAMETER"


def test_delete_place_success(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    place_id = _create_place(table, "community-1", "user-1")

    response = places.delete_place(
        "user-1",
        api_event(path_params={"communityId": "community-1", "placeId": place_id}),
    )

    assert response["statusCode"] == 200
    stored = table.get_item(Key={"PK": f"PLACE#{place_id}", "SK": "METADATA"}).get("Item")
    assert stored is None


def test_delete_place_not_found(table):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")

    response = places.delete_place(
        "user-1",
        api_event(path_params={"communityId": "community-1", "placeId": "unknown"}),
    )

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "LOCATION_NOT_FOUND"


@pytest.mark.parametrize("status", ["OPEN", "CONFIRMED", "IN_PROGRESS"])
def test_delete_place_blocked_when_in_use(table, status):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    place_id = _create_place(table, "community-1", "user-1")
    _put_event(table, "community-1", place_id, "event-1", status=status)

    response = places.delete_place(
        "user-1",
        api_event(path_params={"communityId": "community-1", "placeId": place_id}),
    )

    assert response["statusCode"] == 409
    assert body_of(response)["error"]["code"] == "LOCATION_IN_USE"


@pytest.mark.parametrize("status", ["CANCELLED", "COMPLETED"])
def test_delete_place_allowed_when_only_inactive_events(table, status):
    put_community(table, "community-1", owner_id="user-1")
    put_membership(table, "community-1", "user-1", role="OWNER")
    place_id = _create_place(table, "community-1", "user-1")
    _put_event(table, "community-1", place_id, "event-1", status=status)

    response = places.delete_place(
        "user-1",
        api_event(path_params={"communityId": "community-1", "placeId": place_id}),
    )

    assert response["statusCode"] == 200
