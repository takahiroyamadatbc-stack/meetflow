"""Mリーグ公式サイト（m-league.jp）からの成績取得（docs/draft/SCRAPING.md）。

DynamoDBにもHTTPレスポンス組み立てにも依存しない。取得とパースだけを担う。

**重要**: ここの正規表現は実際のHTMLに対して検証済みで、SCRAPING.mdに書いた
3つの落とし穴を踏まえている。素直に書き直すと静かに壊れるので、変更する場合は
必ず `docs/draft/scrape_prototype.py` で実サイトに対して検算してから入れること。
"""

import html
import re
import urllib.request
from datetime import datetime, timedelta, timezone

BASE_URL = "https://m-league.jp"
# 今季の日程・結果は `/games` 1枚に全節分がモーダルとして埋め込まれている
# （SCRAPING.md §0）。日別ページを個別に取りに行く必要はない。
GAMES_PATH = "/games"
STATS_PATH = "/stats"
USER_AGENT = "Mozilla/5.0 (compatible; meetflow-draft/1.0)"
TIMEOUT_SECONDS = 20

JST = timezone(timedelta(hours=9))

# 対局日リストの1件。消化済みと未消化でmarkupが違う（SCRAPING.md §2.1）。
#   消化済み: class に is-finish、data-target="key{YYYYMMDD}-{節番号}" を持つ
#   未消化  : Abemaの配信ページへのリンクでラップされ、月日テキストしか無い
# 終端を「次の対局日li」で取るのは、未消化liの閉じタグの形が消化済みと違い、
# </ul></li> を終端にすると未消化分をまとめて1件に飲み込むため。
RE_SCHEDULE = re.compile(
    r'<li class="(?P<cls>p-gamesSchedule2__list(?![a-zA-Z-])[^"]*)"(?P<attrs>[^>]*)>'
    r'(?P<body>.*?)(?=<li class="p-gamesSchedule2__list(?![a-zA-Z-])|</ul>\s*(?:<|\Z))',
    re.S,
)
RE_TARGET = re.compile(r'data-target="key(?P<date>\d{8})-(?P<no>\d+)"')
RE_MONTHDAY = re.compile(
    r'p-gamesSchedule2__data">\s*(?P<month>\d{1,2})<span[^>]*>/</span>\s*(?P<day>\d{1,2})'
)
RE_TEAM_ALT = re.compile(r'<img[^>]*alt="(?P<team>[^"]+)"')

# 結果モーダル1つ = 1節（通常2半荘）。
# 終端は「次のモーダルの開始」または「文書の終わり」で取る。文書内で最後の
# モーダルだけは閉じボタンのmarkupが無いため、閉じボタンを終端にすると
# **最新の1節を取りこぼす**（SCRAPING.md §2.3。2025-26アーカイブで実測）。
# 取りこぼすのは常に最新の節＝一番見たい日なので、ここは必ず踏襲すること。
RE_MODAL = re.compile(
    r'<div class="c-modal2" id="js-modal-key(?P<date>\d{8})-(?P<no>\d+)"'
    r'(?P<body>.*?)(?=<div class="c-modal2" id="js-modal-key|\Z)',
    re.S,
)
RE_GAME = re.compile(
    r'<div class="p-gamesResult__number">(?P<label>.*?)</div>(?P<body>.*?)</ol>', re.S
)
RE_ROW = re.compile(
    r"rank-badge is-(?P<rank>\d)\">.*?"
    r"p-gamesResult__name\">(?P<name>.*?)</div>.*?"
    r"p-gamesResult__point\">\s*(?P<point>.*?)\s*</div>",
    re.S,
)


class ScrapeError(Exception):
    """取得・パースの失敗。呼び出し元はこれを捕まえて古いデータを出し続ける。"""


def normalize_name(name: str) -> str:
    """選手名の表記ゆれを吸収する。

    `/stats` は `石井 一馬` と姓名の間に空白が入り、`/games` のモーダルは
    `石井一馬` と入らない（SCRAPING.md §3）。突き合わせ前に必ず通すこと。
    """
    return re.sub(r"\s+", "", html.unescape(name))


def parse_point(raw: str) -> float:
    """"▲48.8pt" → -48.8。公式はマイナスを `▲` で表記する（`-` ではない）。"""
    text = html.unescape(raw).strip()
    negative = text.startswith(("▲", "△", "-", "−"))
    num = re.sub(r"[^0-9.]", "", text)
    if not num:
        raise ScrapeError(f"ポイントを数値化できません: {raw!r}")
    return (-1 if negative else 1) * float(num)


def latest_confirmed_date(now: datetime = None) -> str:
    """結果が確定しているとみなせる最新の対局日（YYYYMMDD、JST基準）。

    DESIGN.md §4.9: `最新確定日 = date(現在時刻 − 26時間)`。
    ユーザー指定の「19時〜26時は前日扱い」を1本の式に畳んだもので、
    境界として実際に効くのは26時（翌2:00）だけ。
    """
    now_jst = (now or datetime.now(timezone.utc)).astimezone(JST)
    return (now_jst - timedelta(hours=26)).strftime("%Y%m%d")


def is_in_game_window(now: datetime = None) -> bool:
    """いま対局の時間帯（19:00〜翌2:00）か。

    DESIGN.md §4.9: 19時は最新確定日の計算を変えない。「対局中」バッジの
    表示判定にだけ使う値として持つ。
    """
    hour = (now or datetime.now(timezone.utc)).astimezone(JST).hour
    return hour >= 19 or hour < 2


def season_start_year(season: str) -> int:
    """"2026-27" → 2026。未消化日の年を補うのに使う（SCRAPING.md §2.1）。"""
    try:
        return int(season.split("-")[0])
    except (ValueError, IndexError) as exc:
        raise ScrapeError(f"シーズン表記が不正です: {season!r}") from exc


