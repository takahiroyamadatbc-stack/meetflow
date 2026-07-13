"""F-403 scoring (機能要件書v1.1 §8/F-403, 要件定義書v1.2 §13.2).

Kept as an isolated, pure function -- not because the docs mandate this
specific weighting (they only give qualitative bonus factors, not point
values), but because Lambda設計書v1.1 §6.4 explicitly recommends separating
the scoring calculation so Phase2 trust-score/NG-set factors can be added
later without restructuring the matching flow. The weights below are an MVP
heuristic invented to fit the qualitative factors in 要件定義書v1.2 §13.2
into a 0-100 score (要件定義書v1.2 §13.4's example candidate shows a
92-point score) -- there is no canonical point breakdown in the docs, so
treat these weights as adjustable, not authoritative.
"""

_CONDITION_MATCH_WEIGHT = 30
_BEGINNER_WEIGHT = 20
_RECENCY_WEIGHT = 30
_PRIORITY_WEIGHT = 20
_RECENCY_CAP_DAYS = 30


def calculate_score(*, template, members_profiles, members_days_since_last_played):
    """
    template: EventTemplate item (dict) -- needs `conditions` (Map) and
        `priority` (0-100).
    members_profiles: User profile dicts for the candidate's members.
    members_days_since_last_played: list of int, one per member -- days
        since their last CONFIRMED Participant record, or None if they have
        no participation history at all (treated as maximally "fresh").

    Returns (score: int 0-100, reasons: list[str]).
    """
    reasons = ["全員予定一致"]  # F-402の必須条件（日時一致）を満たした候補
    conditions = template.get("conditions") or {}
    wants_beginner_ok = bool(conditions.get("beginnerOk"))

    if wants_beginner_ok and members_profiles:
        beginner_fraction = sum(
            1 for p in members_profiles if p.get("beginnerOk")
        ) / len(members_profiles)
    else:
        beginner_fraction = 1.0  # no requirement -> trivially satisfied
    if beginner_fraction == 1.0:
        reasons.append("初心者対応可能" if wants_beginner_ok else "条件一致")

    if members_days_since_last_played:
        normalized = [
            1.0 if days is None else min(days, _RECENCY_CAP_DAYS) / _RECENCY_CAP_DAYS
            for days in members_days_since_last_played
        ]
        recency_fraction = sum(normalized) / len(normalized)
    else:
        recency_fraction = 0.0
    if recency_fraction > 0.5:
        reasons.append("最近参加していない人を含む")

    priority = min(max(template.get("priority", 0) or 0, 0), 100)

    total = (
        _CONDITION_MATCH_WEIGHT * beginner_fraction
        + _BEGINNER_WEIGHT * beginner_fraction
        + _RECENCY_WEIGHT * recency_fraction
        + _PRIORITY_WEIGHT * (priority / 100)
    )
    return round(min(total, 100)), reasons
