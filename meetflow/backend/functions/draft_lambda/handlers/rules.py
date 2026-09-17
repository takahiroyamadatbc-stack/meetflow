"""ドラフトの指名ルール（DESIGN.md §4.3 / §4.4 / §4.4.1）。

DynamoDBにもHTTPにも依存しない純粋な関数だけを置く。ここが企画の肝であり、
「詰みが原理的に発生しない」という不変条件はこのモジュールが担保する。
"""

# DESIGN.md §4.2: 全4巡で4人のチームを編成する。
ROUNDS = 4

# DESIGN.md §4.5: 参加人数の下限・上限。上限は min(10, 女性選手数) で
# さらに絞る（`max_participants`参照）。
MIN_PARTICIPANTS = 3
MAX_PARTICIPANTS = 10


def max_participants(female_player_count: int) -> int:
    """DESIGN.md §4.5: 上限は `min(10, 女性選手数)`。

    女性選手数が参加者数を下回ると、全員が女性を1人確保することが
    そもそも不可能になるため、ここで弾く。
    """
    return min(MAX_PARTICIPANTS, female_player_count)


def initial_female_surplus(female_player_count: int, participant_count: int) -> int:
    """DESIGN.md §4.3(b): 女流余剰枠 B = 女性選手数 − 参加者数。

    全参加者が1人ずつ女性を確保するのに必要な分を差し引いた「余り」。
    追加の女流指名はこの枠を消費する。
    """
    return female_player_count - participant_count


def must_pick_female(round_no: int, has_female: bool, *, rounds: int = ROUNDS) -> bool:
    """DESIGN.md §4.3(a) 動的強制: 「残り巡数 ≦ 自分にまだ必要な女性数」に
    なった参加者は、その巡から女性しか指名できない。

    必要な女性数は0か1しかない（1人以上いればよい）ため、実際に効くのは
    「最終巡に入った時点で女性を1人も持っていない」ケースだけになる。
    """
    rounds_left = rounds - round_no + 1
    females_needed = 0 if has_female else 1
    return rounds_left <= females_needed


def consumes_surplus(has_female: bool, pick_is_female: bool) -> bool:
    """その指名が女流余剰枠を消費するか。

    「女性を既に確保している人が追加で女性を指名する」場合のみ消費する
    （DESIGN.md §4.3(b)）。1人目の女性は必要指名であって余剰ではない。
    """
    return has_female and pick_is_female


def validate_pick(
    *,
    round_no: int,
    has_female: bool,
    pick_is_female: bool,
    female_surplus_remaining: int,
) -> None:
    """指名の受付時バリデーション。違反していれば`DraftError`を送出する。

    余剰枠のチェックは「残り枠が1以上あるか」しか見ない。一斉指名なので
    同じ巡に複数人が追加指名して合計で超過しうるが、それは抽選で解決する
    （DESIGN.md §4.4）。ここで参加者ごとに厳密な取り合いを解こうとすると、
    先に提出した人が有利になってしまう。
    """
    from errors import DraftError

    if must_pick_female(round_no, has_female) and not pick_is_female:
        raise DraftError(
            "FEMALE_REQUIRED",
            "この巡は女性選手を指名してください（最終巡までに女性が1人必要です）",
        )
    if consumes_surplus(has_female, pick_is_female) and female_surplus_remaining <= 0:
        raise DraftError(
            "FEMALE_SURPLUS_EXHAUSTED",
            "女流枠の余りがないため、これ以上女性選手は指名できません",
        )


def resolve_wave(picks, *, female_surplus_remaining: int, draw):
    """1つのwaveの指名を解決する（DESIGN.md §4.4 / §4.4.1）。

    `picks` は `{"userId": ..., "playerId": ..., "isFemale": bool,
    "hasFemale": bool}` のリスト（hasFemaleはこの指名を数える前の状態）。
    `draw(candidates)` は候補リストから当選者を1人選ぶ関数（抽選）。

    戻り値は `(confirmed, losers, lotteries)`:
        confirmed … 獲得が確定した指名のリスト
        losers    … 次のwaveで再指名する userId のリスト
        lotteries … 実施した抽選の記録（LotteryLogに残す）

    解決順は §4.4.1 の通り **①同一選手被り → ②女流余剰枠** で固定する。
    被り抽選に負けた人は誰も獲得していないため、余剰枠を消費させてはいけない。
    """
    lotteries = []
    losers = []

    # ① 同一選手被りの抽選。同じ選手を指名した人同士で1人を当選させる。
    by_player = {}
    for pick in picks:
        by_player.setdefault(pick["playerId"], []).append(pick)

    survivors = []
    for player_id, contenders in by_player.items():
        if len(contenders) == 1:
            survivors.append(contenders[0])
            continue
        winner = draw([c["userId"] for c in contenders])
        lotteries.append(
            {
                "type": "PLAYER",
                "playerId": player_id,
                "candidates": [c["userId"] for c in contenders],
                "winnerUserId": winner,
            }
        )
        for contender in contenders:
            if contender["userId"] == winner:
                survivors.append(contender)
            else:
                losers.append(contender["userId"])

    # ② 女流余剰枠の抽選。①を勝ち抜いた指名のうち、余剰枠を消費するもの
    # だけを数える。合計が残り枠を超えていたら、その人たち同士で抽選する。
    surplus_picks = [
        p for p in survivors if consumes_surplus(p["hasFemale"], p["isFemale"])
    ]
    over = len(surplus_picks) - female_surplus_remaining
    if over > 0:
        remaining = list(surplus_picks)
        # 残り枠の数だけ当選者を決め、あぶれた人を落選させる。
        for _ in range(female_surplus_remaining):
            winner = draw([p["userId"] for p in remaining])
            lotteries.append(
                {
                    "type": "FEMALE_SURPLUS",
                    "playerId": None,
                    "candidates": [p["userId"] for p in remaining],
                    "winnerUserId": winner,
                }
            )
            remaining = [p for p in remaining if p["userId"] != winner]
        dropped = {p["userId"] for p in remaining}
        losers.extend(sorted(dropped))
        survivors = [p for p in survivors if p["userId"] not in dropped]

    return survivors, losers, lotteries
