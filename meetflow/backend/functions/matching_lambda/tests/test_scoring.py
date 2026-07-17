from handlers.scoring import calculate_score

_TEMPLATE = {"conditions": {}, "priority": 0}


def test_calculate_score_no_frequency_status_no_penalty():
    score, reasons = calculate_score(
        template=_TEMPLATE,
        members_profiles=[{}, {}],
        members_days_since_last_played=[None, None],
    )
    assert not any("上限" in r for r in reasons)


def test_calculate_score_all_members_under_limit_no_penalty():
    score, reasons = calculate_score(
        template=_TEMPLATE,
        members_profiles=[{}, {}],
        members_days_since_last_played=[None, None],
        members_frequency_status=[None, None],
    )
    assert not any("上限" in r for r in reasons)


def test_calculate_score_penalizes_proportionally_to_exceeded_fraction():
    baseline_score, _ = calculate_score(
        template=_TEMPLATE,
        members_profiles=[{}, {}],
        members_days_since_last_played=[None, None],
        members_frequency_status=[None, None],
    )
    half_exceeded_score, reasons = calculate_score(
        template=_TEMPLATE,
        members_profiles=[{}, {}],
        members_days_since_last_played=[None, None],
        members_frequency_status=[
            {"name": "たか", "period": "WEEK", "limit": 1, "count": 1},
            None,
        ],
    )
    all_exceeded_score, _ = calculate_score(
        template=_TEMPLATE,
        members_profiles=[{}, {}],
        members_days_since_last_played=[None, None],
        members_frequency_status=[
            {"name": "たか", "period": "WEEK", "limit": 1, "count": 1},
            {"name": "けん", "period": "MONTH", "limit": 2, "count": 3},
        ],
    )

    # 減点は超過メンバーの割合に比例する（機械的な除外はしない）。
    assert half_exceeded_score < baseline_score
    assert all_exceeded_score < half_exceeded_score
    assert "たかさんは週の上限（1回）にすでに達している" in reasons


def test_calculate_score_reasons_use_month_label():
    _, reasons = calculate_score(
        template=_TEMPLATE,
        members_profiles=[{}],
        members_days_since_last_played=[None],
        members_frequency_status=[
            {"name": "けん", "period": "MONTH", "limit": 3, "count": 4}
        ],
    )
    assert "けんさんは月の上限（3回）にすでに達している" in reasons


def test_calculate_score_never_goes_below_zero():
    # 他の加点要素を全てゼロに寄せた上で全員が上限超過の場合、
    # 減点のみで合計がマイナスになりうるため下限クランプを検証する。
    template = {"conditions": {"beginnerOk": True}, "priority": 0}
    score, _ = calculate_score(
        template=template,
        members_profiles=[{"beginnerOk": False}] * 5,
        members_days_since_last_played=[0] * 5,
        members_frequency_status=[
            {"name": f"user{i}", "period": "WEEK", "limit": 1, "count": 5}
            for i in range(5)
        ],
    )
    assert score == 0
