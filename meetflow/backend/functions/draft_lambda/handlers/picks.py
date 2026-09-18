"""指名の受付（DESIGN.md §4.2 NOMINATING / §4.3 女性枠ルール / §4.7 代理指名）。"""

from botocore.exceptions import ClientError

from meetflow_common import now_iso_ms, parse_body, success_response

from . import repository as repo
from . import rules
from .drafts import _load_draft_for_member, _require_host, _require_status
from errors import DraftError


def submit_pick(user_id: str, event: dict) -> dict:
    """POST /drafts/{draftId}/picks — 参加者が自分の指名を非公開で提出する。"""
    draft, participant = _load_draft_for_member(user_id, event)
    if participant is None:
        raise DraftError("NOT_DRAFT_PARTICIPANT", "このドラフトの参加者ではありません")
    player_id = _require_player_id(event)
    return _submit(draft, participant, player_id, by_proxy=False)


def submit_proxy_pick(user_id: str, event: dict) -> dict:
    """POST /drafts/{draftId}/picks/proxy — 主催者による代理指名。

    DESIGN.md §4.7: 制限時間は設けない代わりに、どうしても連絡がつかない
    参加者の分だけ主催者が代わりに指名できる。
    """
    draft, _ = _load_draft_for_member(user_id, event)
    _require_host(draft, user_id)

    body = parse_body(event)
    target_user_id = body.get("userId")
    player_id = body.get("playerId")
    if not target_user_id or not player_id:
        raise DraftError("DRAFT_VALIDATION_ERROR", "userIdとplayerIdを指定してください")

    participant = next(
        (p for p in repo.list_participants(draft["draftId"]) if p["userId"] == target_user_id),
        None,
    )
    if participant is None:
        raise DraftError("NOT_DRAFT_PARTICIPANT", "指定されたユーザーは参加者ではありません")
    return _submit(draft, participant, player_id, by_proxy=True)


def _require_player_id(event: dict) -> str:
    player_id = parse_body(event).get("playerId")
    if not player_id:
        raise DraftError("DRAFT_VALIDATION_ERROR", "playerIdを指定してください")
    return player_id


def _submit(draft: dict, participant: dict, player_id: str, *, by_proxy: bool) -> dict:
    _require_status(draft, repo.STATUS_NOMINATING)
    draft_id = draft["draftId"]
    round_no, wave = int(draft["round"]), int(draft["wave"])
    user_id = participant["userId"]

    # その巡で既に選手を確保している人は、この巡ではもう指名しない
    # （waveが進むのは落選者だけのため）。
    if int(participant.get("playerCount", 0)) >= round_no:
        raise DraftError("PICK_NOT_ALLOWED", "この巡の指名はすでに確定しています")

    player = _load_player(draft_id, player_id)
    if any(lock["SK"] == f"LOCK#{player_id}" for lock in repo.list_locks(draft_id)):
        raise DraftError("PLAYER_ALREADY_TAKEN", f"{player['name']}はすでに指名されています")

    rules.validate_pick(
        round_no=round_no,
        has_female=int(participant.get("femaleCount", 0)) > 0,
        pick_is_female=bool(player["isFemale"]),
        female_surplus_remaining=int(draft["femaleSurplusRemaining"]),
    )

    item = {
        "PK": repo.draft_pk(draft_id),
        "SK": repo.pick_sk(round_no, wave, user_id),
        "draftId": draft_id,
        "userId": user_id,
        "playerId": player_id,
        "playerName": player["name"],
        "isFemale": bool(player["isFemale"]),
        "round": round_no,
        "wave": wave,
        "outcome": repo.PICK_PENDING,
        "byProxy": by_proxy,
        "submittedAt": now_iso_ms(),
    }
    try:
        # 同じwaveで二重に提出させない。指名を後から差し替えられると、
        # 開示直前に他人の動きを見て変える余地が生まれてしまう。
        repo.get_draft_table().put_item(
            Item=item, ConditionExpression="attribute_not_exists(PK)"
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise DraftError(
                "PICK_ALREADY_SUBMITTED", "この巡の指名はすでに提出済みです"
            ) from exc
        raise

    return success_response(
        {
            "round": round_no,
            "wave": wave,
            "userId": user_id,
            "playerId": player_id,
            "playerName": player["name"],
            "byProxy": by_proxy,
        },
        status_code=201,
    )


def _load_player(draft_id: str, player_id: str) -> dict:
    """ドラフト作成時に固定したスナップショットから選手を引く。"""
    item = repo.get_draft_table().get_item(
        Key={"PK": repo.draft_pk(draft_id), "SK": f"PLAYER#{player_id}"}
    ).get("Item")
    if item is None:
        raise DraftError("PLAYER_NOT_FOUND", "選手が見つかりません")
    return item
