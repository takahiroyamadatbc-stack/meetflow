import pytest

from meetflow_common import AuthError

from handlers import announcements

from _factories import api_event, body_of


def _create(table, *, title="タイトル", body="本文"):
    resp = announcements.create_announcement(
        "op-1", api_event(body={"title": title, "body": body}, groups=["Operators"])
    )
    return body_of(resp)["data"]["announcementId"]


def test_create_announcement_requires_operator(table):
    with pytest.raises(AuthError) as exc_info:
        announcements.create_announcement(
            "user-1", api_event(body={"title": "t", "body": "b"}, groups=["MEMBER"])
        )
    assert exc_info.value.code == "FORBIDDEN"


def test_create_announcement_defaults_to_draft(table):
    announcement_id = _create(table)
    stored = table.get_item(
        Key={"PK": f"ANNOUNCEMENT#{announcement_id}", "SK": "METADATA"}
    )["Item"]
    assert stored["status"] == "DRAFT"
    assert stored["createdBy"] == "op-1"


def test_list_announcements_hides_drafts_from_general_users(table):
    _create(table)

    resp = announcements.list_announcements("user-1", api_event())
    assert body_of(resp)["data"]["announcements"] == []


def test_list_announcements_includes_all_for_operator(table):
    _create(table)

    resp = announcements.list_announcements(
        "op-1", api_event(query={"includeAll": "true"}, groups=["Operators"])
    )
    assert len(body_of(resp)["data"]["announcements"]) == 1


def test_list_announcements_includes_all_requires_operator(table):
    with pytest.raises(AuthError) as exc_info:
        announcements.list_announcements(
            "user-1", api_event(query={"includeAll": "true"}, groups=["MEMBER"])
        )
    assert exc_info.value.code == "FORBIDDEN"


def test_publish_announcement_makes_it_visible(table):
    announcement_id = _create(table)
    announcements.update_announcement(
        "op-1",
        api_event(
            path_params={"announcementId": announcement_id},
            body={"status": "PUBLISHED"},
            groups=["Operators"],
        ),
    )

    resp = announcements.list_announcements("user-1", api_event())
    items = body_of(resp)["data"]["announcements"]
    assert len(items) == 1
    assert items[0]["status"] == "PUBLISHED"


def test_update_announcement_not_found(table):
    resp = announcements.update_announcement(
        "op-1",
        api_event(
            path_params={"announcementId": "missing"},
            body={"status": "PUBLISHED"},
            groups=["Operators"],
        ),
    )
    assert resp["statusCode"] == 404
    assert body_of(resp)["error"]["code"] == "ANNOUNCEMENT_NOT_FOUND"
