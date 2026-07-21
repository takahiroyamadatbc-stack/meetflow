"""
既存のGameResult/GameResultChipアイテムに、コミュニティ内ランキング機能
（Issue #40）で追加したGSI2PK/GSI2SK属性を後付けするワンショットの
バックフィルスクリプト。

対象：DynamoDB物理設計書v1.19 §3.13。本属性追加（Issue #40）より前に
登録された対局データはGSI2PK/GSI2SKを持たないため、コミュニティ内
ランキング（GET /communities/{communityId}/rankings）の集計から漏れる。
新規の対局登録（result_lambda/handlers/results.py の _write_session_items）
は既にGSI2PK/GSI2SKを設定しているため、このスクリプトが必要になるのは
Issue #40より前にデータが存在する環境（デプロイ済みのdev環境等）のみ。

使い方（backend/ディレクトリから実行）：
    .venv/Scripts/python.exe scripts/backfill_game_result_gsi2.py \
        --table dev-MeetFlowTable --profile personal --dry-run

    # 内容を確認したら --dry-run を外して実行
    .venv/Scripts/python.exe scripts/backfill_game_result_gsi2.py \
        --table dev-MeetFlowTable --profile personal

前提：
- 実行者のAWS認証情報（--profileまたは環境変数）にdynamodb:Scan/UpdateItem権限が必要
- テーブル全件をScanする（GameResult/GameResultChipの判別はSKに"#RESULT#"/
  "#CHIP#"を含むかどうかで行っており、これはresults.py get_user_results()等の
  既存の判別ロジックと同じ。DynamoDB側の単純な属性フィルタでは表現しづらい
  ため、取得後にPython側で判定する）
"""

import argparse

import boto3


def _is_game_result_or_chip(item: dict) -> bool:
    pk = item.get("PK", "")
    sk = item.get("SK", "")
    return pk.startswith("EVENT#") and ("#RESULT#" in sk or "#CHIP#" in sk)


def _needs_backfill(item: dict) -> bool:
    return "GSI2PK" not in item or "GSI2SK" not in item


def _build_gsi2_attrs(item: dict):
    """results.py _write_session_items() が新規書き込み時に設定する
    GSI2PK/GSI2SKと同じ値を、既存の属性（GSI1SK・gameType・playedAt）から
    逆算する。GSI1SKは`COMMUNITY#{communityId}#{playedAt}`形式（communityId
    はgenerate_id()のuuid4().hexのため"#"を含まない）。
    """
    gsi1sk = item.get("GSI1SK", "")
    game_type = item.get("gameType")
    played_at = item.get("playedAt")
    if not gsi1sk.startswith("COMMUNITY#") or not game_type or not played_at:
        return None
    community_id = gsi1sk.split("#", 2)[1]
    return {
        "GSI2PK": f"COMMUNITY#{community_id}#{game_type}",
        "GSI2SK": played_at,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", required=True, help="対象DynamoDBテーブル名（例：dev-MeetFlowTable）")
    parser.add_argument("--profile", default=None, help="AWS CLIプロファイル名")
    parser.add_argument("--region", default="ap-northeast-1")
    parser.add_argument("--dry-run", action="store_true", help="更新せず対象件数のみ表示する")
    args = parser.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    table = session.resource("dynamodb").Table(args.table)

    scanned = 0
    targets = 0
    updated = 0
    skipped_incomplete = 0

    scan_kwargs = {}
    while True:
        resp = table.scan(**scan_kwargs)
        items = resp.get("Items", [])
        scanned += len(items)
        for item in items:
            if not _is_game_result_or_chip(item) or not _needs_backfill(item):
                continue
            targets += 1
            attrs = _build_gsi2_attrs(item)
            if attrs is None:
                skipped_incomplete += 1
                print(f"  [SKIP] 属性不足のため算出不可: PK={item.get('PK')} SK={item.get('SK')}")
                continue
            label = "DRY-RUN" if args.dry_run else "UPDATE"
            print(f"  [{label}] PK={item['PK']} SK={item['SK']} -> {attrs}")
            if not args.dry_run:
                table.update_item(
                    Key={"PK": item["PK"], "SK": item["SK"]},
                    UpdateExpression="SET GSI2PK = :pk, GSI2SK = :sk",
                    ExpressionAttributeValues={":pk": attrs["GSI2PK"], ":sk": attrs["GSI2SK"]},
                )
                updated += 1
        if "LastEvaluatedKey" not in resp:
            break
        scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    print()
    print(f"走査件数: {scanned}")
    print(f"対象件数（GameResult/GameResultChipでGSI2未設定）: {targets}")
    if args.dry_run:
        print("dry-runのため更新は行っていません。内容を確認後、--dry-runを外して再実行してください。")
    else:
        print(f"更新件数: {updated}")
        if skipped_incomplete:
            print(f"属性不足でスキップ: {skipped_incomplete}件（手動確認が必要）")


if __name__ == "__main__":
    main()
