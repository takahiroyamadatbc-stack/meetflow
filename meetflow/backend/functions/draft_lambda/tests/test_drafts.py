"""ドラフト会議のフロー（DESIGN.md §4.2 / §4.3 / §4.6 / §4.7）の結合テスト。"""

import json

import pytest

from handlers import repository as repo
from _factories import api_event, make_players, put_membership, put_profile, seed_players, setup_community
from errors import DraftError
from handlers import drafts, picks, progress

HOST = "host"
MEMBERS = ("u1", "u2")


def _submit_all(draft_id, assignments):
    for user_id, player_id in assignments.items():
        _pick(draft_id, user_id, player_id)


def _create(user_id=HOST, *, community_id="c1", participants=None, name="Mリーグドラフト2026-27"):
    return json.loads(
        drafts.create_draft(
            user_id,
            api_event(
                path_params={"communityId": community_id},
                body={
                    "name": name,
                    "participantUserIds": list(
                        participants if participants is not None else (HOST,) + MEMBERS
                    ),
                },
            ),
        )["body"]
    )["data"]


def _get(draft_id, user_id=HOST):
    return json.loads(
        drafts.get_draft(user_id, api_event(path_params={"draftId": draft_id}))["body"]
    )["data"]


def _pick(draft_id, user_id, player_id):
    return picks.submit_pick(
        user_id,
        api_event(path_params={"draftId": draft_id}, body={"playerId": player_id}),
    )


def _reveal(draft_id, user_id=HOST):
    return json.loads(
        progress.reveal(user_id, api_event(path_params={"draftId": draft_id}))["body"]
    )["data"]


def _lottery(draft_id, user_id=HOST):
    return json.loads(
        progress.run_lottery(user_id, api_event(path_params={"draftId": draft_id}))["body"]
    )["data"]


def _advance(draft_id, user_id=HOST):
    return json.loads(
        progress.advance(user_id, api_event(path_params={"draftId": draft_id}))["body"]
    )["data"]


def _start(draft_id, user_id=HOST):
    return json.loads(
        drafts.start_draft(user_id, api_event(path_params={"draftId": draft_id}))["body"]
    )["data"]


@pytest.fixture
def ready(main_table, draft_table):
    setup_community(main_table, draft_table, host=HOST, members=MEMBERS)
    return main_table, draft_table


# --- 作成 -------------------------------------------------------------------


def test_作成するとSETUPで参加者と選手スナップショットが作られる(ready):
    _, draft_table = ready
    data = _create()

    assert data["status"] == repo.STATUS_SETUP
    assert data["participantCount"] == 3
    assert data["femalePlayerCount"] == 13
    # DESIGN.md §4.3の表: 参加者3人なら余剰枠は10。
    assert data["femaleSurplusRemaining"] == 10

    # DESIGN.md §6.2「選手マスタのスナップショット」: 作成時点の40人を
    # ドラフト配下に固定する。以降のルール判定はこのコピーだけを見る。
    assert len(repo.list_players(data["draftId"])) == 40
    assert len(repo.list_participants(data["draftId"])) == 3


def test_選手マスタが未シードなら作成できない(main_table, draft_table):
    setup_community(main_table, draft_table, host=HOST, members=MEMBERS, players=[])
    with pytest.raises(DraftError) as exc:
        _create()
    assert exc.value.code == "ML_PLAYERS_NOT_SEEDED"


def test_一般メンバーはドラフトを作成できない(ready):
    # DESIGN.md §4.13: 作成は他の管理操作と揃えてOWNER/ADMINのみ。
    from meetflow_common import AuthError

    with pytest.raises(AuthError):
        _create("u1")


def test_コミュニティ外のユーザーは参加者にできない(ready):
    with pytest.raises(DraftError) as exc:
        _create(participants=[HOST, "u1", "stranger"])
    assert exc.value.code == "DRAFT_VALIDATION_ERROR"


def test_参加者が下限未満なら作成できない(ready):
    with pytest.raises(DraftError) as exc:
        _create(participants=[HOST, "u1"])
    assert exc.value.code == "DRAFT_VALIDATION_ERROR"


def test_女性選手数が参加人数の上限を抑える(main_table, draft_table):
    # DESIGN.md §4.5: 上限は min(10, 女性選手数)。女性2人なら3人は入れない。
    setup_community(
        main_table,
        draft_table,
        host=HOST,
        members=MEMBERS,
        players=make_players(total=40, female=2),
    )
    with pytest.raises(DraftError) as exc:
        _create()
    assert exc.value.code == "DRAFT_VALIDATION_ERROR"


def test_選手一覧は確保済みの選手に指名者を付けて返す(ready):
    draft_id = _create()["draftId"]
    _start(draft_id)
    _submit_all(draft_id, {HOST: "p20", "u1": "p21", "u2": "p22"})
    _reveal(draft_id)

    players = json.loads(
        drafts.get_players(HOST, api_event(path_params={"draftId": draft_id}))["body"]
    )["data"]["players"]
    assert len(players) == 40
    taken = {p["playerId"]: p["takenByUserId"] for p in players if p["takenByUserId"]}
    assert taken == {"p20": HOST, "p21": "u1", "p22": "u2"}
    assert sum(1 for p in players if p["isFemale"]) == 13


