import type { GameDefaults, GameDefaultsEntry } from "@/features/community/types";
import type {
  CalcMode,
  ChipRecord,
  GameSessionDetail,
  LastGameSettings,
  TobiAssignment,
} from "@/features/result/types";
import type { GameType } from "@/features/user/types";

export type LiveResultRow = {
  userId: string;
  nickname: string;
  score: number;
  rank: number;
  rankPoints: number;
};

/** 自動計算の箱下精算・飛び賞設定（Issue #66/#67）。省略時は従来通りの挙動になる。 */
export type SettlementOptions = {
  /**
   * false（箱下精算なし）の場合、基礎点の計算にはマイナスの持ち点を0点に切り捨てて使い、
   * 切り捨てたマイナス分の合計は1位の持ち点から差し引く（Issue #114）。
   * 着順・ウマは差し引く前の生の点数で決める。省略時true。
   */
  boxUnderSettlement?: boolean;
  /** 飛び賞1件あたりのポイント数。省略時0（実質無効）。 */
  tobiPoints?: number;
  /** 誰が誰をトビにしたか（省略時なし）。トビ判定自体は常に生の点数（マイナスのまま）で行う。 */
  tobiAssignments?: TobiAssignment[];
};

/**
 * バックエンド（result_lambda/handlers/results.py の _compute_results()）と
 * 同じ計算式によるフロント側プレビュー実装。最終的な正の値はサーバー側の
 * 計算結果であり、ここでの計算はリアルタイム表示（プレビュー）専用。
 *
 * 点数が同点の場合、`tieOrder`（userIdの優先順リスト）内での並び順を
 * 同点者間のタイブレークに使う。バックエンドの`_compute_results`も安定ソートで
 * 送信順を維持するため、`sortByTieOrder`で送信直前に同じ順序を`results`に
 * 反映することで、ここで決めた同点順位がそのまま登録される。
 */
export function computeLiveResults(
  rows: { userId: string; nickname: string; score: number }[],
  calcMode: CalcMode,
  startingPoints: number,
  returnPoints: number,
  umaByRank: number[],
  tieOrder?: string[],
  settlement?: SettlementOptions,
): LiveResultRow[] {
  const orderIndex = new Map((tieOrder ?? []).map((userId, i) => [userId, i]));
  const ordered = [...rows].sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    const ai = orderIndex.get(a.userId) ?? Number.MAX_SAFE_INTEGER;
    const bi = orderIndex.get(b.userId) ?? Number.MAX_SAFE_INTEGER;
    return ai - bi;
  });
  const playerCount = rows.length;
  const boxUnderSettlement = settlement?.boxUnderSettlement ?? true;
  const tobiPoints = settlement?.tobiPoints ?? 0;
  const tobiAssignments = settlement?.tobiAssignments ?? [];
  // 箱下精算なしで1位が負担するマイナス分の合計（着順は上でscoreから確定済み）
  const boxUnderTotal = boxUnderSettlement
    ? 0
    : rows.reduce((sum, r) => sum + Math.min(r.score, 0), 0);

  return ordered.map((row, index) => {
    const rank = index + 1;
    let rankPoints = 0;
    if (calcMode === "AUTO") {
      const settledScore = boxUnderSettlement
        ? row.score
        : rank === 1
          ? row.score + boxUnderTotal
          : Math.max(row.score, 0);
      const base = (settledScore - returnPoints) / 1000;
      const oka = rank === 1 ? ((returnPoints - startingPoints) * playerCount) / 1000 : 0;
      const uma = umaByRank[rank - 1] ?? 0;
      const tobiDelta = tobiAssignments.reduce((sum, a) => {
        if (a.receiverUserId === row.userId) return sum + tobiPoints;
        if (a.bustedUserId === row.userId) return sum - tobiPoints;
        return sum;
      }, 0);
      rankPoints = Math.round((base + uma + oka + tobiDelta) * 10) / 10;
    }
    return { ...row, rank, rankPoints };
  });
}

/**
 * 同点タイブレークの並び替え結果（`tieOrder`）を、実際に送信する行配列に反映する。
 * 点数降順は変えず、同点者同士だけを`tieOrder`内の順序に並び替える。
 */
export function sortByTieOrder<T extends { userId: string; score: number }>(
  items: T[],
  tieOrder: string[],
): T[] {
  const orderIndex = new Map(tieOrder.map((userId, i) => [userId, i]));
  return [...items].sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    const ai = orderIndex.get(a.userId) ?? Number.MAX_SAFE_INTEGER;
    const bi = orderIndex.get(b.userId) ?? Number.MAX_SAFE_INTEGER;
    return ai - bi;
  });
}

/**
 * AUTO時の点数合計チェック。点数合計と「配給原点×人数」の差分を返す
 * （0なら一致。正の値は超過、負の値は不足）。
 */
export function scoreMismatchDiff(rows: { score: number }[], startingPoints: number): number {
  const total = rows.reduce((sum, r) => sum + r.score, 0);
  return total - startingPoints * rows.length;
}

