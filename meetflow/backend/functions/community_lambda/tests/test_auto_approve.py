from meetflow_common import get_auto_approve, resolve_auto_approve

from _factories import put_membership, put_profile


def test_resolve_auto_approve_prefers_membership_value():
    assert resolve_auto_approve({"autoApprove": False}, {"autoApprove": True}) is False


def test_resolve_auto_approve_falls_back_to_user_default_when_unset():
    assert resolve_auto_approve({}, {"autoApprove": True}) is True


def test_resolve_auto_approve_defaults_false_when_both_unset():
    assert resolve_auto_approve({}, {}) is False
    assert resolve_auto_approve(None, None) is False


def test_get_auto_approve_reads_membership_override(table):
    put_membership(table, "community-1", "user-1", auto_approve=True)
    put_profile(table, "user-1", auto_approve=False)
    assert get_auto_approve(table, "community-1", "user-1") is True


def test_get_auto_approve_falls_back_to_profile(table):
    put_membership(table, "community-1", "user-1")
    put_profile(table, "user-1", auto_approve=True)
    assert get_auto_approve(table, "community-1", "user-1") is True


def test_get_auto_approve_defaults_false(table):
    put_membership(table, "community-1", "user-1")
    put_profile(table, "user-1")
    assert get_auto_approve(table, "community-1", "user-1") is False
