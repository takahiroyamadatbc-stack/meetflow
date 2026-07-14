import { apiClient } from "@/api/client";
import type {
  CommunityDetail,
  CommunityMember,
  CommunityMutationResult,
  CommunitySummary,
  CreateCommunityInput,
  CreatePlaceInput,
  JoinRequest,
  Place,
  UpdateMemberInput,
} from "@/features/community/types";

export const communityKeys = {
  all: ["communities"] as const,
  detail: (communityId: string) => ["communities", communityId] as const,
  members: (communityId: string) => ["communities", communityId, "members"] as const,
  joinRequests: (communityId: string) => ["communities", communityId, "joinRequests"] as const,
  places: (communityId: string) => ["communities", communityId, "places"] as const,
};

/** GET /communities */
export function listCommunities() {
  return apiClient
    .get<{ communities: CommunitySummary[] }>("/communities")
    .then((data) => data.communities);
}

/** GET /communities/{communityId} */
export function getCommunity(communityId: string) {
  return apiClient.get<CommunityDetail>(`/communities/${communityId}`);
}

/** POST /communities */
export function createCommunity(input: CreateCommunityInput) {
  return apiClient.post<CommunityMutationResult>("/communities", input);
}

/** PUT /communities/{communityId} */
export function updateCommunity(communityId: string, input: Partial<CreateCommunityInput>) {
  return apiClient.put<CommunityMutationResult>(`/communities/${communityId}`, input);
}

/** POST /communities/{communityId}/invite */
export function createInvite(communityId: string) {
  return apiClient.post<{ url: string }>(`/communities/${communityId}/invite`);
}

/** POST /invites/{token}/join */
export function joinViaInvite(token: string, message?: string) {
  return apiClient.post<{ communityId: string; status: "ACTIVE" | "PENDING" }>(
    `/invites/${token}/join`,
    message ? { message } : undefined,
  );
}

/** GET /communities/{communityId}/members */
export function listMembers(communityId: string) {
  return apiClient
    .get<{ members: CommunityMember[] }>(`/communities/${communityId}/members`)
    .then((data) => data.members);
}

/** PUT /communities/{communityId}/members/{userId} */
export function updateMember(communityId: string, userId: string, input: UpdateMemberInput) {
  return apiClient.put(`/communities/${communityId}/members/${userId}`, input);
}

/** GET /communities/{communityId}/join-requests（statusフィルタはPENDING固定で扱う） */
export function listJoinRequests(communityId: string) {
  return apiClient
    .get<{ requests: JoinRequest[] }>(`/communities/${communityId}/join-requests?status=PENDING`)
    .then((data) => data.requests);
}

/** POST /communities/{communityId}/join-requests/{requestId}/approve */
export function approveJoinRequest(communityId: string, requestId: string) {
  return apiClient.post(`/communities/${communityId}/join-requests/${requestId}/approve`);
}

/** POST /communities/{communityId}/join-requests/{requestId}/reject */
export function rejectJoinRequest(communityId: string, requestId: string) {
  return apiClient.post(`/communities/${communityId}/join-requests/${requestId}/reject`);
}

/** GET /communities/{communityId}/locations */
export function listPlaces(communityId: string) {
  return apiClient
    .get<{ places: Place[] }>(`/communities/${communityId}/locations`)
    .then((data) => data.places);
}

/** POST /communities/{communityId}/locations */
export function createPlace(communityId: string, input: CreatePlaceInput) {
  return apiClient.post<Place>(`/communities/${communityId}/locations`, input);
}
