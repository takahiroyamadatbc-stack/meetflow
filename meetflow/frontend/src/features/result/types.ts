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

/** results.py create_session()/update_session() へのリクエストボディ実体 */
export type SessionInput = {
  gameType: GameType;
  calcMode: CalcMode;
  startingPoints?: number;
  returnPoints?: number;
  umaByRank?: number[];
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
    };

/** results.py get_user_results() のレスポンス実体（_aggregate()の集計値） */
export type ResultSummary = {
  userId: string;
  communityId: string;
  totalGames: number;
  averageRank: number;
  firstPlaceRate: number;
  lastPlaceRate: number;
  totalPoints: number;
  totalChips: number;
};
