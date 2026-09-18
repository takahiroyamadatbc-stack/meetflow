"""ドラフトの作成・一覧・状態取得・開始（DESIGN.md §4.2 / §4.13）。"""

from meetflow_common import (
    generate_id,
    get_table,
    now_iso_ms,
    parse_body,
    require_membership,
    resolve_display_name,
    success_response,
)

import repository as repo
import rules
from errors import DraftError

# DESIGN.md §2: 2026-27シーズンが対象。将来シーズンは選手マスタを差し替える。
DEFAULT_SEASON = "2026-27"


def create_draft(user_id: str, event: dict) -> dict:
    """POST /communities/{communityId}/drafts

    DESIGN.md §4.13: 参加者は既存コミュニティのACTIVEメンバーから選ぶ。
    作成は他の管理操作と揃えてOWNER/ADMINのみで、作成者が主催者になる。
    """
    community_id = event["pathParameters"]["communityId"]
    main_table = get_table()
    require_membership(main_table, community_id, user_id, roles=("OWNER", "ADMIN"))

    body = parse_body(event)
    name = (body.get("name") or "").strip()
    if not name:
        raise DraftError("DRAFT_VALIDATION_ERROR", "ドラフト名を入力してください")
    season = body.get("season") or DEFAULT_SEASON
    participant_ids = body.get("participantUserIds") or []
    if len(set(participant_ids)) != len(participant_ids):
        raise DraftError("DRAFT_VALIDATION_ERROR", "参加者が重複しています")

    players = repo.list_master_players(season)
    if not players:
        raise DraftError(
            "ML_PLAYERS_NOT_SEEDED",
            f"{season}シーズンの選手マスタが登録されていません",
        )
    female_count = sum(1 for p in players if p.get("isFemale"))

    _validate_participant_count(len(participant_ids), female_count)
    memberships = _load_active_memberships(main_table, community_id, participant_ids)

    draft_id = generate_id()
    created_at = now_iso_ms()
    draft_item = {
        "PK": repo.draft_pk(draft_id),
        "SK": "METADATA",
        "GSI1PK": f"COMMUNITY#{community_id}",
        "GSI1SK": f"DRAFT#{created_at}#{draft_id}",
        "draftId": draft_id,
        "communityId": community_id,
        "name": name,
        "season": season,
        "hostUserId": user_id,
        "status": repo.STATUS_SETUP,
        "round": 0,
        "wave": 0,
        # DESIGN.md §4.12: ポーリングで「変わっていない」を安く判定するための
        # 単調増加リビジョン。状態を書き換える操作は必ずこれを+1する。
        "version": 1,
        "participantCount": len(participant_ids),
        "femalePlayerCount": female_count,
        "femaleSurplusRemaining": rules.initial_female_surplus(
            female_count, len(participant_ids)
        ),
        # DESIGN.md §4.15: 未設定のうちはシーズン全体を集計する。
        "regularSeasonEndDate": body.get("regularSeasonEndDate"),
        "createdAt": created_at,
        "updatedAt": created_at,
    }

    operations = [{"Put": {"Item": draft_item}}]
    for participant_id in participant_ids:
        membership, profile = memberships[participant_id]
        operations.append(
            {
                "Put": {
                    "Item": {
                        "PK": repo.draft_pk(draft_id),
                        "SK": f"PARTICIPANT#{participant_id}",
                        "GSI1PK": f"USER#{participant_id}",
                        "GSI1SK": f"DRAFT#{created_at}#{draft_id}",
                        "draftId": draft_id,
                        "userId": participant_id,
                        "displayName": resolve_display_name(membership, profile),
                        "playerCount": 0,
                        "femaleCount": 0,
                    }
                }
            }
        )
    for player in players:
        operations.append(
            {
                "Put": {
                    "Item": {
                        "PK": repo.draft_pk(draft_id),
                        "SK": f"PLAYER#{player['playerId']}",
                        "playerId": player["playerId"],
                        "name": player["name"],
                        "kana": player.get("kana"),
                        "teamId": player["teamId"],
                        "teamName": player["teamName"],
                        "isFemale": bool(player.get("isFemale")),
                    }
                }
            }
        )
    repo.transact_write(operations)

    return success_response(_draft_summary(draft_item), status_code=201)


def list_drafts(user_id: str, event: dict) -> dict:
    """GET /communities/{communityId}/drafts"""
    community_id = event["pathParameters"]["communityId"]
    require_membership(get_table(), community_id, user_id)
    drafts = repo.list_community_drafts(community_id)
    return success_response({"drafts": [_draft_summary(d) for d in drafts]})


