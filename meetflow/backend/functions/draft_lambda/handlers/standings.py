"""成績追跡（docs/draft/DESIGN.md §4.8〜§4.10、§4.15）。

Mリーグ公式サイトから今季の結果を取り込み、各参加者のチーム（4人）の
獲得ポイント合計を出す。

取得は**完全オンデマンド**（§4.8）。EventBridge Schedulerも定期実行Lambdaも
作らない。誰かが「更新」を押したときだけ取りに行き、1日1回までに制限する。
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from botocore.exceptions import ClientError

from meetflow_common import now_iso_ms, parse_body, success_response

from . import mleague
from . import repository as repo
from .drafts import _load_draft_for_member, _require_host
from errors import DraftError

# 同時押しロックの有効期限（秒）。DESIGN.md §6.2「2人が同時に成績更新ボタンを
# 押したときの二重取得防止」。取得が落ちてロックが残っても、この時間を過ぎれば
# 次の人が取り直せる。
LOCK_TIMEOUT_SECONDS = 120


def get_standings(user_id: str, event: dict) -> dict:
    """GET /drafts/{draftId}/standings — 参加者ごとの獲得ポイント合計。

    集計範囲は §4.15 の通りレギュラーシーズン終了日まで。未設定なら
    シーズン全体を集計する（4月より前は差が出ないため実害が無い）。
    """
    draft, _ = _load_draft_for_member(user_id, event)
    season = draft["season"]
    cutoff = draft.get("regularSeasonEndDate")
    until = _to_yyyymmdd(cutoff)

    gamedays = repo.list_gamedays(season)
    totals, played_counts = _accumulate(gamedays, until=until)
    state = repo.get_fetch_state(season) or {}

    rosters = repo.list_rosters(draft["draftId"])
    by_user: dict[str, list] = {}
    for entry in rosters:
        by_user.setdefault(entry["userId"], []).append(entry)

    standings = []
    for participant in repo.list_participants(draft["draftId"]):
        players = []
        for entry in sorted(by_user.get(participant["userId"], []), key=lambda e: int(e["round"])):
            name = mleague.normalize_name(entry["playerName"])
            players.append(
                {
                    "playerId": entry["playerId"],
                    "playerName": entry["playerName"],
                    "teamName": entry["teamName"],
                    "isFemale": bool(entry["isFemale"]),
                    "points": totals.get(name, 0.0),
                    "games": played_counts.get(name, 0),
                }
            )
        standings.append(
            {
                "userId": participant["userId"],
                "displayName": participant["displayName"],
                "totalPoints": round(sum(p["points"] for p in players), 1),
                "players": players,
            }
        )
    standings.sort(key=lambda s: -s["totalPoints"])
    for index, row in enumerate(standings, start=1):
        row["rank"] = index

    played = [g for g in gamedays if g.get("state") == repo.GAMEDAY_PLAYED]
    scheduled = [g for g in gamedays if g.get("state") == repo.GAMEDAY_SCHEDULED]
    return success_response(
        {
            "season": season,
            "regularSeasonEndDate": cutoff,
            "standings": standings,
            # §7: 取得に失敗していても古いデータを出し続ける。そのかわり
            # 「いつ時点のデータか」は必ず出す。
            "lastUpdatedAt": state.get("lastSuccessAt"),
            "lastError": state.get("lastError"),
            "lastErrorAt": state.get("lastErrorAt"),
            # 日別積算と公式の累計が食い違った選手（SCRAPING.md §3の検算）。
            # ポストシーズンが始まると当然ズレるため、警告としてだけ出す。
            "mismatchedPlayers": list(state.get("mismatchedPlayers") or []),
            # 結果側にいてマスタに無い名前。表記ゆれの検知用。
            "unmatchedPlayerNames": _unmatched_names(totals, standings),
            "playedGamedayCount": len(played),
            "scheduledGamedayCount": len(scheduled),
            "latestPlayedDate": _format_date(state.get("latestPlayedDate")),
            # §4.9: 19時は最新確定日の計算を変えない。「対局中」バッジの
            # 表示判定にだけ使う。
            "inGameWindow": mleague.is_in_game_window(),
            "latestConfirmedDate": _format_date(mleague.latest_confirmed_date()),
            "canRefresh": _can_refresh(state),
        }
    )


def refresh_standings(user_id: str, event: dict) -> dict:
    """POST /drafts/{draftId}/standings/refresh — 公式サイトから取り込む。

    DESIGN.md §4.8: 完全オンデマンド・1日1回まで。**失敗時はカウントを
    消費しない**ため、パースがこけた日でも直ればその日のうちに取り直せる。
    """
    draft, _ = _load_draft_for_member(user_id, event)
    season = draft["season"]
    state = dict(repo.get_fetch_state(season) or {})

    if not _can_refresh(state):
        # 取得済みなら何もしない。エラーにはしない（ボタンを押した人に
        # 「今日はもう最新です」と返すだけ）。
        return success_response({"refreshed": False, "reason": "ALREADY_FETCHED_TODAY"})

    _acquire_lock(season, state)
    try:
        data = mleague.fetch_season_results(season)
    except mleague.ScrapeError as exc:
        # §7: パース失敗は前提として設計する。古いデータはそのまま残し、
        # 失敗した事実だけ記録して画面に出す。1日1回のカウントは消費しない。
        state.update({"lastError": str(exc), "lastErrorAt": now_iso_ms()})
        # ロックは属性ごと消す。Noneのまま残すと、次にacquireしたときに
        # attribute_not_existsも大小比較も成立せず、永久にロックされてしまう。
        state.pop("lockedAt", None)
        repo.put_fetch_state(season, state)
        raise DraftError("MLEAGUE_FETCH_FAILED", "Mリーグ公式サイトから成績を取得できませんでした")

    written = _store_results(season, data)
    accumulated = mleague.accumulate(data["results"])
    mismatched = mleague.verify(accumulated, data["officialTotals"])
    latest_played = max(
        (day["date"] for day in data["schedule"] if day["finished"]), default=None
    )

    state.update(
        {
            "lastSuccessAt": now_iso_ms(),
            # 1日1回の判定キー（JSTの日付）。失敗時は更新しないので、
            # パースがこけた日でも直ればその日のうちに取り直せる（§4.8）。
            "lastFetchDate": _today_jst(),
            "lastError": None,
            "lastErrorAt": None,
            "mismatchedPlayers": mismatched,
            "latestPlayedDate": latest_played,
        }
    )
    state.pop("lockedAt", None)
    repo.put_fetch_state(season, state)

    return success_response(
        {
            "refreshed": True,
            "gamedayCount": written,
            "latestPlayedDate": _format_date(latest_played),
            "mismatchedPlayers": mismatched,
        }
    )


def submit_manual_result(user_id: str, event: dict) -> dict:
    """POST /drafts/{draftId}/standings/manual — 手動入力のフォールバック。

    DESIGN.md §7: 「手動入力のフォールバック画面を最初から作る。これがあれば
    最悪シーズンは回る」。公式サイトのHTMLが変わってパースが直らない間も、
    主催者が結果を打ち込めば集計は続けられる。

    次回の取得が成功すると公式の値で上書きされる（公式が正）。
    """
    draft, _ = _load_draft_for_member(user_id, event)
    _require_host(draft, user_id)

    body = parse_body(event)
    date = str(body.get("date") or "").replace("-", "")
    if len(date) != 8 or not date.isdigit():
        raise DraftError("DRAFT_VALIDATION_ERROR", "対局日はYYYY-MM-DD形式で指定してください")
    try:
        no = int(body.get("no") or 0)
    except (TypeError, ValueError):
        raise DraftError("DRAFT_VALIDATION_ERROR", "節番号は数値で指定してください") from None

    games = _validate_manual_games(body.get("games"))
    repo.get_draft_table().put_item(
        Item={
            "PK": repo.season_pk(draft["season"]),
            "SK": repo.gameday_sk(date, no),
            "season": draft["season"],
            "date": date,
            "no": no,
            "state": repo.GAMEDAY_PLAYED,
            "source": repo.SOURCE_MANUAL,
            "games": games,
            "enteredBy": user_id,
            "fetchedAt": now_iso_ms(),
        }
    )
    return success_response({"date": date, "no": no, "gameCount": len(games)})


# --- 内部ヘルパー -----------------------------------------------------------


def _validate_manual_games(raw) -> list:
    if not isinstance(raw, list) or not raw:
        raise DraftError("DRAFT_VALIDATION_ERROR", "半荘の結果を1つ以上入力してください")
    games = []
    for game in raw:
        rows = game.get("rows") if isinstance(game, dict) else None
        if not isinstance(rows, list) or not rows:
            raise DraftError("DRAFT_VALIDATION_ERROR", "各半荘に着順を入力してください")
        parsed_rows = []
        for row in rows:
            name = mleague.normalize_name(str(row.get("name") or ""))
            if not name:
                raise DraftError("DRAFT_VALIDATION_ERROR", "選手名を入力してください")
            try:
                point = Decimal(str(row["point"]))
            except (KeyError, TypeError, ValueError):
                raise DraftError(
                    "DRAFT_VALIDATION_ERROR", f"{name}のポイントが数値ではありません"
                ) from None
            parsed_rows.append(
                {"rank": int(row.get("rank") or 0), "name": name, "point": point}
            )
        games.append({"label": str(game.get("label") or ""), "rows": parsed_rows})
    return games


def _store_results(season: str, data: dict) -> int:
    """取得した日程と結果をDraftTableへ書き込む。

    SCRAPING.md §6の通り毎回まるごと取れるので、差分管理はせず上書きする。
    日別レコードを残す意味は「今日の獲得ポイント」の差分表示と、公式ページが
    壊れたときの履歴保全（§4.10）。
    """
    table = repo.get_draft_table()
    written = 0
    with table.batch_writer() as batch:
        for day in data["schedule"]:
            key = f'{day["date"]}-{day["no"]}'
            games = data["results"].get(key)
            item = {
                "PK": repo.season_pk(season),
                "SK": repo.gameday_sk(day["date"], day["no"]),
                "season": season,
                "date": day["date"],
                "no": day["no"] or 0,
                "teams": day["teams"],
                "fetchedAt": now_iso_ms(),
            }
            if day["finished"] and games:
                item["state"] = repo.GAMEDAY_PLAYED
                item["source"] = repo.SOURCE_OFFICIAL
                item["games"] = [
                    {
                        "label": game["label"],
                        "rows": [
                            {
                                "rank": row["rank"],
                                "name": row["name"],
                                # DynamoDBはfloatを受け付けないのでDecimal化する。
                                "point": Decimal(str(row["point"])),
                            }
                            for row in game["rows"]
                        ],
                    }
                    for game in games
                ]
            else:
                item["state"] = repo.GAMEDAY_SCHEDULED
            batch.put_item(Item=item)
            written += 1
    return written


def _accumulate(gamedays: list, *, until: str = None):
    """保存済みの節から選手別の合計ポイントと出場半荘数を出す。"""
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for day in gamedays:
        if day.get("state") != repo.GAMEDAY_PLAYED:
            continue
        # §4.15: レギュラーシーズン終了日を超える節は集計しない。
        if until and str(day["date"]) > until:
            continue
        for game in day.get("games") or []:
            for row in game.get("rows") or []:
                name = row["name"]
                totals[name] = round(totals.get(name, 0.0) + float(row["point"]), 1)
                counts[name] = counts.get(name, 0) + 1
    return totals, counts


def _unmatched_names(totals: dict, standings: list) -> list:
    """結果側にいて、どの参加者のチームにも紐づかなかった名前。

    全員分の選手が誰にも指名されていないのは普通（40人中、指名されるのは
    参加者数×4人だけ）なので、これ自体は異常ではない。表記ゆれで
    ポイントが0のまま張り付く事故に気づくための材料として返す。
    """
    known = {
        mleague.normalize_name(player["playerName"])
        for row in standings
        for player in row["players"]
    }
    return sorted(name for name in totals if name not in known)


def _can_refresh(state: dict) -> bool:
    """今日まだ取得していないか（DESIGN.md §4.8「取得は1日1回まで」）。

    見るのは成功した日だけ。失敗はカウントを消費しないのでリトライできる。
    """
    return state.get("lastFetchDate") != _today_jst()


def _acquire_lock(season: str, state: dict) -> None:
    """同時押しの二重取得を防ぐ（DESIGN.md §6.2）。

    条件付き書き込みで「ロックが無い、または期限切れ」のときだけ取れる。
    """
    now = datetime.now(timezone.utc)
    locked_at = state.get("lockedAt")
    if locked_at:
        try:
            elapsed = (now - datetime.fromisoformat(str(locked_at))).total_seconds()
        except ValueError:
            elapsed = LOCK_TIMEOUT_SECONDS + 1
        if elapsed < LOCK_TIMEOUT_SECONDS:
            raise DraftError("REFRESH_IN_PROGRESS", "成績の更新中です。少し待ってから再度お試しください")

    token = now.isoformat()
    try:
        repo.get_draft_table().update_item(
            Key={"PK": repo.season_pk(season), "SK": "FETCH_STATE"},
            UpdateExpression="SET lockedAt = :now, season = :season",
            ConditionExpression=(
                "attribute_not_exists(lockedAt) OR lockedAt = :previous OR lockedAt < :stale"
            ),
            ExpressionAttributeValues={
                ":now": token,
                ":season": season,
                ":previous": locked_at if locked_at else "",
                ":stale": (now - timedelta(seconds=LOCK_TIMEOUT_SECONDS)).isoformat(),
            },
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise DraftError(
                "REFRESH_IN_PROGRESS", "成績の更新中です。少し待ってから再度お試しください"
            ) from exc
        raise
    state["lockedAt"] = token


def _today_jst() -> str:
    return datetime.now(timezone.utc).astimezone(mleague.JST).strftime("%Y%m%d")


def _to_yyyymmdd(value) -> str | None:
    """"2027-03-26" → "20270326"。未設定ならNone。"""
    if not value:
        return None
    return str(value).replace("-", "")


def _format_date(value) -> str | None:
    """"20260917" → "2026-09-17"。画面で扱いやすい形に戻す。"""
    if not value:
        return None
    text = str(value)
    if len(text) != 8:
        return text
    return f"{text[:4]}-{text[4:6]}-{text[6:]}"
