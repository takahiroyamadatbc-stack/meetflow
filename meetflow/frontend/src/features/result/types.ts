import type { GameType } from "@/features/user/types";

export type SessionResultInput = {
  userId: string;
  rank: number;
  score: number;
  rankPoints: number;
};

/** results.py create_session() のレスポンス実体 */
export type SessionResult = {
  eventId: string;
  sessionNo: string;
  gameType: GameType;
  results: SessionResultInput[];
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
};