def get_draft(user_id: str, event: dict) -> dict:
    """GET /drafts/{draftId}

    参加者・主催者のポーリング先（DESIGN.md §4.12）。`version`だけ見て
    変化が無ければクライアントは再描画しない。

    DESIGN.md §4.6: 開示前は主催者画面にも「何人提出済み」しか出さない。
    他人の指名内容は、REVEAL以降でなければレスポンスに含めない。
    """
    draft, _ = _load_draft_for_member(user_id, event)
    participants = repo.list_participants(draft["draftId"])
    rosters = repo.list_rosters(draft["draftId"])
    payload = _draft_summary(draft)
    payload["participants"] = [
        {
            "userId": p["userId"],
            "displayName": p["displayName"],
            "playerCount": int(p.get("playerCount", 0)),
            "femaleCount": int(p.get("femaleCount", 0)),
        }
        for p in sorted(participants, key=lambda p: p["userId"])
    ]
    payload["rosters"] = _group_rosters(rosters)
    payload["currentWave"] = _current_wave_view(draft, participants, user_id)
    return success_response(payload)


def get_rosters(user_id: str, event: dict) -> dict:
    """GET /drafts/{draftId}/rosters — 確定したチームの閲覧。"""
    draft, _ = _load_draft_for_member(user_id, event)
    return success_response({"rosters": _group_rosters(repo.list_rosters(draft["draftId"]))})


def get_lotteries(user_id: str, event: dict) -> dict:
    """GET /drafts/{draftId}/lotteries — 抽選の記録（DESIGN.md §4.14）。"""
    draft, _ = _load_draft_for_member(user_id, event)
    lotteries = repo.list_lotteries(draft["draftId"])
    return success_response(
        {
            "lotteries": [
                {
                    "round": int(item["round"]),
                    "wave": int(item["wave"]),
                    "type": item["type"],
                    "playerId": item.get("playerId"),
                    "playerName": item.get("playerName"),
                    "candidates": item["candidates"],
                    "winnerUserId": item["winnerUserId"],
                    "drawnAt": item["drawnAt"],
                }
                for item in lotteries
            ]
        }
    )


def get_players(user_id: str, event: dict) -> dict:
    """GET /drafts/{draftId}/players — 指名対象の選手一覧。

    ドラフト作成時に固定したスナップショット（DESIGN.md §6.2）に、
    誰が確保済みかを載せて返す。指名画面が「選べる選手」を出すために使う。
    """
    draft, _ = _load_draft_for_member(user_id, event)
    draft_id = draft["draftId"]
    taken = {
        lock["SK"].removeprefix("LOCK#"): lock["userId"] for lock in repo.list_locks(draft_id)
    }
    players = [
        {
            "playerId": player["playerId"],
            "name": player["name"],
            "kana": player.get("kana"),
            "teamId": player["teamId"],
            "teamName": player["teamName"],
            "isFemale": bool(player["isFemale"]),
            "takenByUserId": taken.get(player["playerId"]),
        }
        for player in repo.list_players(draft_id)
    ]
    # チームごとにまとめて表示するため、チーム→名前の順に並べて返す。
    players.sort(key=lambda p: (p["teamName"], p["playerId"]))
    return success_response({"players": players})


def start_draft(user_id: str, event: dict) -> dict:
    """POST /drafts/{draftId}/start — SETUP → NOMINATING(1, 1)。主催者のみ。"""
    draft, _ = _load_draft_for_member(user_id, event)
    _require_host(draft, user_id)
    _require_status(draft, repo.STATUS_SETUP)
    _validate_participant_count(
        int(draft["participantCount"]), int(draft["femalePlayerCount"])
    )

    updated = _advance_state(draft, status=repo.STATUS_NOMINATING, round_no=1, wave=1)
    return success_response(_draft_summary(updated))


# --- 内部ヘルパー -----------------------------------------------------------


def _validate_participant_count(count: int, female_count: int) -> None:
    upper = rules.max_participants(female_count)
    if count < rules.MIN_PARTICIPANTS or count > upper:
        raise DraftError(
            "DRAFT_VALIDATION_ERROR",
            f"参加人数は{rules.MIN_PARTICIPANTS}〜{upper}人にしてください（現在{count}人）",
        )


def _load_active_memberships(main_table, community_id: str, participant_ids: list):
    """参加者が全員そのコミュニティのACTIVEメンバーであることを確認する。

    表示名の解決に必要なMembership/Userアイテムもここで一緒に返し、
    呼び出し元が同じアイテムを取り直さずに済むようにしている。
    """
    result = {}
    for participant_id in participant_ids:
        membership = main_table.get_item(
            Key={"PK": f"COMMUNITY#{community_id}", "SK": f"MEMBER#{participant_id}"}
        ).get("Item")
        if membership is None or membership.get("status") != "ACTIVE":
            raise DraftError(
                "DRAFT_VALIDATION_ERROR",
                "コミュニティに所属していないメンバーが参加者に含まれています",
            )
        profile = main_table.get_item(
            Key={"PK": f"USER#{participant_id}", "SK": "PROFILE"}
        ).get("Item")
        result[participant_id] = (membership, profile)
    return result


