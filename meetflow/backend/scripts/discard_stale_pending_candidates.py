"""
候補再生成時の重複防止ロジック（_discard_stale_pending_candidates、Issue #27）が
デプロイされる前に生成された、同一コミュニティ・同一開催条件（templateId）の
古いPENDING候補が積み残ったままになっている環境向けの、ワンショットの
クリーンアップスクリプト。

背景：matching_lambda/handlers/matching.py の generate_candidates は、
Issue #27の修正以降は候補生成のたびに同一templateIdの既存PENDING候補を
自動でDISCARDEDにするが、この修正が反映される前に複数回候補生成を実行
した環境では、過去のPENDING候補がDISCARDEDにならないまま残り続け、
候補一覧に大量の重複として表示されてしまう（例：候補47件）。

このスクリプトは_discard_stale_pending_candidatesと同じ判定基準
（対象コミュニティ×templateIdのMatchCandidateでstatus=PENDINGのもの。
CONFIRMED＝イベント化済みの候補には触れない）で、該当するMatchCandidateと
その配下のCandidateMemberをDISCARDEDに更新する。ハード削除ではなく
status更新に留めることで、既存のDISCARDED運用（再生成時の自動discard）
と整合させる。

使い方（backend/ディレクトリから実行）：
    .venv/Scripts/python.exe scripts/discard_stale_pending_candidates.py \
        --table dev-MeetFlowTable --community-id <communityId> \
        --template-id <templateId> --profile personal --dry-run

    # 内容を確認したら --dry-run を外して実行
    .venv/Scripts/python.exe scripts/discard_stale_pending_candidates.py \
        --table dev-MeetFlowTable --community-id <communityId> \
        --template-id <templateId> --profile personal

前提：
- 実行者のAWS認証情報（--profileまたは環境変数）にdynamodb:Query/UpdateItem権限が必要
- communityId・templateIdは対象の開催条件のもの（他テンプレートの候補は
  対象外。粒度はgenerate_candidates側のdiscardロジックと同じ）
"""

import argparse
import sys

import boto3
from boto3.dynamodb.conditions import Key


def _is_candidate_item(item: dict) -> bool:
    return "#MEMBER#" not in item["SK"]


def _query_all_candidates(table, community_id):
    key_condition = Key("PK").eq(f"COMMUNITY#{community_id}") & Key("SK").begins_with(
        "CANDIDATE#"
    )
    resp = table.query(KeyConditionExpression=key_condition)
    items = resp.get("Items", [])
    while "LastEvaluatedKey" in resp:
        resp = table.query(
            KeyConditionExpression=key_condition,
            ExclusiveStartKey=resp["LastEvaluatedKey"],
        )
        items.extend(resp.get("Items", []))
    return items


def main():
    # Windowsのコンソールコードページ（cp932等）では日本語のprint()が文字化け
    # することがあるため、標準出力をUTF-8に固定する。
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", required=True, help="対象DynamoDBテーブル名（例：dev-MeetFlowTable）")
    parser.add_argument("--community-id", required=True, help="対象コミュニティのcommunityId")
    parser.add_argument("--template-id", required=True, help="対象開催条件のtemplateId")
    parser.add_argument("--profile", default=None, help="AWS CLIプロファイル名")
    parser.add_argument("--region", default="ap-northeast-1")
    parser.add_argument("--dry-run", action="store_true", help="更新せず対象件数のみ表示する")
    args = parser.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    table = session.resource("dynamodb").Table(args.table)

    all_items = _query_all_candidates(table, args.community_id)
    stale = [
        item
        for item in all_items
        if _is_candidate_item(item)
        and item.get("templateId") == args.template_id
        and item.get("status") == "PENDING"
    ]

    print(f"走査件数（当該コミュニティのCANDIDATE#配下）: {len(all_items)}")
    print(f"対象件数（templateId={args.template_id} でstatus=PENDINGの候補）: {len(stale)}")

    updated = 0
    for item in stale:
        candidate_id = item["GSI2PK"].split("#", 1)[1]
        label = "DRY-RUN" if args.dry_run else "UPDATE"
        print(
            f"  [{label}] candidateId={candidate_id} "
            f"startTime={item.get('startTime')} members={sorted(item.get('members', []))}"
        )
        if args.dry_run:
            continue

        table.update_item(
            Key={"PK": item["PK"], "SK": item["SK"]},
            UpdateExpression="SET #status = :discarded",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":discarded": "DISCARDED"},
        )
        for uid in item.get("members", []):
            table.update_item(
                Key={
                    "PK": f"COMMUNITY#{args.community_id}",
                    "SK": f"CANDIDATE#{candidate_id}#MEMBER#{uid}",
                },
                UpdateExpression="SET #status = :discarded",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":discarded": "DISCARDED"},
            )
        updated += 1

    print()
    if args.dry_run:
        print("dry-runのため更新は行っていません。内容を確認後、--dry-runを外して再実行してください。")
    else:
        print(f"更新件数（MatchCandidate）: {updated}")


if __name__ == "__main__":
    main()
