import { apiClient } from "@/api/client";
import type {
  GameSessionDetail,
  LastGameSettings,
  ResultSummary,
  SessionInput,
} from "@/features/result/types";

export const resultKeys = {
  summary: (communityId: string, userId: string) =>
    ["communities", communityId, "results", userId] as const,
  eventSessions: (eventId: string) => ["events", eventId, "sessions"] as const,
  lastSettings: (communityId: string) =>
    ["communities", communityId, "game-sessions", "last-settings"] as const,
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

/** GET /events/{eventId}/sessions */
export function listEventSessions(eventId: string) {
  return apiClient
    .get<{ sessions: GameSessionDetail[] }>(`/events/${eventId}/sessions`)
    .then((data) => data.sessions);
}

/** GET /communities/{communityId}/game-sessions/last-settings */
export function getLastGameSettings(communityId: string) {
  return apiClient.get<LastGameSettings>(
    `/communities/${communityId}/game-sessions/last-settings`,
  );
}

/** GET /users/{userId}/results?communityId=... */
export function getUserResults(userId: string, communityId: string) {
  return apiClient.get<ResultSummary>(`/users/${userId}/results?communityId=${communityId}`);
}
