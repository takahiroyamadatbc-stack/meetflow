"""
Mリーグの選手マスタ（MLPlayer）をDraftTableに投入するシードスクリプト。

対象：docs/draft/DESIGN.md §3・§7。選手は40人しかおらずシーズン中は
ほぼ変動しないため、ランタイムでスクレイピングはしない。ローカルで
作ったJSONをリポジトリに置き、デプロイのタイミングで人手でこれを流す。

投入先は本体テーブルではなく **DraftTable**（DESIGN.md §4.11の完全分離）。

    PK=MLPLAYER#{season}  SK=PLAYER#{playerId}

使い方（backend/ディレクトリから実行）：
    python scripts/seed_ml_players.py --table dev-MeetFlowDraftTable --dry-run

    # 内容を確認したら --dry-run を外して実行
    python scripts/seed_ml_players.py --table dev-MeetFlowDraftTable

前提：
- 実行者のAWS認証情報に dynamodb:PutItem 権限が必要
- 既存アイテムは上書きする（冪等。シーズン中の選手入れ替えにも使える）
- `isFemale` はスクレイピングでは取得できず手動メンテナンスしている
  （DESIGN.md §3「性別フラグについて」）。JSONを直接編集して流し直すこと
"""

import argparse
import json
import sys
from pathlib import Path

import boto3

# backend/scripts/ から見た docs/draft/ の位置。
_DEFAULT_JSON = (
    Path(__file__).resolve().parent.parent.parent / "docs" / "draft" / "players_2026-27.json"
)


def _load(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    season = data["season"]
    players = []
    for team in data["teams"]:
        for player in team["players"]:
            players.append(
                {
                    "PK": f"MLPLAYER#{season}",
                    "SK": f"PLAYER#{player['playerId']}",
                    "season": season,
                    "playerId": player["playerId"],
                    "name": player["name"],
                    "kana": player.get("kana"),
                    "teamId": team["teamId"],
                    "teamName": team["teamName"],
                    "isFemale": bool(player["isFemale"]),
                }
            )
    return season, data, players


def _verify(data: dict, players: list) -> list:
    """JSONのヘッダ（teamCount / playerCount / femaleCount）と中身の整合を見る。

    女性の人数は女流余剰枠ルール（DESIGN.md §4.3(b)）の成立条件に直結する
    ため、ヘッダとの食い違いは黙って流さずここで止める。
    """
    problems = []
    if len(data["teams"]) != data["teamCount"]:
        problems.append(f"teamCount={data['teamCount']} だが実際は{len(data['teams'])}チーム")
    if len(players) != data["playerCount"]:
        problems.append(f"playerCount={data['playerCount']} だが実際は{len(players)}人")
    female = sum(1 for p in players if p["isFemale"])
    if female != data["femaleCount"]:
        problems.append(f"femaleCount={data['femaleCount']} だが実際は{female}人")
    ids = [p["playerId"] for p in players]
    if len(set(ids)) != len(ids):
        problems.append("playerIdが重複している")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", required=True, help="DraftTable名（例: dev-MeetFlowDraftTable）")
    parser.add_argument("--json", type=Path, default=_DEFAULT_JSON, help="選手マスタJSON")
    parser.add_argument("--profile", default=None, help="AWSプロファイル名")
    parser.add_argument("--region", default="ap-northeast-1")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    season, data, players = _load(args.json)
    problems = _verify(data, players)
    if problems:
        print("選手マスタJSONに不整合があります:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    female = sum(1 for p in players if p["isFemale"])
    print(f"{season}シーズン: {len(data['teams'])}チーム / {len(players)}人 / うち女性{female}人")
    print(f"投入先: {args.table}")
    if args.dry_run:
        for player in players:
            mark = "♀" if player["isFemale"] else "  "
            print(f"  {mark} {player['playerId']:<24} {player['name']:<8} {player['teamName']}")
        print("\n--dry-run のため書き込みはしていません")
        return 0

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    table = session.resource("dynamodb").Table(args.table)
    with table.batch_writer() as batch:
        for player in players:
            batch.put_item(Item=player)
    print(f"{len(players)}件を投入しました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