def _load_draft_for_member(user_id: str, event: dict):
    """ドラフトを読み、呼び出し元がそのコミュニティのメンバーかを確認する。

    参加者でなくても同じコミュニティのメンバーなら閲覧はできる
    （プロジェクター用の主催者画面を別の人が開く、観戦する等）。
    戻り値の2つ目は、その人がドラフトの参加者ならParticipantアイテム。
    """
    draft_id = event["pathParameters"]["draftId"]
    draft = repo.get_draft(draft_id)
    if draft is None:
        raise DraftError("DRAFT_NOT_FOUND", "ドラフトが見つかりません")
    require_membership(get_table(), draft["communityId"], user_id)
    participant = next(
        (p for p in repo.list_participants(draft_id) if p["userId"] == user_id), None
    )
    return draft, participant


def _require_host(draft: dict, user_id: str) -> None:
    if draft["hostUserId"] != user_id:
        raise DraftError("NOT_DRAFT_HOST", "この操作は主催者のみ実行できます")


def _require_status(draft: dict, *expected: str) -> None:
    if draft["status"] not in expected:
        raise DraftError(
            "DRAFT_INVALID_STATUS",
            f"現在の状態（{draft['status']}）ではこの操作はできません",
        )


def _advance_state(draft: dict, *, status: str, round_no: int, wave: int) -> dict:
    """Draftの状態を1つ進める。

    `version`の一致を条件にすることで、主催者が同じボタンを二度押ししたり、
    2つの画面から同時に操作したときに、片方だけが通るようにする。
    """
    now = now_iso_ms()
    version = int(draft["version"]) + 1
    repo.update_draft_state(
        draft_id=draft["draftId"],
        status=status,
        round_no=round_no,
        wave=wave,
        version=version,
        expected_version=int(draft["version"]),
        updated_at=now,
    )
    return {
        **draft,
        "status": status,
        "round": round_no,
        "wave": wave,
        "version": version,
        "updatedAt": now,
    }


def _draft_summary(draft: dict) -> dict:
    return {
        "draftId": draft["draftId"],
        "communityId": draft["communityId"],
        "name": draft["name"],
        "season": draft["season"],
        "hostUserId": draft["hostUserId"],
        "status": draft["status"],
        "round": int(draft.get("round", 0)),
        "wave": int(draft.get("wave", 0)),
        "rounds": rules.ROUNDS,
        "version": int(draft["version"]),
        "participantCount": int(draft["participantCount"]),
        "femalePlayerCount": int(draft["femalePlayerCount"]),
        "femaleSurplusRemaining": int(draft["femaleSurplusRemaining"]),
        "regularSeasonEndDate": draft.get("regularSeasonEndDate"),
        "createdAt": draft["createdAt"],
        "updatedAt": draft["updatedAt"],
    }


def _group_rosters(rosters: list) -> dict:
    grouped = {}
    for item in sorted(rosters, key=lambda r: (r["userId"], int(r["round"]))):
        grouped.setdefault(item["userId"], []).append(
            {
                "playerId": item["playerId"],
                "playerName": item["playerName"],
                "teamId": item["teamId"],
                "teamName": item["teamName"],
                "isFemale": bool(item["isFemale"]),
                "round": int(item["round"]),
                "wave": int(item["wave"]),
            }
        )
    return grouped


def _current_wave_view(draft: dict, participants: list, viewer_id: str) -> dict | None:
    """進行中のwaveの状況。

    DESIGN.md §4.6 / §4.7: 開示前に見せてよいのは「誰が提出済みか」だけ。
    未提出者を出すのは主催者が催促できるようにするためで、中身は出さない。
    """
    if draft["status"] == repo.STATUS_SETUP or draft["status"] == repo.STATUS_COMPLETED:
        return None
    round_no, wave = int(draft["round"]), int(draft["wave"])
    picks = repo.list_wave_picks(draft["draftId"], round_no, wave)
    submitted = {p["userId"] for p in picks}
    expected = {
        p["userId"] for p in participants if int(p.get("playerCount", 0)) < round_no
    }
    revealed = draft["status"] in (repo.STATUS_REVEAL, repo.STATUS_LOTTERY)
    view = {
        "round": round_no,
        "wave": wave,
        "expectedUserIds": sorted(expected),
        "submittedUserIds": sorted(submitted & expected),
        "pendingUserIds": sorted(expected - submitted),
        "revealed": revealed,
    }
    if revealed:
        # PENDINGが残っていれば抽選待ち（DESIGN.md §4.2の分岐）。
        view["lotteryRequired"] = any(
            p["outcome"] == repo.PICK_PENDING for p in picks
        )
        view["picks"] = [
            {
                "userId": p["userId"],
                "playerId": p["playerId"],
                "playerName": p["playerName"],
                "outcome": p["outcome"],
                "byProxy": bool(p.get("byProxy")),
            }
            for p in sorted(picks, key=lambda p: p["userId"])
        ]
    else:
        # 開示前でも自分の指名だけは確認できる（押し間違いに気づけるように）。
        own = next((p for p in picks if p["userId"] == viewer_id), None)
        view["myPick"] = (
            None
            if own is None
            else {"playerId": own["playerId"], "playerName": own["playerName"]}
        )
    return view