# --- 指名 -------------------------------------------------------------------


def test_開始前は指名できない(ready):
    draft_id = _create()["draftId"]
    with pytest.raises(DraftError) as exc:
        _pick(draft_id, HOST, "p20")
    assert exc.value.code == "DRAFT_INVALID_STATUS"


def test_開始すると1巡目1waveのNOMINATINGになる(ready):
    draft_id = _create()["draftId"]
    data = _start(draft_id)
    assert (data["status"], data["round"], data["wave"]) == (
        repo.STATUS_NOMINATING,
        1,
        1,
    )


def test_開示前は他人の指名が見えず提出状況だけ分かる(ready):
    # DESIGN.md §4.6: 主催者画面にも「何人提出完了」しか出さない。
    draft_id = _create()["draftId"]
    _start(draft_id)
    _pick(draft_id, HOST, "p20")

    view = _get(draft_id, HOST)["currentWave"]
    assert view["submittedUserIds"] == [HOST]
    assert view["pendingUserIds"] == ["u1", "u2"]
    assert view["revealed"] is False
    assert "picks" not in view
    # 自分の指名だけは押し間違い確認のために返す。
    assert view["myPick"]["playerId"] == "p20"
    assert _get(draft_id, "u1")["currentWave"]["myPick"] is None


def test_同じwaveで二度提出できない(ready):
    draft_id = _create()["draftId"]
    _start(draft_id)
    _pick(draft_id, HOST, "p20")
    with pytest.raises(DraftError) as exc:
        _pick(draft_id, HOST, "p21")
    assert exc.value.code == "PICK_ALREADY_SUBMITTED"


def test_参加者でなければ指名できない(ready, main_table):
    put_membership(main_table, "c1", "watcher")
    put_profile(main_table, "watcher")
    draft_id = _create()["draftId"]
    _start(draft_id)
    with pytest.raises(DraftError) as exc:
        _pick(draft_id, "watcher", "p20")
    assert exc.value.code == "NOT_DRAFT_PARTICIPANT"


def test_主催者は代理指名できる(ready):
    # DESIGN.md §4.7: 制限時間は設けず、連絡がつかない人の分だけ代理指名。
    draft_id = _create()["draftId"]
    _start(draft_id)
    picks.submit_proxy_pick(
        HOST,
        api_event(
            path_params={"draftId": draft_id}, body={"userId": "u1", "playerId": "p20"}
        ),
    )
    assert _get(draft_id)["currentWave"]["submittedUserIds"] == ["u1"]


def test_主催者以外は代理指名できない(ready):
    draft_id = _create()["draftId"]
    _start(draft_id)
    with pytest.raises(DraftError) as exc:
        picks.submit_proxy_pick(
            "u1",
            api_event(
                path_params={"draftId": draft_id},
                body={"userId": "u2", "playerId": "p20"},
            ),
        )
    assert exc.value.code == "NOT_DRAFT_HOST"


# --- 開示・抽選・進行 -------------------------------------------------------


def test_全員提出前は開示できない(ready):
    draft_id = _create()["draftId"]
    _start(draft_id)
    _pick(draft_id, HOST, "p20")
    with pytest.raises(DraftError) as exc:
        _reveal(draft_id)
    assert exc.value.code == "PICKS_NOT_COMPLETE"


def test_重複がなければ開示だけで確定する(ready):
    draft_id = _create()["draftId"]
    _start(draft_id)
    _submit_all(draft_id, {HOST: "p20", "u1": "p21", "u2": "p22"})

    revealed = _reveal(draft_id)
    assert revealed["lotteryRequired"] is False
    assert len(revealed["picks"]) == 3

    rosters = _get(draft_id)["rosters"]
    assert {u: [r["playerId"] for r in rs] for u, rs in rosters.items()} == {
        HOST: ["p20"],
        "u1": ["p21"],
        "u2": ["p22"],
    }
    # 確定した選手は他の人が指名できなくなる。
    assert {lock["playerId"] for lock in repo.list_locks(draft_id)} == {
        "p20",
        "p21",
        "p22",
    }


def test_確定済みの選手は指名できない(ready):
    draft_id = _create()["draftId"]
    _start(draft_id)
    _submit_all(draft_id, {HOST: "p20", "u1": "p21", "u2": "p22"})
    _reveal(draft_id)
    _advance(draft_id)

    with pytest.raises(DraftError) as exc:
        _pick(draft_id, "u1", "p20")
    assert exc.value.code == "PLAYER_ALREADY_TAKEN"


