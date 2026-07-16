import type { CalcMode } from "@/features/result/types";

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
