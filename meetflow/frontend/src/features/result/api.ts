import { apiClient } from "@/api/client";
import type { GameType } from "@/features/user/types";
import type { ResultSummary, SessionResult, SessionResultInput } from "@/features/result/types";

export const resultKeys = {
  summary: (communityId: string, userId: string) =>
    ["communities", communityId, "results", userId] as const,
};

/** POST /events/{eventId}/sessions */
export function createSession(eventId: string, gameType: GameType, results: SessionResultInput[]) {
  return apiClient.post<SessionResult>(`/events/${eventId}/sessions`, { gameType, results });
}

/** GET /users/{userId}/results?communityId=... */
export function getUserResults(userId: string, communityId: string) {
  return apiClient.get<ResultSummary>(`/users/${userId}/results?communityId=${communityId}`);
}
