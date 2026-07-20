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
