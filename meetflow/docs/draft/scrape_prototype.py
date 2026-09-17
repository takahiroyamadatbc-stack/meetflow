#!/usr/bin/env python3
"""Mリーグ公式サイトのスクレイピング検証用プロトタイプ。

本番実装ではない。docs/draft/SCRAPING.md に書いたパース規則が
実際のHTMLに対して成立することを確認するための調査スクリプト。

使い方:
    python3 scrape_prototype.py                    # 公式サイトから取得して検証
    python3 scrape_prototype.py --dir ./cache      # 保存済みHTMLで検証（オフライン）

検証内容:
    1. /games から対局日カレンダーと日別結果を取り出す
    2. /stats から選手別のレギュラーシーズン累計ポイントを取り出す
    3. 1を自前で積算した値が2と一致することを確認する（検算）
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.request

BASE = "https://m-league.jp"
UA = "Mozilla/5.0 (compatible; meetflow-draft-research/0.1)"

# 対局日リストの1件。消化済みと未消化で markup が違う。
#   消化済み: class に is-finish、data-target="key{YYYYMMDD}-{節番号}" を持つ
#   未消化  : class は素、data-target も節番号も無く、月日テキストしか無い（年が入らない）
# 未消化側の年はシーズン（9〜12月＝開幕年 / 1〜5月＝翌年）から補う。
# 終端は「次の対局日li」または「リストの終わり」で取る。
# 未消化の li は <a> でラップされるため閉じタグの形が消化済みと違い、
# </ul></li> を終端にすると未消化分をまとめて1件に飲み込む。
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
# 結果モーダル1つ = 1節（通常2半荘）
# 終端は「次のモーダルの開始」または「文書の終わり」で取る。
# 文書内で最後のモーダルだけは閉じボタンの markup が無いため、
# 閉じボタンを終端にすると最新の1節を取りこぼす（2025-26アーカイブで実測）。
RE_MODAL = re.compile(
    r'<div class="c-modal2" id="js-modal-key(?P<date>\d{8})-(?P<no>\d+)"'
    r'(?P<body>.*?)(?=<div class="c-modal2" id="js-modal-key|\Z)',
    re.S,
)
# モーダル内の1半荘ブロック（第1回戦 / 第2回戦）
RE_GAME = re.compile(r'<div class="p-gamesResult__number">(?P<label>.*?)</div>(?P<body>.*?)</ol>', re.S)
# 1半荘内の1着順行
RE_ROW = re.compile(
    r'rank-badge is-(?P<rank>\d)">.*?'
    r'p-gamesResult__name">(?P<name>.*?)</div>.*?'
    r'p-gamesResult__point">\s*(?P<point>.*?)\s*</div>',
    re.S,
)


def fetch(path: str, cache_dir: str | None) -> str:
    """公式サイトからHTMLを取得する。cache_dir があればそこから読む。"""
    fname = path.strip("/").replace("/", "_") + ".html"
    if cache_dir:
        with open(os.path.join(cache_dir, fname), encoding="utf-8") as f:
            return f.read()
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read().decode("utf-8", errors="replace")


def strip_tags(s: str) -> str:
    return re.sub(r"\s+", "", html.unescape(re.sub(r"<[^>]+>", "", s)))


def parse_point(raw: str) -> float:
    """"▲48.8pt" → -48.8 。公式はマイナスを ▲ で表記する。"""
    text = html.unescape(raw).strip()
    negative = text.startswith(("▲", "△", "-", "−"))
    num = re.sub(r"[^0-9.]", "", text)
    if not num:
        raise ValueError(f"ポイントを数値化できない: {raw!r}")
    return (-1 if negative else 1) * float(num)


def parse_games(page: str, season_start_year: int = 2026) -> tuple[list[dict], dict[str, list[dict]]]:
    """対局日カレンダーと日別結果を返す。

    カレンダーは「公式が公開している対局日のすべて」であり、
    ここに載っていない日付は対局なしと判断してよい（当月分が公開済みであれば）。
    """
    schedule = []
    for m in RE_SCHEDULE.finditer(page):
        finished = "is-finish" in m.group("cls")
        target = RE_TARGET.search(m.group("attrs"))
        if target:
            date, no = target.group("date"), int(target.group("no"))
        else:
            md = RE_MONTHDAY.search(m.group("body"))
            if not md:
                continue
            month, day = int(md.group("month")), int(md.group("day"))
            year = season_start_year if month >= 9 else season_start_year + 1
            date, no = f"{year:04d}{month:02d}{day:02d}", None
        schedule.append(
            {
                "date": date,
                "no": no,
                "finished": finished,
                "teams": RE_TEAM_ALT.findall(m.group("body")),
            }
        )
    results: dict[str, list[dict]] = {}
    for modal in RE_MODAL.finditer(page):
        games = []
        for game in RE_GAME.finditer(modal.group("body")):
            rows = [
                {
                    "rank": int(r.group("rank")),
                    "name": strip_tags(r.group("name")),
                    "point": parse_point(r.group("point")),
                }
                for r in RE_ROW.finditer(game.group("body"))
            ]
            if rows:
                games.append({"label": strip_tags(game.group("label")), "rows": rows})
        results[f'{modal.group("date")}-{modal.group("no")}'] = games
    return schedule, results


def parse_stats(page: str) -> dict[str, float]:
    """/stats のレギュラーシーズン表から 選手名 → 累計ポイント を返す（検算用）。"""
    page = re.sub(r"<script.*?</script>", "", page, flags=re.S)
    cells = [
        re.sub(r"\s+", " ", html.unescape(c)).strip()
        for c in re.sub(r"<[^>]+>", "\n", page).split("\n")
    ]
    cells = [c for c in cells if c]
    totals: dict[str, float] = {}
    for i, cell in enumerate(cells):
        if cell != "選手名":
            continue
        names = [re.sub(r"\s+", "", n) for n in cells[i + 1 : i + 5]]
        j = i
        while j < len(cells) and cells[j] != "ポイント":
            j += 1
        for name, point in zip(names, cells[j + 1 : j + 5]):
            totals[name] = float(point)
    return totals


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", dest="cache_dir", default=None, help="保存済みHTMLのディレクトリ")
    parser.add_argument("--json", action="store_true", help="日別結果をJSONで出力する")
    args = parser.parse_args()

    schedule, results = parse_games(fetch("/games", args.cache_dir))
    stats = parse_stats(fetch("/stats", args.cache_dir))

    if args.json:
        json.dump({"schedule": schedule, "results": results}, sys.stdout, ensure_ascii=False, indent=2)
        return 0

    print("=== 対局日カレンダー ===")
    for day in schedule:
        key = f'{day["date"]}-{day["no"]}'
        games = results.get(key, [])
        state = "消化済" if day["finished"] else "未消化"
        no = f'第{day["no"]:3d}節' if day["no"] else "   （未定）"
        print(f'  {day["date"]} {no}  {state}  半荘={len(games)}  {len(day["teams"])}チーム')
    print(f"  対局日 {len(schedule)}件 / 結果取得済 {len(results)}件")

    # 日別結果を自前で積算し、公式の累計ポイントと突き合わせる
    accumulated: dict[str, float] = {}
    for games in results.values():
        for game in games:
            for row in game["rows"]:
                accumulated[row["name"]] = round(accumulated.get(row["name"], 0.0) + row["point"], 1)

    print("\n=== 検算（日別積算 vs /stats 累計） ===")
    mismatches = []
    for name, value in sorted(accumulated.items(), key=lambda kv: -kv[1]):
        official = stats.get(name)
        ok = official is not None and abs(official - value) < 0.05
        if not ok:
            mismatches.append((name, value, official))
        print(f'  {"OK" if ok else "NG"}  {name:<10s} 積算={value:>7.1f}  公式={official}')

    unplayed = sorted(set(stats) - set(accumulated))
    print(f"\n  未出場（/stats にいて結果に未登場）: {len(unplayed)}名")
    if mismatches:
        print(f"\n  ❌ 不一致 {len(mismatches)}件: {mismatches}")
        return 1
    print("\n  ✅ 全選手一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
