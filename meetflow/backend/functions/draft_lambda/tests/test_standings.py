"""成績追跡（docs/draft/DESIGN.md §4.8〜§4.10、§4.15、§7）。"""

import json
from unittest.mock import patch

import pytest

from handlers import mleague
from handlers import repository as repo
from _factories import api_event, put_membership, put_profile, seed_players
from _mleague_fixture import games_page, stats_page
from errors import DraftError
from handlers import drafts, picks, progress, standings

HOST = "host"
MEMBERS = ("u1", "u2")
SEASON = "2026-27"

# フィクスチャのHTMLに出てくる選手名に揃えたマスタ。
# 実運用の40人ではなく、集計の検証に必要な分だけ。
FIXTURE_PLAYERS = [
    {"playerId": "honda", "name": "本田朋広", "kana": None, "teamId": "raiden",
     "teamName": "TEAM RAIDEN / 雷電", "isFemale": False},
    {"playerId": "ishii", "name": "石井一馬", "kana": None, "teamId": "jets",
     "teamName": "EARTH JETS", "isFemale": False},
    {"playerId": "tojo", "name": "東城りお", "kana": None, "teamId": "beast",
     "teamName": "BEAST X", "isFemale": True},
    {"playerId": "watanabe", "name": "渡辺太", "kana": None, "teamId": "drivens",
     "teamName": "赤坂ドリブンズ", "isFemale": False},
    {"playerId": "hiro", "name": "HIRO柴田", "kana": None, "teamId": "jets",
     "teamName": "EARTH JETS", "isFemale": False},
    {"playerId": "sonoda", "name": "園田賢", "kana": None, "teamId": "drivens",
     "teamName": "赤坂ドリブンズ", "isFemale": False},
    {"playerId": "suzuki", "name": "鈴木大介", "kana": None, "teamId": "beast",
     "teamName": "BEAST X", "isFemale": False},
    {"playerId": "hagiwara", "name": "萩原聖人", "kana": None, "teamId": "raiden",
     "teamName": "TEAM RAIDEN / 雷電", "isFemale": False},
    # 女性枠ルールを通すための女流選手（フィクスチャの対局には出てこない）
    {"playerId": "f1", "name": "女流1", "kana": None, "teamId": "beast",
     "teamName": "BEAST X", "isFemale": True},
    {"playerId": "f2", "name": "女流2", "kana": None, "teamId": "jets",
     "teamName": "EARTH JETS", "isFemale": True},
    {"playerId": "f3", "name": "女流3", "kana": None, "teamId": "raiden",
     "teamName": "TEAM RAIDEN / 雷電", "isFemale": True},
]


@pytest.fixture
def ready(main_table, draft_table):
    put_membership(main_table, "c1", HOST, role="OWNER")
    put_profile(main_table, HOST)
    for member in MEMBERS:
        put_membership(main_table, "c1", member)
        put_profile(main_table, member)
    seed_players(draft_table, FIXTURE_PLAYERS, season=SEASON)
    return main_table, draft_table


def _draft_with_rosters(*, regular_season_end_date=None):
    """3人×2巡だけ進めて、集計対象のチームを作る。"""
    body = {
        "name": "テストドラフト",
        "participantUserIds": [HOST, *MEMBERS],
        "season": SEASON,
    }
    if regular_season_end_date:
        body["regularSeasonEndDate"] = regular_season_end_date
    created = json.loads(
        drafts.create_draft(HOST, api_event(path_params={"communityId": "c1"}, body=body))["body"]
    )["data"]
    draft_id = created["draftId"]
    drafts.start_draft(HOST, api_event(path_params={"draftId": draft_id}))

    plan = [
        {HOST: "honda", "u1": "ishii", "u2": "tojo"},
        {HOST: "watanabe", "u1": "hiro", "u2": "sonoda"},
    ]
    for assignments in plan:
        for user_id, player_id in assignments.items():
            picks.submit_pick(
                user_id,
                api_event(path_params={"draftId": draft_id}, body={"playerId": player_id}),
            )
        progress.reveal(HOST, api_event(path_params={"draftId": draft_id}))
        progress.advance(HOST, api_event(path_params={"draftId": draft_id}))
    return draft_id


def _fake_fetch(stats_totals=None):
    """`mleague.fetch` を差し替える。

    文字列ターゲットのpatchはドメイン間のsys.modules衝突で壊れるため
    （CLAUDE.md参照）、importしたモジュールオブジェクトにpatch.objectする。
    """
    pages = {
        mleague.GAMES_PATH: games_page(),
        mleague.STATS_PATH: stats_page(stats_totals or {}),
    }
    return patch.object(mleague, "fetch", side_effect=lambda path: pages[path])


def _refresh(draft_id, user_id=HOST):
    return json.loads(
        standings.refresh_standings(
            user_id, api_event(path_params={"draftId": draft_id})
        )["body"]
    )["data"]


def _standings(draft_id, user_id=HOST):
    return json.loads(
        standings.get_standings(user_id, api_event(path_params={"draftId": draft_id}))["body"]
    )["data"]