def fetch(path: str) -> str:
    request = urllib.request.Request(BASE_URL + path, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        raise ScrapeError(f"公式サイトの取得に失敗しました: {path}") from exc


def parse_games(page: str, start_year: int) -> tuple[list[dict], dict[str, list[dict]]]:
    """`/games` から対局日カレンダーと節ごとの結果を取り出す。

    カレンダーは公式が公開している対局日そのもの。ここに載っていない日付は
    対局なしと判断してよい（当月分が公開済みであれば。SCRAPING.md §2.4）。

    戻り値の2つ目のキーは `{YYYYMMDD}-{節番号}`。**同じ日付に2節入る日がある**
    （2025-26は131日中42日）ため、日付だけをキーにしてはいけない。
    """
    schedule = []
    for match in RE_SCHEDULE.finditer(page):
        finished = "is-finish" in match.group("cls")
        target = RE_TARGET.search(match.group("attrs"))
        if target:
            date, no = target.group("date"), int(target.group("no"))
        else:
            month_day = RE_MONTHDAY.search(match.group("body"))
            if not month_day:
                continue
            month, day = int(month_day.group("month")), int(month_day.group("day"))
            # Mリーグは9月開幕・5月終了。1〜5月は翌年になる。
            year = start_year if month >= 9 else start_year + 1
            date, no = f"{year:04d}{month:02d}{day:02d}", None
        schedule.append(
            {
                "date": date,
                "no": no,
                "finished": finished,
                "teams": RE_TEAM_ALT.findall(match.group("body")),
            }
        )

    results = {}
    for modal in RE_MODAL.finditer(page):
        games = []
        for game in RE_GAME.finditer(modal.group("body")):
            rows = [
                {
                    "rank": int(row.group("rank")),
                    "name": normalize_name(re.sub(r"<[^>]+>", "", row.group("name"))),
                    "point": parse_point(row.group("point")),
                }
                for row in RE_ROW.finditer(game.group("body"))
            ]
            if rows:
                games.append(
                    {
                        "label": normalize_name(re.sub(r"<[^>]+>", "", game.group("label"))),
                        "rows": rows,
                    }
                )
        results[f'{modal.group("date")}-{modal.group("no")}'] = games

    if not schedule:
        # 日程が1件も取れない＝HTML構造が変わった可能性が高い。
        # 空の結果で既存データを上書きしないよう、ここで止める（§7）。
        raise ScrapeError("対局日が1件も取得できませんでした（サイト構造の変更の可能性）")
    return schedule, results


def parse_stats(page: str) -> dict[str, float]:
    """`/stats` のレギュラーシーズン表から 選手名 → 累計ポイント を返す。

    日別積算の検算用（SCRAPING.md §3）。取得できなくても致命ではないので、
    パースに失敗したら空dictを返して検算をスキップする。
    """
    page = re.sub(r"<script.*?</script>", "", page, flags=re.S)
    cells = [
        re.sub(r"\s+", " ", html.unescape(cell)).strip()
        for cell in re.sub(r"<[^>]+>", "\n", page).split("\n")
    ]
    cells = [cell for cell in cells if cell]
    totals = {}
    for index, cell in enumerate(cells):
        if cell != "選手名":
            continue
        names = [normalize_name(name) for name in cells[index + 1 : index + 5]]
        cursor = index
        while cursor < len(cells) and cells[cursor] != "ポイント":
            cursor += 1
        for name, point in zip(names, cells[cursor + 1 : cursor + 5]):
            try:
                totals[name] = float(point)
            except ValueError:
                return {}
    return totals


def fetch_season_results(season: str) -> dict:
    """今季の対局日と結果を丸ごと取得する（`/games` への1リクエスト）。

    差分取得はしない。SCRAPING.md §6の通り全節が1枚に載っているため、
    毎回まるごと取って上書きするほうが「どの日が未取得か」の管理より単純で、
    取りこぼしも起きない。
    """
    schedule, results = parse_games(fetch(GAMES_PATH), season_start_year(season))
    try:
        official_totals = parse_stats(fetch(STATS_PATH))
    except ScrapeError:
        # 検算用なので、取れなくても本体の取得は成功扱いにする。
        official_totals = {}
    return {"schedule": schedule, "results": results, "officialTotals": official_totals}


def accumulate(results: dict[str, list[dict]], *, until_date: str = None) -> dict[str, float]:
    """節ごとの結果を選手別に積算する。

    `until_date`（YYYYMMDD）を渡すとその日までで打ち切る。DESIGN.md §4.15の
    レギュラーシーズン終了日がこれにあたる。公式サイトの日程HTMLには
    レギュラー／セミファイナル／ファイナルの区別が無いため、日付で切る。
    """
    totals: dict[str, float] = {}
    for key, games in results.items():
        date = key.split("-")[0]
        if until_date and date > until_date:
            continue
        for game in games:
            for row in game["rows"]:
                totals[row["name"]] = round(totals.get(row["name"], 0.0) + row["point"], 1)
    return totals


def verify(accumulated: dict[str, float], official_totals: dict[str, float]) -> list[str]:
    """日別積算と公式の累計ポイントを突き合わせる（SCRAPING.md §3）。

    不一致の選手名を返す。呼び出し元はこれを警告として持つだけで、取得自体は
    失敗にしない（ポストシーズンが始まると公式のRegularタブとは当然ズレる）。
    """
    if not official_totals:
        return []
    return sorted(
        name
        for name, value in accumulated.items()
        if name in official_totals and abs(official_totals[name] - value) >= 0.05
    )
