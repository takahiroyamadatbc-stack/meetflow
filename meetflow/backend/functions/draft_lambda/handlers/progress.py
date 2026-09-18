"""waveの開示・抽選・巡の進行（DESIGN.md §4.2 / §4.4 / §4.4.1 / §4.6）。

DESIGN.md §4.6の通り、状態遷移は自動では起きない。主催者が
「開示」→（必要なら）「抽選」→「次へ」とボタンを押して進める。
"""

import secrets

from meetflow_common import now_iso_ms, success_response

from . import repository as repo
from . import rules
from .drafts import _draft_summary, _load_draft_for_member, _require_host, _require_status
from errors import DraftError


def reveal(user_id: str, event: dict) -> dict:
    """POST /drafts/{draftId}/reveal — 全員の指名を一斉公開する。

    重複も余剰枠超過も無ければ、この時点でそのwaveの指名はすべて確定する
    （抽選ボタンは出ない）。どちらかがあれば PENDING のまま残し、
    主催者の「抽選」を待つ。
    """
    draft, _ = _load_draft_for_member(user_id, event)
    _require_host(draft, user_id)
    _require_status(draft, repo.STATUS_NOMINATING)

    draft_id = draft["draftId"]
    round_no, wave = int(draft["round"]), int(draft["wave"])
    participants = repo.list_participants(draft_id)
    picks = repo.list_wave_picks(draft_id, round_no, wave)

    expected = {
        p["userId"] for p in participants if int(p.get("playerCount", 0)) < round_no
    }
    pending = sorted(expected - {p["userId"] for p in picks})
    if pending:
        raise DraftError(
            "PICKS_NOT_COMPLETE",
            f"未提出の参加者が{len(pending)}人います。全員の提出後に開示できます",
        )

    surplus = int(draft["femaleSurplusRemaining"])
    if _needs_lottery(picks, participants, surplus):
        # 抽選が要る場合はここでは状態だけ動かす。誰が誰と被ったかは
        # 開示された指名一覧から画面側で分かる。
        operations = [_state_op(draft, repo.STATUS_REVEAL, round_no, wave)]
        repo.transact_write(operations)
        return success_response(_reveal_payload(draft, repo.STATUS_REVEAL, picks, True))

    operations, new_surplus = _confirm_operations(
        draft, picks, participants, losers=[], lotteries=[]
    )
    operations.append(
        _state_op(draft, repo.STATUS_REVEAL, round_no, wave, surplus=new_surplus)
    )
    repo.transact_write(operations)
    return success_response(_reveal_payload(draft, repo.STATUS_REVEAL, picks, False))


def run_lottery(user_id: str, event: dict) -> dict:
    """POST /drafts/{draftId}/lottery — 抽選を実行して当選者を確定する。

    解決順は DESIGN.md §4.4.1 の通り ①同一選手被り → ②女流余剰枠。
    抽選結果は LotteryLog に候補者ごと残す（§4.14: 検証は操作ログのみ）。
    """
    draft, _ = _load_draft_for_member(user_id, event)
    _require_host(draft, user_id)
    _require_status(draft, repo.STATUS_REVEAL)

    draft_id = draft["draftId"]
    round_no, wave = int(draft["round"]), int(draft["wave"])
    participants = repo.list_participants(draft_id)
    picks = [
        p
        for p in repo.list_wave_picks(draft_id, round_no, wave)
        if p["outcome"] == repo.PICK_PENDING
    ]
    if not picks:
        raise DraftError("DRAFT_INVALID_STATUS", "抽選が必要な指名がありません")

    female_by_user = {
        p["userId"]: int(p.get("femaleCount", 0)) > 0 for p in participants
    }
    resolved, losers, lotteries = rules.resolve_wave(
        [
            {
                "userId": p["userId"],
                "playerId": p["playerId"],
                "isFemale": bool(p["isFemale"]),
                "hasFemale": female_by_user.get(p["userId"], False),
            }
            for p in picks
        ],
        female_surplus_remaining=int(draft["femaleSurplusRemaining"]),
        draw=_draw,
    )

    winner_keys = {(r["userId"], r["playerId"]) for r in resolved}
    confirmed_picks = [p for p in picks if (p["userId"], p["playerId"]) in winner_keys]
    name_by_player = {p["playerId"]: p["playerName"] for p in picks}
    operations, new_surplus = _confirm_operations(
        draft, confirmed_picks, participants, losers=losers, lotteries=lotteries,
        name_by_player=name_by_player,
    )
    operations.append(
        _state_op(draft, repo.STATUS_LOTTERY, round_no, wave, surplus=new_surplus)
    )
    repo.transact_write(operations)

    return success_response(
        {
            **_draft_summary({**draft, "status": repo.STATUS_LOTTERY,
                              "version": int(draft["version"]) + 1,
                              "femaleSurplusRemaining": new_surplus}),
            "lotteries": lotteries,
            "loserUserIds": losers,
        }
    )