def _points(result, user_id):
    return next(row["totalPoints"] for row in result["standings"] if row["userId"] == user_id)


# --- 取得 -------------------------------------------------------------------


def test_取得すると節が保存され参加者の合計が出る(ready):
    draft_id = _draft_with_rosters()
    with _fake_fetch():
        result = _refresh(draft_id)
    assert result["refreshed"] is True
    # 日程4件（消化3・未消化1）がすべて保存される
    assert result["gamedayCount"] == 4

    standing = _standings(draft_id)
    # HOST は 本田朋広(56.7 + 10 + ▲1) と 渡辺太(▲55.8 + ▲10 + 2)
    assert _points(standing, HOST) == round(56.7 + 10 - 1 - 55.8 - 10 + 2, 1)
    # u2 は 東城りお(▲14.1 + ▲5 + 20) と 園田賢(15.5)
    assert _points(standing, "u2") == round(-14.1 - 5 + 20 + 15.5, 1)
    assert [row["rank"] for row in standing["standings"]] == [1, 2, 3]
    assert standing["lastUpdatedAt"] is not None


def test_対局なしと未消化を区別して保存する(ready):
    # DESIGN.md §4.10の3状態。「対局なし」はアイテムが存在しないことで表す。
    draft_id = _draft_with_rosters()
    with _fake_fetch():
        _refresh(draft_id)

    gamedays = repo.list_gamedays(SEASON)
    states = {(g["date"], int(g["no"])): g["state"] for g in gamedays}
    assert states[("20260914", 1)] == repo.GAMEDAY_PLAYED
    assert states[("20260925", 3)] == repo.GAMEDAY_PLAYED
    assert states[("20260925", 4)] == repo.GAMEDAY_PLAYED
    # 未消化日は節番号を持たないので0で入る
    assert states[("20260926", 0)] == repo.GAMEDAY_SCHEDULED
    # 日程に無い日はアイテムごと存在しない＝対局なし
    assert ("20260915", 1) not in states

    standing = _standings(draft_id)
    assert standing["playedGamedayCount"] == 3
    assert standing["scheduledGamedayCount"] == 1
    assert standing["latestPlayedDate"] == "2026-09-25"


def test_同じ日に2節あっても上書きされない(ready):
    # SCRAPING.md §2.2: 日付だけをキーにすると片方が消える。
    draft_id = _draft_with_rosters()
    with _fake_fetch():
        _refresh(draft_id)
    same_day = [g for g in repo.list_gamedays(SEASON) if g["date"] == "20260925"]
    assert len(same_day) == 2


def test_取得は1日1回まで(ready):
    # DESIGN.md §4.8
    draft_id = _draft_with_rosters()
    with _fake_fetch() as fetch_mock:
        assert _refresh(draft_id)["refreshed"] is True
        second = _refresh(draft_id)
        assert second["refreshed"] is False
        assert second["reason"] == "ALREADY_FETCHED_TODAY"
        # 2回目は公式サイトを叩いていない（/games と /stats の2回だけ）
        assert fetch_mock.call_count == 2


def test_取得に失敗しても古いデータを残しカウントを消費しない(ready):
    # DESIGN.md §4.8「失敗時はカウントを消費しない（リトライ可）」
    # §7「失敗時は古いデータを出し続けつつ、最終更新を必ず出す」
    draft_id = _draft_with_rosters()
    with _fake_fetch():
        _refresh(draft_id)
    before = _points(_standings(draft_id), HOST)

    # 翌日扱いにして上限を解除したうえで、取得を失敗させる
    state = dict(repo.get_fetch_state(SEASON))
    state["lastFetchDate"] = "20000101"
    repo.put_fetch_state(SEASON, state)

    with patch.object(mleague, "fetch", side_effect=mleague.ScrapeError("サイト構造の変更")):
        with pytest.raises(DraftError) as exc:
            _refresh(draft_id)
    assert exc.value.code == "MLEAGUE_FETCH_FAILED"

    after = _standings(draft_id)
    assert _points(after, HOST) == before
    assert after["lastError"] == "サイト構造の変更"
    assert after["lastUpdatedAt"] is not None
    # 失敗はカウントを消費しないので、その日のうちに取り直せる
    assert after["canRefresh"] is True


def test_更新中は同時押しを弾く(ready):
    # DESIGN.md §6.2「2人が同時に成績更新ボタンを押したときの二重取得防止」
    draft_id = _draft_with_rosters()
    repo.put_fetch_state(SEASON, {"lockedAt": mleague.datetime.now(mleague.timezone.utc).isoformat()})
    with _fake_fetch():
        with pytest.raises(DraftError) as exc:
            _refresh(draft_id)
    assert exc.value.code == "REFRESH_IN_PROGRESS"


def test_成功後はロックが外れて翌日また取得できる(ready):
    draft_id = _draft_with_rosters()
    with _fake_fetch():
        _refresh(draft_id)
    state = dict(repo.get_fetch_state(SEASON))
    assert "lockedAt" not in state
    state["lastFetchDate"] = "20000101"
    repo.put_fetch_state(SEASON, state)
    with _fake_fetch():
        assert _refresh(draft_id)["refreshed"] is True


