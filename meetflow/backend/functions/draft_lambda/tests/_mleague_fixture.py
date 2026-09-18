"""テスト用の `/games` HTML断片。

実サイトのmarkupから、SCRAPING.mdに書いた落とし穴が再現する最小構成を
切り出したもの：

  - 消化済みliは `is-finish` + `data-target="key{YYYYMMDD}-{節番号}"` を持つ
  - 未消化liは `<a>` でラップされ、節番号を持たず月日テキストしか無い
  - 同じ日付に2節入る日がある（9/25の第3節・第4節）
  - **未消化日にも同じ日付に2節入る日がある**（9/27）。この場合どちらも
    節番号を持たないため、節番号だけで一意にしようとすると衝突する
  - **文書内で最後のモーダルだけ閉じボタンのmarkupが無い**
"""


def _schedule_finished(date: str, no: int, teams: list[str]) -> str:
    month, day = int(date[4:6]), int(date[6:])
    logos = "".join(f'<li><img src="x.png" alt="{team}"></li>' for team in teams)
    return (
        f'<li class="p-gamesSchedule2__list js-modal2-trigger is-finish" '
        f'data-target="key{date}-{no}" tabindex="0">'
        f'<p class="p-gamesSchedule2__data">{month}'
        f'<span class="p-gamesSchedule2__slash">/</span>{day}'
        f'<span class="p-gamesSchedule2__dayWeek">（木）</span></p>'
        f'<ul class="p-gamesSchedule2__logos">{logos}</ul>'
        f"</li>"
    )


def _schedule_scheduled(month: int, day: int, teams: list[str]) -> str:
    logos = "".join(f'<li><img src="x.png" alt="{team}"></li>' for team in teams)
    return (
        '<li class="p-gamesSchedule2__list">'
        '<a href="https://abema.tv/now-on-air/mahjong" target="_blank">'
        f'<p class="p-gamesSchedule2__data">{month}'
        f'<span class="p-gamesSchedule2__slash">/</span>{day}'
        f'<span class="p-gamesSchedule2__dayWeek">（金）</span></p>'
        f'<ul class="p-gamesSchedule2__logos">{logos}</ul>'
        "</a></li>"
    )


def _rank_row(rank: int, name: str, point: str) -> str:
    return (
        f'<li><div class="p-gamesResult__rank-item">'
        f'<div class="p-gamesResult__rank-badge is-{rank}">{rank}</div>'
        f'<div class="p-gamesResult__name-wrap">'
        f'<div class="p-gamesResult__name">{name}</div>'
        f'<div class="p-gamesResult__point">{point}</div>'
        f"</div></div></li>"
    )


def _modal(date: str, no: int, games: list[list[tuple[int, str, str]]], *, closed=True) -> str:
    columns = ""
    for index, rows in enumerate(games, start=1):
        body = "".join(_rank_row(rank, name, point) for rank, name, point in rows)
        columns += (
            f'<div class="p-gamesResult__column">'
            f'<div class="p-gamesResult__number">第{index}回戦</div>'
            f'<ol class="p-gamesResult__rank-list">{body}</ol></div>'
        )
    close = '<button class="c-modal2__close js-close" type="button"></button>' if closed else ""
    return (
        f'<div class="c-modal2" id="js-modal-key{date}-{no}" hidden tabindex="0">'
        f'<div class="c-modal2__contents" role="dialog">'
        f'<div class="p-gamesResult">{columns}</div></div>{close}</div>'
    )


def games_page(*, played_0927: bool = False) -> str:
    """消化3節（うち1日は2節）＋未消化3節（うち9/27は1日2節）。

    未消化でも同じ日に2節入るのが実サイトの通常の姿で、そちらは消化済みと
    違って節番号を持たない。ここを「未消化は1日1節」でしかテストしていな
    かったため、未消化日のSKが全部同じ値になってBatchWriteItemが
    ValidationExceptionで落ちる不具合を取り逃していた。

    `played_0927=True`にすると9/27の2節が消化済み（第5節・第6節）に変わる。
    未消化のうちに書いた行が消化後に残らないことの確認に使う。

    最後のモーダルは閉じボタン無し（SCRAPING.md §2.3）。
    """
    if played_0927:
        day_0927 = _schedule_finished(
            "20260927", 5, ["A", "B", "C", "D"]
        ) + _schedule_finished("20260927", 6, ["E", "F", "G", "H"])
    else:
        day_0927 = _schedule_scheduled(9, 27, ["A", "B", "C", "D"]) + _schedule_scheduled(
            9, 27, ["E", "F", "G", "H"]
        )
    schedule = (
        '<ul class="p-gamesSchedule2__lists">'
        + _schedule_finished("20260914", 1, ["A", "B", "C", "D"])
        + _schedule_finished("20260925", 3, ["A", "B", "C", "D"])
        + _schedule_finished("20260925", 4, ["E", "F", "G", "H"])
        + _schedule_scheduled(9, 26, ["A", "B", "E", "F"])
        + day_0927
        + "</ul>"
    )
    modals = (
        _modal(
            "20260914",
            1,
            [
                [(1, "本田 朋広", "56.7pt"), (2, "HIRO柴田", "13.2pt"),
                 (3, "東城りお", "▲14.1pt"), (4, "渡辺太", "▲55.8pt")],
                [(1, "石井一馬", "55.6pt"), (2, "園田賢", "15.5pt"),
                 (3, "鈴木大介", "▲10.1pt"), (4, "萩原聖人", "▲61pt")],
            ],
        )
        + _modal(
            "20260925",
            3,
            [[(1, "本田朋広", "10pt"), (2, "石井一馬", "5pt"),
              (3, "東城りお", "▲5pt"), (4, "渡辺太", "▲10pt")]],
        )
        # 文書内で最後のモーダル: 閉じボタンが無い（実サイトと同じ）。
        + _modal(
            "20260925",
            4,
            [[(1, "東城りお", "20pt"), (2, "渡辺太", "2pt"),
              (3, "本田朋広", "▲1pt"), (4, "石井一馬", "▲20pt")]],
            closed=played_0927,
        )
    )
    if played_0927:
        modals += _modal(
            "20260927",
            5,
            [[(1, "園田賢", "30pt"), (2, "石井一馬", "10pt"),
              (3, "渡辺太", "▲10pt"), (4, "鈴木大介", "▲30pt")]],
        ) + _modal(
            "20260927",
            6,
            [[(1, "本田朋広", "40pt"), (2, "東城りお", "8pt"),
              (3, "HIRO柴田", "▲8pt"), (4, "萩原聖人", "▲40pt")]],
            closed=False,
        )
    return f"<html><body>{schedule}{modals}</body></html>"


def stats_page(totals: dict[str, float]) -> str:
    """`/stats` のチーム成績表。選手名は姓名の間に空白が入る形で出す。"""
    names = list(totals)
    cells = "".join(f"<td>{name}</td>" for name in names)
    points = "".join(f"<td>{totals[name]}</td>" for name in names)
    return (
        "<html><body><table>"
        f"<tr><th>選手名</th>{cells}</tr>"
        f"<tr><th>ポイント</th>{points}</tr>"
        "</table></body></html>"
    )
