"""公式サイトのパースと日付ロジック（docs/draft/SCRAPING.md、DESIGN.md §4.9）。

実サイトのHTMLを丸ごと置くのは重いので、SCRAPING.mdに書いた落とし穴が
再現する最小構成の断片（_mleague_fixture.py）に対して固定する。
"""

from datetime import datetime, timezone

import pytest

from handlers import mleague
from _mleague_fixture import games_page, stats_page


def test_消化済みと未消化の両方が日程として取れる():
    schedule, _ = mleague.parse_games(games_page(), 2026)
    assert len(schedule) == 6
    assert [(day["date"], day["finished"]) for day in schedule] == [
        ("20260914", True),
        ("20260925", True),
        ("20260925", True),
        # 未消化のliは<a>でラップされ節番号を持たないが、日程としては拾う。
        # 年はシーズン（9〜12月＝開幕年）から補う。
        ("20260926", False),
        # 未消化でも同じ日に2節入る。どちらも節番号を持たない。
        ("20260927", False),
        ("20260927", False),
    ]
    assert all(len(day["teams"]) == 4 for day in schedule)


def test_未消化で同じ日に2節あっても2件として取れる():
    # 節番号が無いので、日付だけで潰すと片方が消える。
    schedule, _ = mleague.parse_games(games_page(), 2026)
    same_day = [day for day in schedule if day["date"] == "20260927"]
    assert len(same_day) == 2
    assert [day["no"] for day in same_day] == [None, None]
    # 対戦カードは別物なので、潰れていないことはチームで見分けられる。
    assert same_day[0]["teams"] != same_day[1]["teams"]


def test_同じ日付に2節ある日を取り違えない():
    # SCRAPING.md §2.2: 2025-26は131日中42日が1日2節。日付だけをキーにすると壊れる。
    _, results = mleague.parse_games(games_page(), 2026)
    assert "20260925-3" in results
    assert "20260925-4" in results
    assert results["20260925-3"] != results["20260925-4"]


def test_文書内で最後のモーダルも取りこぼさない():
    # SCRAPING.md §2.3: 最後のモーダルだけ閉じボタンのmarkupが無い。
    # 閉じボタンを終端にすると最新の1節＝一番見たい日が消える。
    _, results = mleague.parse_games(games_page(), 2026)
    assert len(results) == 3
    assert results["20260925-4"][0]["rows"][0]["name"] == "東城りお"


def test_未消化日は結果を持たない():
    schedule, results = mleague.parse_games(games_page(), 2026)
    unfinished = [day for day in schedule if not day["finished"]]
    assert len(unfinished) == 3
    for day in unfinished:
        assert f'{day["date"]}-{day["no"]}' not in results


def test_日程が1件も取れなければ失敗として扱う():
    # 空の結果で既存データを上書きしないためのガード（DESIGN.md §7）。
    with pytest.raises(mleague.ScrapeError):
        mleague.parse_games("<html><body></body></html>", 2026)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("56.7pt", 56.7),
        # 公式はマイナスを▲で表記する（-ではない）
        ("▲48.8pt", -48.8),
        ("▲61pt", -61.0),
        ("0pt", 0.0),
    ],
)
def test_ポイント表記をパースする(raw, expected):
    assert mleague.parse_point(raw) == expected


def test_数値にならないポイントは失敗として扱う():
    with pytest.raises(mleague.ScrapeError):
        mleague.parse_point("－pt")


def test_選手名の空白を正規化する():
    # SCRAPING.md §3: /statsは「石井 一馬」、/gamesは「石井一馬」。
    assert mleague.normalize_name("石井 一馬") == "石井一馬"
    assert mleague.normalize_name("本田　朋広") == "本田朋広"


def test_モーダル側の選手名も正規化されている():
    _, results = mleague.parse_games(games_page(), 2026)
    names = [row["name"] for row in results["20260914-1"][0]["rows"]]
    assert "本田朋広" in names


def test_積算はレギュラーシーズン終了日で打ち切れる():
    # DESIGN.md §4.15: 日程HTMLにシリーズの区別が無いため日付で切る。
    _, results = mleague.parse_games(games_page(), 2026)
    everything = mleague.accumulate(results)
    until_first = mleague.accumulate(results, until_date="20260914")
    assert everything["東城りお"] == round(-14.1 + -5 + 20, 1)
    assert until_first["東城りお"] == -14.1


def test_公式の累計と突き合わせて不一致を返す():
    _, results = mleague.parse_games(games_page(), 2026)
    accumulated = mleague.accumulate(results)
    assert mleague.verify(accumulated, {"東城りお": accumulated["東城りお"]}) == []
    assert mleague.verify(accumulated, {"東城りお": 999.9}) == ["東城りお"]
    # 検算用の値が取れなかった場合は警告を出さない
    assert mleague.verify(accumulated, {}) == []


def test_statsの空白入り選手名も突き合わせできる():
    totals = mleague.parse_stats(stats_page({"石井 一馬": 55.6, "園田 賢": 15.5}))
    assert totals == {"石井一馬": 55.6, "園田賢": 15.5}


def _jst(hour: int, day: int = 18) -> datetime:
    return datetime(2026, 9, day, hour, 0, tzinfo=mleague.JST).astimezone(timezone.utc)


@pytest.mark.parametrize(
    "hour,expected,reason",
    [
        (7, "20260917", "前夜の対局は終わっている"),
        (20, "20260917", "今夜の対局は進行中"),
        (1, "20260916", "昨夜の対局がまだ進行中（25時扱い）"),
    ],
)
def test_最新確定日は26時間前の日付(hour, expected, reason):
    # DESIGN.md §4.9の表をそのまま固定する。
    assert mleague.latest_confirmed_date(_jst(hour)) == expected, reason


def test_境界として効くのは26時だけ():
    # 19時は最新確定日を変えない（18:59でも19:01でも答えは前日）。
    assert mleague.latest_confirmed_date(_jst(18)) == mleague.latest_confirmed_date(_jst(19))
    # 翌2時をまたぐと1日ずれる
    assert mleague.latest_confirmed_date(_jst(1)) != mleague.latest_confirmed_date(_jst(2))


@pytest.mark.parametrize(
    "hour,expected", [(18, False), (19, True), (23, True), (1, True), (2, False), (7, False)]
)
def test_対局中バッジの判定は19時から翌2時(hour, expected):
    # §4.9: 19時は「対局中」バッジの表示判定にだけ使う値として持つ。
    assert mleague.is_in_game_window(_jst(hour)) is expected


def test_シーズン表記から開幕年を取り出す():
    assert mleague.season_start_year("2026-27") == 2026
    with pytest.raises(mleague.ScrapeError):
        mleague.season_start_year("こわれた表記")
