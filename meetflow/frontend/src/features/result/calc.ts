import type { CalcMode, GameSessionDetail } from "@/features/result/types";
import type { GameType } from "@/features/user/types";

export type LiveResultRow = {
  userId: string;
  nickname: string;
  score: number;
  rank: number;
  rankPoints: number;
};

/**
 * バックエンド（result_lambda/handlers/results.py の _compute_results()）と
 * 同じ計算式によるフロント側プレビュー実装。最終的な正の値はサーバー側の
 * 計算結果であり、ここでの計算はリアルタイム表示（プレビュー）専用。
 */
export function computeLiveResults(
  rows: { userId: string; nickname: string; score: number }[],
  calcMode: CalcMode,
  startingPoints: number,
  returnPoints: number,
  umaByRank: number[],
): LiveResultRow[] {
  const ordered = [...rows].sort((a, b) => b.score - a.score);
  const playerCount = rows.length;

  return ordered.map((row, index) => {
    const rank = index + 1;
    let rankPoints = 0;
    if (calcMode === "AUTO") {
      const base = (row.score - returnPoints) / 1000;
      const oka = rank === 1 ? ((returnPoints - startingPoints) * playerCount) / 1000 : 0;
      const uma = umaByRank[rank - 1] ?? 0;
      rankPoints = Math.round((base + uma + oka) * 10) / 10;
    }
    return { ...row, rank, rankPoints };
  });
}

/** AUTO時の点数合計チェック（非ブロッキングの警告表示専用）。 */
export function hasScoreMismatch(
  rows: { score: number }[],
  startingPoints: number,
): boolean {
  const total = rows.reduce((sum, r) => sum + r.score, 0);
  return total !== startingPoints * rows.length;
}

/** ゲーム種別ごとの本来の対局人数（四麻=4人・三麻=3人）。 */
export function expectedPlayerCount(gameType: GameType): number {
  return gameType === "MAHJONG3" ? 3 : 4;
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
 * 既に取得済みのセッション一覧からフロントで都度計算する）。
 */
export function aggregateSessionTotals(
  sessions: GameSessionDetail[],
  nicknameByUserId: Map<string, string>,
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
