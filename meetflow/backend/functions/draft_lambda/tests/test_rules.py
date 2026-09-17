"""指名ルール（DESIGN.md §4.3 / §4.4 / §4.4.1）の単体テスト。

DBもHTTPも介さない純粋関数なので、ここで境界条件を潰しておく。
"""

import pytest

import rules


def test_初期余剰枠は女性選手数から参加者数を引いた値():
    # DESIGN.md §4.3の表: 参加者3人なら10、10人なら3。
    assert rules.initial_female_surplus(13, 3) == 10
    assert rules.initial_female_surplus(13, 10) == 3


def test_参加人数の上限は女性選手数でも抑えられる():
    assert rules.max_participants(13) == 10
    assert rules.max_participants(6) == 6


@pytest.mark.parametrize(
    "round_no,has_female,expected",
    [
        (1, False, False),
        (2, False, False),
        # 3巡目終了時点で女性ゼロ = 4巡目に入った時点で強制
        # （DESIGN.md §4.3(a)）。
        (3, False, False),
        (4, False, True),
        # 既に確保していれば最終巡でも自由。
        (4, True, False),
    ],
)
def test_動的強制は最終巡に女性ゼロのときだけ効く(round_no, has_female, expected):
    assert rules.must_pick_female(round_no, has_female) is expected


def test_余剰枠を消費するのは女性を持っている人の追加女流指名だけ():
    assert rules.consumes_surplus(has_female=True, pick_is_female=True) is True
    # 1人目の女性は必要指名であって余剰ではない。
    assert rules.consumes_surplus(has_female=False, pick_is_female=True) is False
    assert rules.consumes_surplus(has_female=True, pick_is_female=False) is False


def test_最終巡で男性を指名しようとすると弾かれる():
    from errors import DraftError

    with pytest.raises(DraftError) as exc:
        rules.validate_pick(
            round_no=4, has_female=False, pick_is_female=False, female_surplus_remaining=5
        )
    assert exc.value.code == "FEMALE_REQUIRED"


def test_余剰枠ゼロで追加の女流指名は弾かれる():
    from errors import DraftError

    with pytest.raises(DraftError) as exc:
        rules.validate_pick(
            round_no=2, has_female=True, pick_is_female=True, female_surplus_remaining=0
        )
    assert exc.value.code == "FEMALE_SURPLUS_EXHAUSTED"


def test_余剰枠ゼロでも1人目の女性は指名できる():
    # ここを弾いてしまうと「女性を持たない人」が詰む。§4.3の不変条件
    # 「残り女流数 ≧ 未確保人数」は、必要指名を余剰枠と無関係に通すことで保たれる。
    rules.validate_pick(
        round_no=2, has_female=False, pick_is_female=True, female_surplus_remaining=0
    )


def _first(candidates):
    """決定的な抽選（常に先頭が当選）。抽選の順序と結果だけを検証するため。"""
    return sorted(candidates)[0]


def test_同一選手被りは抽選で1人に絞られ落選者が返る():
    picks = [
        {"userId": "a", "playerId": "p1", "isFemale": False, "hasFemale": False},
        {"userId": "b", "playerId": "p1", "isFemale": False, "hasFemale": False},
        {"userId": "c", "playerId": "p2", "isFemale": False, "hasFemale": False},
    ]
    confirmed, losers, lotteries = rules.resolve_wave(
        picks, female_surplus_remaining=5, draw=_first
    )
    assert sorted(p["userId"] for p in confirmed) == ["a", "c"]
    assert losers == ["b"]
    assert len(lotteries) == 1
    assert lotteries[0]["type"] == "PLAYER"
    assert lotteries[0]["candidates"] == ["a", "b"]


def test_余剰枠超過は追加指名者同士の抽選で解決される():
    # 残り枠1に対して2人が追加の女流指名。別々の選手なので被り抽選は起きない。
    picks = [
        {"userId": "a", "playerId": "p1", "isFemale": True, "hasFemale": True},
        {"userId": "b", "playerId": "p2", "isFemale": True, "hasFemale": True},
    ]
    confirmed, losers, lotteries = rules.resolve_wave(
        picks, female_surplus_remaining=1, draw=_first
    )
    assert [p["userId"] for p in confirmed] == ["a"]
    assert losers == ["b"]
    assert [x["type"] for x in lotteries] == ["FEMALE_SURPLUS"]


def test_被り抽選の落選者は余剰枠を消費しない():
    """DESIGN.md §4.4.1 の解決順が効いていることの検証。

    a と b が同じ女流選手を指名し、c が別の女流選手を指名する。全員が既に
    女性を持っているので3件とも余剰枠を消費しうるが、残り枠は2。
    先に被り抽選を解けば生き残りは2件なので、余剰枠の抽選は起きない。
    先に余剰枠を解いてしまうと、どのみち被りで落ちる b が枠を1つ食って
    しまい、本来通るはずの c が落ちうる。
    """
    picks = [
        {"userId": "a", "playerId": "p1", "isFemale": True, "hasFemale": True},
        {"userId": "b", "playerId": "p1", "isFemale": True, "hasFemale": True},
        {"userId": "c", "playerId": "p2", "isFemale": True, "hasFemale": True},
    ]
    confirmed, losers, lotteries = rules.resolve_wave(
        picks, female_surplus_remaining=2, draw=_first
    )
    assert sorted(p["userId"] for p in confirmed) == ["a", "c"]
    assert losers == ["b"]
    assert [x["type"] for x in lotteries] == ["PLAYER"]


def test_被りに勝った人が余剰枠抽選で落ちることもある():
    # §4.4.1 が明示的に許容しているケース。
    picks = [
        {"userId": "a", "playerId": "p1", "isFemale": True, "hasFemale": True},
        {"userId": "b", "playerId": "p1", "isFemale": True, "hasFemale": True},
        {"userId": "c", "playerId": "p2", "isFemale": True, "hasFemale": True},
    ]

    def draw(candidates):
        # 被り抽選ではaを、余剰枠抽選ではcを当選させる。
        return "a" if "b" in candidates else "c"

    confirmed, losers, lotteries = rules.resolve_wave(
        picks, female_surplus_remaining=1, draw=draw
    )
    assert [p["userId"] for p in confirmed] == ["c"]
    assert sorted(losers) == ["a", "b"]
    assert [x["type"] for x in lotteries] == ["PLAYER", "FEMALE_SURPLUS"]


def test_必要指名は余剰枠の抽選対象にならない():
    # まだ女性を持っていない a の指名は余剰枠を消費しないので、
    # 残り枠0でも確定する。
    picks = [
        {"userId": "a", "playerId": "p1", "isFemale": True, "hasFemale": False},
    ]
    confirmed, losers, lotteries = rules.resolve_wave(
        picks, female_surplus_remaining=0, draw=_first
    )
    assert [p["userId"] for p in confirmed] == ["a"]
    assert losers == []
    assert lotteries == []
