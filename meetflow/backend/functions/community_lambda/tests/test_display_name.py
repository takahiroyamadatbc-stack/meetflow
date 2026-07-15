from meetflow_common import get_display_name, is_display_name_taken, resolve_display_name

from _factories import put_membership, put_profile


def test_resolve_display_name_prefers_membership_display_name():
    assert resolve_display_name({"displayName": "たか"}, {"nickname": "たかし"}) == "たか"


def test_resolve_display_name_falls_back_to_nickname_when_unset():
    assert resolve_display_name({}, {"nickname": "たかし"}) == "たかし"


def test_resolve_display_name_handles_none_items():
    assert resolve_display_name(None, {"nickname": "たかし"}) == "たかし"
    assert resolve_display_name(None, None) == ""


def test_get_display_name_reads_from_table_with_display_name(table):
    put_membership(table, "community-1", "user-1", display_name="たか")
    put_profile(table, "user-1", nickname="たかし")
    assert get_display_name(table, "community-1", "user-1") == "たか"


def test_get_display_name_reads_from_table_without_display_name(table):
    put_membership(table, "community-1", "user-1")
    put_profile(table, "user-1", nickname="たかし")
    assert get_display_name(table, "community-1", "user-1") == "たかし"


def test_is_display_name_taken_matches_other_members_display_name(table):
    put_membership(table, "community-1", "user-1")
    put_membership(table, "community-1", "user-2", display_name="けん")
    assert is_display_name_taken(table, "community-1", "けん", exclude_user_id="user-1") is True


def test_is_display_name_taken_matches_other_members_fallback_nickname(table):
    """displayNameだけでなく、未設定メンバーの実効nicknameとの重複も検知する"""
    put_membership(table, "community-1", "user-1")
    put_membership(table, "community-1", "user-2")  # displayName未設定
    put_profile(table, "user-2", nickname="けん")
    assert is_display_name_taken(table, "community-1", "けん", exclude_user_id="user-1") is True


def test_is_display_name_taken_excludes_self(table):
    put_membership(table, "community-1", "user-1", display_name="けん")
    assert is_display_name_taken(table, "community-1", "けん", exclude_user_id="user-1") is False


def test_is_display_name_taken_returns_false_when_no_match(table):
    put_membership(table, "community-1", "user-1")
    put_membership(table, "community-1", "user-2", display_name="けん")
    assert is_display_name_taken(table, "community-1", "みらい", exclude_user_id="user-1") is False
