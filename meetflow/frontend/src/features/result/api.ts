import { apiClient } from "@/api/client";
import type {
  ChipRecord,
  ChipRecordInput,
  CommunityRanking,
  GameSessionDetail,
  LastGameSettings,
  RankingPeriodParams,
  ResultSummary,
  SessionInput,
} from "@/features/result/types";
import type { GameType } from "@/features/user/types";

export const resultKeys = {
  summary: (communityId: string, userId: string) =>
    ["communities", communityId, "results", userId] as const,
  eventSessions: (eventId: string) => ["events", eventId, "sessions"] as const,
  eventChipRecords: (eventId: string) => ["events", eventId, "chip-records"] as const,
  lastSettings: (communityId: string, eventId: string) =>
    ["communities", communityId, "game-sessions", "last-settings", eventId] as const,
  ranking: (communityId: string, gameType: GameType, period: RankingPeriodParams) =>
    ["communities", communityId, "rankings", gameType, period] as const,
};

/** POST /events/{eventId}/sessions */
export function createSession(eventId: string, input: SessionInput) {
  return apiClient.post<GameSessionDetail>(`/events/${eventId}/sessions`, input);
}

/** PUT /events/{eventId}/sessions/{sessionNo} */
export function updateSession(eventId: string, sessionNo: string, input: SessionInput) {
  return apiClient.put<GameSessionDetail>(
    `/events/${eventId}/sessions/${sessionNo}`,
    input,
  );
}

/** DELETE /events/{eventId}/sessions/{sessionNo} */
export function deleteSession(eventId: string, sessionNo: string) {
  return apiClient.delete<{ eventId: string; sessionNo: string }>(
    `/events/${eventId}/sessions/${sessionNo}`,
  );
}

/** GET /events/{eventId}/sessions */
export function listEventSessions(eventId: string) {
  return apiClient
    .get<{ sessions: GameSessionDetail[] }>(`/events/${eventId}/sessions`)
    .then((data) => data.sessions);
}

/** GET /events/{eventId}/chip-records（Issue #116） */
export function listChipRecords(eventId: string) {
  return apiClient
    .get<{ records: ChipRecord[] }>(`/events/${eventId}/chip-records`)
    .then((data) => data.records);
}

/** POST /events/{eventId}/chip-records（Issue #116） */
export function createChipRecord(eventId: string, input: ChipRecordInput) {
  return apiClient.post<ChipRecord>(`/events/${eventId}/chip-records`, input);
}

/** PUT /events/{eventId}/chip-records/{recordNo}（Issue #116、OWNER/ADMIN） */
export function updateChipRecord(eventId: string, recordNo: string, input: ChipRecordInput) {
  return apiClient.put<ChipRecord>(`/events/${eventId}/chip-records/${recordNo}`, input);
}

/** DELETE /events/{eventId}/chip-records/{recordNo}（Issue #116、OWNER/ADMIN） */
export function deleteChipRecord(eventId: string, recordNo: string) {
  return apiClient.delete<{ eventId: string; recordNo: string }>(
    `/events/${eventId}/chip-records/${recordNo}`,
  );
}

/**
 * GET /communities/{communityId}/game-sessions/last-settings?eventId=...
 *
 * eventIdを渡すと、同一イベント内で直前に(自分以外を含む)誰かが入力した
 * 設定を優先して返す。イベント内に前例が無ければユーザー本人の直近設定に
 * フォールバックする(Issue #109)。
 */
export function getLastGameSettings(communityId: string, eventId: string) {
  return apiClient.get<LastGameSettings>(
    `/communities/${communityId}/game-sessions/last-settings?eventId=${eventId}`,
  );
}

/** GET /users/{userId}/results?communityId=... */
export function getUserResults(userId: string, communityId: string) {
  return apiClient.get<ResultSummary>(`/users/${userId}/results?communityId=${communityId}`);
}

/**
 * GET /communities/{communityId}/rankings（Issue #40 F-805）。
 * minGames（足切り）はクエリパラメータに含めない -- 各メンバーのtotalGamesが
 * レスポンスに含まれるため、足切り閾値や表示指標の切り替えはフロント側で
 * 再取得なしに行う設計（API設計書v1.25 §10.3）。
 */
export function getCommunityRanking(
  communityId: string,
  gameType: GameType,
  period: RankingPeriodParams,
) {
  const query = new URLSearchParams({ gameType, periodType: period.periodType });
  if (period.periodType === "MONTH") {
    query.set("year", String(period.year));
    query.set("month", String(period.month));
  } else if (period.periodType === "QUARTER") {
    query.set("year", String(period.year));
    query.set("quarter", String(period.quarter));
  } else if (period.periodType === "HALF_YEAR") {
    query.set("year", String(period.year));
    query.set("half", String(period.half));
  } else if (period.periodType === "YEAR") {
    query.set("year", String(period.year));
  }
  return apiClient.get<CommunityRanking>(`/communities/${communityId}/rankings?${query}`);
}