def test_重複があると抽選待ちになり落選者だけが再指名する(ready):
    draft_id = _create()["draftId"]
    _start(draft_id)
    _submit_all(draft_id, {HOST: "p20", "u1": "p20", "u2": "p22"})

    revealed = _reveal(draft_id)
    assert revealed["lotteryRequired"] is True

    result = _lottery(draft_id)
    assert len(result["lotteries"]) == 1
    assert result["lotteries"][0]["type"] == "PLAYER"
    assert sorted(result["lotteries"][0]["candidates"]) == [HOST, "u1"]
    winner = result["lotteries"][0]["winnerUserId"]
    loser = "u1" if winner == HOST else HOST
    assert result["loserUserIds"] == [loser]

    # 抽選の記録は残す（DESIGN.md §4.14: 検証は操作ログのみ）。
    logged = json.loads(
        drafts.get_lotteries(HOST, api_event(path_params={"draftId": draft_id}))["body"]
    )["data"]["lotteries"]
    assert len(logged) == 1
    assert logged[0]["winnerUserId"] == winner

    # 同じ巡のまま次のwaveへ進み、落選者だけが再指名の対象になる。
    state = _advance(draft_id)
    assert (state["round"], state["wave"]) == (1, 2)
    assert _get(draft_id)["currentWave"]["expectedUserIds"] == [loser]


def test_4巡終わるとCOMPLETEDになる(ready):
    draft_id = _create()["draftId"]
    _start(draft_id)
    plan = [
        {HOST: "p20", "u1": "p21", "u2": "p22"},
        {HOST: "p23", "u1": "p24", "u2": "p25"},
        {HOST: "p26", "u1": "p27", "u2": "p28"},
        # 4巡目: 誰も女性を持っていないので全員が女性強制（§4.3(a)）。
        {HOST: "p01", "u1": "p02", "u2": "p03"},
    ]
    for round_no, assignments in enumerate(plan, start=1):
        state = _get(draft_id)
        assert state["round"] == round_no
        _submit_all(draft_id, assignments)
        _reveal(draft_id)
        state = _advance(draft_id)

    assert state["status"] == repo.STATUS_COMPLETED
    rosters = _get(draft_id)["rosters"]
    assert all(len(team) == 4 for team in rosters.values())
    # 全員が女性を1人以上持っている（Mリーグのレギュレーションに倣う: §1）。
    assert all(any(p["isFemale"] for p in team) for team in rosters.values())


def test_最終巡で女性を持たない人は女性しか指名できない(ready):
    draft_id = _create()["draftId"]
    _start(draft_id)
    for assignments in [
        {HOST: "p20", "u1": "p21", "u2": "p22"},
        {HOST: "p23", "u1": "p24", "u2": "p25"},
        {HOST: "p26", "u1": "p27", "u2": "p28"},
    ]:
        _submit_all(draft_id, assignments)
        _reveal(draft_id)
        _advance(draft_id)

    with pytest.raises(DraftError) as exc:
        _pick(draft_id, HOST, "p29")
    assert exc.value.code == "FEMALE_REQUIRED"
    # 女性ならそのまま通る。
    _pick(draft_id, HOST, "p01")


def test_余剰枠が尽きると追加の女流指名が弾かれる(main_table, draft_table):
    # 参加者3人・女性3人 → 余剰枠0。1人目の女性は通るが、2人目は弾かれる。
    setup_community(
        main_table,
        draft_table,
        host=HOST,
        members=MEMBERS,
        players=make_players(total=40, female=3),
    )
    draft_id = _create()["draftId"]
    _start(draft_id)
    _submit_all(draft_id, {HOST: "p01", "u1": "p20", "u2": "p21"})
    _reveal(draft_id)
    _advance(draft_id)

    with pytest.raises(DraftError) as exc:
        _pick(draft_id, HOST, "p02")
    assert exc.value.code == "FEMALE_SURPLUS_EXHAUSTED"
    # 女性をまだ持っていない u1 は同じ選手を指名できる（必要指名は余剰枠外）。
    _pick(draft_id, "u1", "p02")


def test_主催者以外は進行操作ができない(ready):
    # DESIGN.md §4.6: 開示も抽選も主催者ボタンで進める。
    draft_id = _create()["draftId"]
    _start(draft_id)
    _submit_all(draft_id, {HOST: "p20", "u1": "p21", "u2": "p22"})
    for action in (progress.reveal, progress.advance):
        with pytest.raises(DraftError) as exc:
            action("u1", api_event(path_params={"draftId": draft_id}))
        assert exc.value.code == "NOT_DRAFT_HOST"


def test_状態を変える操作のたびにversionが増える(ready):
    # DESIGN.md §4.12: ポーリング側は version が変わったときだけ再描画する。
    draft_id = _create()["draftId"]
    versions = [_get(draft_id)["version"]]
    _start(draft_id)
    versions.append(_get(draft_id)["version"])
    _submit_all(draft_id, {HOST: "p20", "u1": "p21", "u2": "p22"})
    _reveal(draft_id)
    versions.append(_get(draft_id)["version"])
    _advance(draft_id)
    versions.append(_get(draft_id)["version"])
    assert versions == sorted(set(versions))
