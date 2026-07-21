import { apiClient } from "@/api/client";
import type {
  CancelRequest,
  CreateEventInput,
  EventDetail,
  EventSummary,
  MyEvent,
  Participant,
  ParticipationApproveResult,
  ParticipationRejectResult,
} from "@/features/event/types";

export const eventKeys = {
  communityEvents: (communityId: string, status?: string) =>
    ["communities", communityId, "events", status ?? "all"] as const,
  detail: (eventId: string) => ["events", eventId] as const,
  participants: (eventId: string) => ["events", eventId, "participants"] as const,
  cancelRequests: (eventId: string) => ["events", eventId, "cancelRequests"] as const,
  myEvents: ["events", "me"] as const,
};

/** GET /users/me/events（Issue #12） */
export function listMyEvents() {
  return apiClient.get<{ events: MyEvent[] }>("/users/me/events").then((data) => data.events);
}

/** POST /events */
export function createEvent(input: CreateEventInput) {
  return apiClient.post<EventDetail>("/events", input);
}

/** GET /events/{eventId} */
export function getEvent(eventId: string) {
  return apiClient.get<EventDetail>(`/events/${eventId}`);
}

/**
 * POST /events/{eventId}/confirm
 * memberIds省略時は候補メンバー全員を参加者にする（後方互換）。
 * Issue #79: 管理者が候補メンバーの一部だけを選んで仮確定できるように、
 * 選択したメンバーIDリストを渡せるようにした。
 */
export function confirmEvent(eventId: string, memberIds?: string[]) {
  return apiClient.post<EventDetail>(
    `/events/${eventId}/confirm`,
    memberIds ? { memberIds } : undefined,
  );
}

/** POST /events/{eventId}/cancel（イベント全体の中止） */
export function cancelEvent(eventId: string) {
  return apiClient.post<{ eventId: string; status: "CANCELLED" }>(`/events/${eventId}/cancel`);
}

/** POST /events/{eventId}/complete（本日の対局を終了し、成績をコミュニティの通算成績に反映する） */
export function completeEvent(eventId: string) {
  return apiClient.post<{ eventId: string; status: "COMPLETED" }>(`/events/${eventId}/complete`);
}

/** GET /communities/{communityId}/events?status=... */
export function listCommunityEvents(communityId: string, status?: string) {
  const query = status ? `?status=${status}` : "";
  return apiClient
    .get<{ events: EventSummary[] }>(`/communities/${communityId}/events${query}`)
    .then((data) => data.events);
}

/** GET /events/{eventId}/participants */
export function listParticipants(eventId: string) {
  return apiClient
    .get<{ participants: Participant[] }>(`/events/${eventId}/participants`)
    .then((data) => data.participants);
}

/** GET /events/{eventId}/cancel-requests */
export function listCancelRequests(eventId: string) {
  return apiClient
    .get<{ cancelRequests: CancelRequest[] }>(`/events/${eventId}/cancel-requests`)
    .then((data) => data.cancelRequests);
}

/** POST /events/{eventId}/cancel-request（個人の離脱申請） */
export function createCancelRequest(eventId: string, reason: string) {
  return apiClient.post(`/events/${eventId}/cancel-request`, { reason });
}

/** POST /events/{eventId}/cancel-requests/{userId}/approve */
export function approveCancelRequest(eventId: string, userId: string) {
  return apiClient.post(`/events/${eventId}/cancel-requests/${userId}/approve`);
}

/** POST /events/{eventId}/participants/me/approve（Issue #10 F-502b） */
export function approveParticipation(eventId: string) {
  return apiClient.post<ParticipationApproveResult>(
    `/events/${eventId}/participants/me/approve`,
  );
}

/** POST /events/{eventId}/participants/me/reject（Issue #10 F-502c） */
export function rejectParticipation(eventId: string, reason?: string) {
  return apiClient.post<ParticipationRejectResult>(
    `/events/${eventId}/participants/me/reject`,
    reason ? { reason } : {},
  );
}