/** 点数合計の不一致を人が読める文言にする（例：「20点多い」「30点足りない」）。 */
export function formatScoreMismatch(diff: number): string {
  return diff > 0 ? `${diff}点多い` : `${Math.abs(diff)}点足りない`;
}

/** チップ合計の±0からのずれを人が読める文言にする（例：「+3枚」「-2枚」、Issue #116）。 */
export function formatChipMismatch(total: number): string {
  return total > 0 ? `+${total}枚` : `${total}枚`;
}

/** ゲーム種別ごとの本来の対局人数（四麻=4人・三麻=3人）。 */
export function expectedPlayerCount(gameType: GameType): number {
  return gameType === "MAHJONG3" ? 3 : 4;
}

/** ゲーム種別ごとのシステム既定の配給原点/返し点（Issue #64：三麻は四麻と異なる）。 */
export const DEFAULT_POINTS_BY_GAME_TYPE: Record<
  GameType,
  { startingPoints: number; returnPoints: number }
> = {
  MAHJONG4: { startingPoints: 25000, returnPoints: 30000 },
  MAHJONG3: { startingPoints: 35000, returnPoints: 40000 },
};

/**
 * 成績入力（自動計算）の配給原点・返し点・ウマの初期値。コミュニティの
 * デフォルト設定（Issue #115）があればそれを、無ければシステム既定値
 * （ウマはすべて0）を返す。
 */
export function resolveGameDefaults(
  gameType: GameType,
  gameDefaults: GameDefaults | null | undefined,
): GameDefaultsEntry {
  const configured = gameDefaults?.[gameType];
  if (configured) return configured;
  return {
    ...DEFAULT_POINTS_BY_GAME_TYPE[gameType],
    umaByRank: Array.from({ length: expectedPlayerCount(gameType) }, () => 0),
  };
}

/**
 * 前回設定（Issue #109）の配給原点・返し点・ウマを初期値に使うかどうか（Issue #115）。
 * 同一イベント内の直前の半荘の設定は常に優先する。入力者本人の過去の設定は、
 * その種目のコミュニティのデフォルト設定が無い場合にのみ使う。
 */
export function shouldUseLastSettings(
  lastSettings: Extract<LastGameSettings, { found: true }>,
  gameDefaults: GameDefaults | null | undefined,
): boolean {
  // sourceを返さない旧バックエンドでは、従来通り前回設定を優先する
  if (lastSettings.source !== "USER") return true;
  return !gameDefaults?.[lastSettings.gameType];
}

export type SessionTotalRow = {
  userId: string;
  nickname: string;
  games: number;
  totalRankPoints: number;
  totalChips: number;
  averageRank: number;
};

/**
 * 1イベント内の複数半荘（GameSessionDetail[]）をユーザー単位で合算する。
 * イベント詳細画面での「当日の累計成績」表示用（サーバー側の集計APIではなく
 * 既に取得済みのセッション一覧からフロントで都度計算する）。チップは、
 * 半荘ごとのチップ（Issue #116より前の記録）とチップ記録（`chipRecords`）を合算する。
 */
export function aggregateSessionTotals(
  sessions: GameSessionDetail[],
  nicknameByUserId: Map<string, string>,
  chipRecords: ChipRecord[] = [],
): SessionTotalRow[] {
  const byUser = new Map<
    string,
    { games: number; totalRankPoints: number; totalChips: number; rankSum: number }
  >();

  for (const session of sessions) {
    for (const r of session.results) {
      const entry = byUser.get(r.userId) ?? {
        games: 0,
        totalRankPoints: 0,
        totalChips: 0,
        rankSum: 0,
      };
      entry.games += 1;
      entry.totalRankPoints += r.rankPoints;
      entry.rankSum += r.rank;
      byUser.set(r.userId, entry);
    }
    for (const c of session.chips) {
      const entry = byUser.get(c.userId) ?? {
        games: 0,
        totalRankPoints: 0,
        totalChips: 0,
        rankSum: 0,
      };
      entry.totalChips += c.chipCount;
      byUser.set(c.userId, entry);
    }
  }
  for (const c of chipRecords.flatMap((r) => r.chips)) {
    const entry = byUser.get(c.userId) ?? {
      games: 0,
      totalRankPoints: 0,
      totalChips: 0,
      rankSum: 0,
    };
    entry.totalChips += c.chipCount;
    byUser.set(c.userId, entry);
  }

  return Array.from(byUser.entries())
    .map(([userId, v]) => ({
      userId,
      nickname: nicknameByUserId.get(userId) ?? userId,
      games: v.games,
      totalRankPoints: Math.round(v.totalRankPoints * 10) / 10,
      totalChips: v.totalChips,
      averageRank: v.games > 0 ? Math.round((v.rankSum / v.games) * 100) / 100 : 0,
    }))
    .sort((a, b) => b.totalRankPoints - a.totalRankPoints);
}
