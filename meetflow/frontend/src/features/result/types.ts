import type { RankingMetric } from "@/features/community/types";
import type { GameType } from "@/features/user/types";

export type CalcMode = "AUTO" | "MANUAL";

/** 点数入力（サーバー側でrankを導出し、AUTO時のみrankPointsを計算する） */
export type ScoreInput = {
  userId: string;
  score: number;
};

export type ChipInput = {
  userId: string;
  chipCount: number;
};

/**
 * 飛び賞（Issue #66）: 誰が誰をトビにしたかは最終スコアだけからは判定できない
 * ため、管理者がUIで明示的に指定した組を持つ。半荘共通のポイント数
 * （`SessionInput.tobiPoints`）を、bustedUserIdから減算しreceiverUserIdへ
 * 加算する。
 */
export type TobiAssignment = {
  bustedUserId: string;
  receiverUserId: string;
};

/** results.py create_session()/update_session() へのリクエストボディ実体 */
export type SessionInput = {
  gameType: GameType;
  calcMode: CalcMode;
  startingPoints?: number;
  returnPoints?: number;
  umaByRank?: number[];
  /** 箱下精算（Issue #67）。省略時はtrue（従来通りマイナス点をそのまま使う）。 */
  boxUnderSettlement?: boolean;
  /** 飛び賞1件あたりのポイント数（Issue #66）。省略時は0（実質的に無効）。 */
  tobiPoints?: number;
  tobiAssignments?: TobiAssignment[];
  results: ScoreInput[];
  chips?: ChipInput[];
};

export type SessionResultRow = {
  userId: string;
  rank: number;
  score: number;
  rankPoints: number;
};

export type ChipResultRow = {
  userId: string;
  chipCount: number;
};

/** results.py _build_session_response() / _group_sessions() のレスポンス実体 */
export type GameSessionDetail = {
  eventId: string;
  sessionNo: string;
  gameType: GameType;
  calcMode: CalcMode;
  playedAt?: string;
  startingPoints?: number;
  returnPoints?: number;
  umaByRank?: number[];
  boxUnderSettlement?: boolean;
  tobiPoints?: number;
  tobiAssignments?: TobiAssignment[];
  results: SessionResultRow[];
  chips: ChipResultRow[];
};

/** results.py get_last_game_settings() のレスポンス実体 */
export type LastGameSettings =
  | { found: false }
  | {
      found: true;
      gameType: GameType;
      calcMode: CalcMode;
      startingPoints?: number;
      returnPoints?: number;
      umaByRank?: number[];
      // tobiAssignmentsは半荘ごとの実データ（誰が誰をトビにしたか）のため、
      // 「次回のデフォルト」として引き継ぐ対象に含めない（boxUnderSettlement/
      // tobiPointsは配給原点等と同じ「house rule」的な設定のため引き継ぐ）。
      boxUnderSettlement?: boolean;
      tobiPoints?: number;
    };

/** results.py get_user_results() の_aggregate()集計値（ゲーム種別ごと） */
export type ResultSummaryStats = {
  totalGames: number;
  averageRank: number;
  firstPlaceRate: number;
  lastPlaceRate: number;
  totalPoints: number;
  totalChips: number;
};

/**
 * results.py get_user_results() のレスポンス実体。四麻と三麻は着順の
 * スケールが異なり平均着順を混ぜると意味を持たなくなるため、種別ごとに
 * 分けて返す（DynamoDB物理設計書v1.13 §3.13）。
 */
export type ResultSummary = {
  userId: string;
  communityId: string;
  byGameType: Record<GameType, ResultSummaryStats>;
};

/** results.py _resolve_ranking_period() が返す期間メタ情報（F-805） */
export type RankingPeriod =
  | { type: "MONTH"; year: number; month: number; startDate: string; endDate: string }
  | { type: "QUARTER"; year: number; quarter: number; startDate: string; endDate: string }
  | { type: "HALF_YEAR"; year: number; half: number; startDate: string; endDate: string }
  | { type: "YEAR"; year: number; startDate: string; endDate: string }
  | { type: "ALL_TIME" };

/**
 * results.py _aggregate_ranking_metrics() の集計値（1メンバー分）。
 * minGames（足切り）はAPIパラメータに含めず、totalGamesを使ってフロント側で
 * 再取得なしにフィルタする（API設計書v1.25 §10.3の設計意図）。
 */
export type RankingMemberStats = {
  userId: string;
  displayName: string;
  totalGames: number;
  averageRank: number;
  firstPlaceRate: number;
  secondPlaceRate: number;
  topTwoRate: number;
  nonLastRate: number;
  totalPoints: number;
  participatedEvents: number;
  totalChips: number;
  averageChips: number;
};

/** results.py get_community_ranking() のレスポンス実体（F-805） */
export type CommunityRanking = {
  communityId: string;
  gameType: GameType;
  period: RankingPeriod;
  members: RankingMemberStats[];
};

/** S-31 ランキング画面のセグメントコントロールで扱う期間指定パラメータ */
export type RankingPeriodParams =
  | { periodType: "MONTH"; year: number; month: number }
  | { periodType: "QUARTER"; year: number; quarter: number }
  | { periodType: "HALF_YEAR"; year: number; half: number }
  | { periodType: "YEAR"; year: number }
  | { periodType: "ALL_TIME" };

/** 指標ごとの表示ラベル・並び順（大きいほど上位か、小さいほど上位か） */
export const RANKING_METRIC_LABELS: Record<RankingMetric, string> = {
  AVERAGE_RANK: "平均着順",
  TOTAL_POINTS: "ポイント",
  FIRST_PLACE_RATE: "トップ率",
  SECOND_PLACE_RATE: "2着率",
  TOP_TWO_RATE: "連対率",
  NON_LAST_RATE: "ラス回避率",
  TOTAL_GAMES: "対局数",
  PARTICIPATED_EVENTS: "参加イベント数",
  TOTAL_CHIPS: "チップポイント",
  AVERAGE_CHIPS: "平均チップポイント",
};

/** averageRankのみ小さいほど上位（着順は数値が小さいほど良い）。他は大きいほど上位。 */
export const RANKING_ASCENDING_METRICS: ReadonlySet<RankingMetric> = new Set(["AVERAGE_RANK"]);

/** 足切り（最低対局数）が適用可能な指標（率・平均系のみ、Issue #40決定事項6） */
export const RANKING_MIN_GAMES_APPLICABLE_METRICS: ReadonlySet<RankingMetric> = new Set([
  "AVERAGE_RANK",
  "FIRST_PLACE_RATE",
  "SECOND_PLACE_RATE",
  "TOP_TWO_RATE",
  "NON_LAST_RATE",
]);

const RANKING_METRIC_VALUE_GETTERS: Record<
  RankingMetric,
  (stats: RankingMemberStats) => number
> = {
  AVERAGE_RANK: (s) => s.averageRank,
  TOTAL_POINTS: (s) => s.totalPoints,
  FIRST_PLACE_RATE: (s) => s.firstPlaceRate,
  SECOND_PLACE_RATE: (s) => s.secondPlaceRate,
  TOP_TWO_RATE: (s) => s.topTwoRate,
  NON_LAST_RATE: (s) => s.nonLastRate,
  TOTAL_GAMES: (s) => s.totalGames,
  PARTICIPATED_EVENTS: (s) => s.participatedEvents,
  TOTAL_CHIPS: (s) => s.totalChips,
  AVERAGE_CHIPS: (s) => s.averageChips,
};

export function getRankingMetricValue(stats: RankingMemberStats, metric: RankingMetric) {
  return RANKING_METRIC_VALUE_GETTERS[metric](stats);
}
