import { apiClient } from "@/api/client";
import type {
  Availability,
  AvailabilityInput,
  AvailabilityRequest,
  CreateAvailabilityRequestInput,
  PendingMember,
} from "@/features/availability/types";

export const availabilityKeys = {
  list: (communityId: string) => ["availability", communityId] as const,
  requests: (communityId: string) => ["availability-requests", communityId] as const,
  pendingMembers: (communityId: string, requestId: string) =>
    ["availability-requests", communityId, requestId, "pending-members"] as const,
};

/** GET /communities/{communityId}/availability（呼び出し元自身の登録分のみ） */
export function listAvailability(communityId: string) {
  return apiClient
    .get<{ availabilities: Availability[] }>(`/communities/${communityId}/availability`)
    .then((data) => data.availabilities);
}

/** POST /communities/{communityId}/availability/batch */
export function createAvailabilityBatch(communityId: string, entries: AvailabilityInput[]) {
  return apiClient
    .post<{ availabilities: Availability[] }>(
      `/communities/${communityId}/availability/batch`,
      { availabilities: entries },
    )
    .then((data) => data.availabilities);
}

/** DELETE /availability/{availabilityId} */
export function deleteAvailability(availabilityId: string) {
  return apiClient.delete(`/availability/${availabilityId}`);
}

/** POST /communities/{communityId}/availability-requests */
export function createAvailabilityRequest(
  communityId: string,
  input: CreateAvailabilityRequestInput,
) {
  return apiClient.post<AvailabilityRequest>(
    `/communities/${communityId}/availability-requests`,
    input,
  );
}

/** GET /communities/{communityId}/availability-requests */
export function listAvailabilityRequests(communityId: string) {
  return apiClient
    .get<{ requests: AvailabilityRequest[] }>(`/communities/${communityId}/availability-requests`)
    .then((data) => data.requests);
}

/** GET /communities/{communityId}/availability-requests/{requestId}/pending-members */
export function listPendingMembers(communityId: string, requestId: string) {
  return apiClient
    .get<{ pendingMembers: PendingMember[] }>(
      `/communities/${communityId}/availability-requests/${requestId}/pending-members`,
    )
    .then((data) => data.pendingMembers);
}