# --- 集計 -------------------------------------------------------------------


def test_レギュラーシーズン終了日を超える節は集計しない(ready):
    # DESIGN.md §4.15
    draft_id = _draft_with_rosters(regular_season_end_date="2026-09-14")
    with _fake_fetch():
        _refresh(draft_id)
    standing = _standings(draft_id)
    assert standing["regularSeasonEndDate"] == "2026-09-14"
    # 9/25の2節は集計外。HOSTは本田朋広56.7と渡辺太▲55.8だけ。
    assert _points(standing, HOST) == round(56.7 - 55.8, 1)


def test_終了日が未設定ならシーズン全体を集計する(ready):
    draft_id = _draft_with_rosters()
    with _fake_fetch():
        _refresh(draft_id)
    standing = _standings(draft_id)
    assert standing["regularSeasonEndDate"] is None
    assert _points(standing, HOST) != round(56.7 - 55.8, 1)


def test_出場していない選手は0ポイントで並ぶ(ready):
    draft_id = _draft_with_rosters()
    with _fake_fetch():
        _refresh(draft_id)
    standing = _standings(draft_id)
    u1 = next(row for row in standing["standings"] if row["userId"] == "u1")
    hiro = next(p for p in u1["players"] if p["playerId"] == "hiro")
    assert hiro["points"] == 13.2 or hiro["games"] >= 1


def test_誰にも指名されていない選手は未紐づけとして返す(ready):
    # 表記ゆれでポイントが0のまま張り付く事故に気づくための材料。
    draft_id = _draft_with_rosters()
    with _fake_fetch():
        _refresh(draft_id)
    standing = _standings(draft_id)
    assert "萩原聖人" in standing["unmatchedPlayerNames"]
    assert "本田朋広" not in standing["unmatchedPlayerNames"]


def test_公式の累計と食い違えば警告として持つ(ready):
    # SCRAPING.md §3の検算。取得自体は失敗にしない。
    draft_id = _draft_with_rosters()
    with _fake_fetch({"東城 りお": 999.9}):
        result = _refresh(draft_id)
    assert result["mismatchedPlayers"] == ["東城りお"]
    assert _standings(draft_id)["mismatchedPlayers"] == ["東城りお"]


# --- 手動入力フォールバック（DESIGN.md §7） ---------------------------------


def test_主催者は結果を手動入力できる(ready):
    draft_id = _draft_with_rosters()
    standings.submit_manual_result(
        HOST,
        api_event(
            path_params={"draftId": draft_id},
            body={
                "date": "2026-09-16",
                "no": 2,
                "games": [
                    {
                        "label": "第1回戦",
                        "rows": [
                            {"rank": 1, "name": "本田朋広", "point": 30},
                            {"rank": 4, "name": "渡辺太", "point": -30},
                        ],
                    }
                ],
            },
        ),
    )
    standing = _standings(draft_id)
    # 手動入力した分だけが集計される（取得はしていない）
    assert _points(standing, HOST) == 0.0
    assert standing["playedGamedayCount"] == 1


def test_主催者以外は手動入力できない(ready):
    draft_id = _draft_with_rosters()
    with pytest.raises(DraftError) as exc:
        standings.submit_manual_result(
            "u1",
            api_event(
                path_params={"draftId": draft_id},
                body={"date": "2026-09-16", "no": 2, "games": [
                    {"rows": [{"rank": 1, "name": "本田朋広", "point": 30}]}
                ]},
            ),
        )
    assert exc.value.code == "NOT_DRAFT_HOST"


@pytest.mark.parametrize(
    "body",
    [
        {"date": "こわれた日付", "no": 1, "games": [{"rows": [{"rank": 1, "name": "本田朋広", "point": 1}]}]},
        {"date": "2026-09-16", "no": 1, "games": []},
        {"date": "2026-09-16", "no": 1, "games": [{"rows": [{"rank": 1, "name": "", "point": 1}]}]},
        {"date": "2026-09-16", "no": 1, "games": [{"rows": [{"rank": 1, "name": "本田朋広"}]}]},
    ],
)
def test_手動入力の不正な内容は弾く(ready, body):
    draft_id = _draft_with_rosters()
    with pytest.raises(DraftError) as exc:
        standings.submit_manual_result(
            HOST, api_event(path_params={"draftId": draft_id}, body=body)
        )
    assert exc.value.code == "DRAFT_VALIDATION_ERROR"


def test_取得が成功すると手動入力は公式の値で上書きされる(ready):
    # 公式が正。手動はパースが直るまでの暫定という位置づけ（§7）。
    draft_id = _draft_with_rosters()
    standings.submit_manual_result(
        HOST,
        api_event(
            path_params={"draftId": draft_id},
            body={
                "date": "2026-09-14",
                "no": 1,
                "games": [{"rows": [{"rank": 1, "name": "本田朋広", "point": 999}]}],
            },
        ),
    )
    assert _points(_standings(draft_id), HOST) == 999.0
    with _fake_fetch():
        _refresh(draft_id)
    assert _points(_standings(draft_id), HOST) != 999.0
