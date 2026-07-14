import { apiClient } from "@/api/client";
import type {
  CommunityMember,
  CommunityMutationResult,
  CommunitySummary,
  CreateCommunityInput,
  JoinRequest,
  UpdateMemberInput,
} from "@/features/community/types";

export const communityKeys = {
  all: ["communities"] as const,
  members: (communityId: string) => ["communities", communityId, "members"] as const,
  joinRequests: (communityId: string) => ["communities", communityId, "joinRequests"] as const,
};

/** GET /communities */
export function listCommunities() {
  return apiClient
    .get<{ communities: CommunitySummary[] }>("/communities")
    .then((data) => data.communities);
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