def advance(user_id: str, event: dict) -> dict:
    """POST /drafts/{draftId}/advance — 次のwave / 次の巡 / 完了へ進む。"""
    draft, _ = _load_draft_for_member(user_id, event)
    _require_host(draft, user_id)
    _require_status(draft, repo.STATUS_REVEAL, repo.STATUS_LOTTERY)

    draft_id = draft["draftId"]
    round_no = int(draft["round"])
    wave = int(draft["wave"])
    participants = repo.list_participants(draft_id)

    if any(int(p.get("playerCount", 0)) < round_no for p in participants):
        # 落選者が残っている: 同じ巡のまま次のwaveへ（DESIGN.md §4.2）。
        status, next_round, next_wave = repo.STATUS_NOMINATING, round_no, wave + 1
    elif round_no < rules.ROUNDS:
        status, next_round, next_wave = repo.STATUS_NOMINATING, round_no + 1, 1
    else:
        status, next_round, next_wave = repo.STATUS_COMPLETED, round_no, wave

    repo.transact_write([_state_op(draft, status, next_round, next_wave)])
    return success_response(
        _draft_summary(
            {
                **draft,
                "status": status,
                "round": next_round,
                "wave": next_wave,
                "version": int(draft["version"]) + 1,
            }
        )
    )


# --- 内部ヘルパー -----------------------------------------------------------


def _draw(candidates: list) -> str:
    """抽選。候補から1人を選ぶ。

    `random`ではなく`secrets`を使う。当たり外れが参加者の利害に直結する
    ため、プロセスごとに予測可能なシードで動くPRNGは避ける。
    """
    return secrets.choice(sorted(candidates))


def _needs_lottery(picks: list, participants: list, surplus: int) -> bool:
    """このwaveに抽選が必要か（同一選手被り or 女流余剰枠の超過）。"""
    player_ids = [p["playerId"] for p in picks]
    if len(player_ids) != len(set(player_ids)):
        return True
    female_by_user = {
        p["userId"]: int(p.get("femaleCount", 0)) > 0 for p in participants
    }
    surplus_picks = sum(
        1
        for p in picks
        if rules.consumes_surplus(female_by_user.get(p["userId"], False), bool(p["isFemale"]))
    )
    return surplus_picks > surplus


def _confirm_operations(
    draft: dict,
    confirmed_picks: list,
    participants: list,
    *,
    losers: list,
    lotteries: list,
    name_by_player: dict = None,
):
    """確定した指名をDynamoDBに書くための操作リストを組み立てる。

    PlayerLockには`attribute_not_exists`条件を付ける（DESIGN.md §5）。
    「同じ選手を2人が確保する」事故を、アプリのロジックではなくDynamoDBの
    条件付き書き込みで物理的に不可能にするため。二重に開示ボタンを押した
    ようなケースでも、後発のトランザクションが丸ごと失敗する。
    """
    draft_id = draft["draftId"]
    round_no, wave = int(draft["round"]), int(draft["wave"])
    now = now_iso_ms()
    female_by_user = {
        p["userId"]: int(p.get("femaleCount", 0)) > 0 for p in participants
    }
    players = {p["playerId"]: p for p in repo.list_players(draft_id)}

    surplus = int(draft["femaleSurplusRemaining"])
    operations = []
    for pick in confirmed_picks:
        player = players[pick["playerId"]]
        is_female = bool(player["isFemale"])
        consumed = rules.consumes_surplus(
            female_by_user.get(pick["userId"], False), is_female
        )
        if consumed:
            surplus -= 1
        operations.append(
            {
                "Put": {
                    "Item": {
                        "PK": repo.draft_pk(draft_id),
                        "SK": f"LOCK#{pick['playerId']}",
                        "playerId": pick["playerId"],
                        "userId": pick["userId"],
                        "round": round_no,
                        "wave": wave,
                    },
                    "ConditionExpression": "attribute_not_exists(PK)",
                }
            }
        )
        operations.append(
            {
                "Put": {
                    "Item": {
                        "PK": repo.draft_pk(draft_id),
                        "SK": f"ROSTER#{pick['userId']}#{pick['playerId']}",
                        "draftId": draft_id,
                        "userId": pick["userId"],
                        "playerId": pick["playerId"],
                        "playerName": player["name"],
                        "teamId": player["teamId"],
                        "teamName": player["teamName"],
                        "isFemale": is_female,
                        "round": round_no,
                        "wave": wave,
                        "consumedSurplus": consumed,
                        "confirmedAt": now,
                    }
                }
            }
        )
        operations.append(
            {
                "Update": {
                    "Key": {
                        "PK": repo.draft_pk(draft_id),
                        "SK": f"PARTICIPANT#{pick['userId']}",
                    },
                    "UpdateExpression": (
                        "SET playerCount = playerCount + :one, "
                        "femaleCount = femaleCount + :female"
                    ),
                    "ExpressionAttributeValues": {
                        ":one": 1,
                        ":female": 1 if is_female else 0,
                    },
                }
            }
        )
        operations.append(_pick_outcome_op(draft_id, pick, repo.PICK_CONFIRMED))

    for loser_id in losers:
        operations.append(
            _pick_outcome_op(
                draft_id, {"userId": loser_id, "round": round_no, "wave": wave},
                repo.PICK_LOST,
            )
        )

    for seq, lottery in enumerate(lotteries, start=1):
        operations.append(
            {
                "Put": {
                    "Item": {
                        "PK": repo.draft_pk(draft_id),
                        "SK": repo.lottery_sk(round_no, wave, seq),
                        "draftId": draft_id,
                        "round": round_no,
                        "wave": wave,
                        "type": lottery["type"],
                        "playerId": lottery["playerId"],
                        "playerName": (name_by_player or {}).get(lottery["playerId"]),
                        "candidates": lottery["candidates"],
                        "winnerUserId": lottery["winnerUserId"],
                        "drawnAt": now,
                    }
                }
            }
        )
    return operations, surplus


def _pick_outcome_op(draft_id: str, pick: dict, outcome: str):
    return {
        "Update": {
            "Key": {
                "PK": repo.draft_pk(draft_id),
                "SK": repo.pick_sk(int(pick["round"]), int(pick["wave"]), pick["userId"]),
            },
            "UpdateExpression": "SET #outcome = :outcome",
            "ExpressionAttributeNames": {"#outcome": "outcome"},
            "ExpressionAttributeValues": {":outcome": outcome},
        }
    }


def _state_op(draft: dict, status: str, round_no: int, wave: int, *, surplus: int = None):
    return repo.draft_state_update(
        draft_id=draft["draftId"],
        status=status,
        round_no=round_no,
        wave=wave,
        version=int(draft["version"]) + 1,
        expected_version=int(draft["version"]),
        updated_at=now_iso_ms(),
        female_surplus_remaining=surplus,
    )


def _reveal_payload(draft: dict, status: str, picks: list, lottery_required: bool):
    return {
        **_draft_summary({**draft, "status": status, "version": int(draft["version"]) + 1}),
        "lotteryRequired": lottery_required,
        "picks": [
            {
                "userId": p["userId"],
                "playerId": p["playerId"],
                "playerName": p["playerName"],
                "isFemale": bool(p["isFemale"]),
                "byProxy": bool(p.get("byProxy")),
            }
            for p in sorted(picks, key=lambda p: p["userId"])
        ],
    }
