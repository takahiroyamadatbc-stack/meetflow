import { apiClient } from "@/api/client";
import type {
  CommunityDetail,
  CommunityMember,
  CommunityMutationResult,
  CommunitySummary,
  CreateCommunityInput,
  CreatePlaceInput,
  InvitePreview,
  JoinRequest,
  Place,
  UpdateMemberInput,
} from "@/features/community/types";
import type { FrequencyLimitPeriod } from "@/features/user/types";

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

/**
 * PUT /communities/order（Issue #16。API設計書には無い新規エンドポイント）。
 * 渡した順にコミュニティ一覧の表示順を並び替える。
 */
export function reorderCommunities(communityIds: string[]) {
  return apiClient.put<{ communityIds: string[] }>("/communities/order", { communityIds });
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

/**
 * PUT /communities/{communityId}/theme-color（Issue #5）。
 * 空文字を送るとテーマカラー設定を解除する。
 */
export function updateThemeColor(communityId: string, themeColor: string) {
  return apiClient.put<{ communityId: string; themeColor: string | null }>(
    `/communities/${communityId}/theme-color`,
    { themeColor },
  );
}

/** POST /communities/{communityId}/icon/upload-url（Issue #52） */
function presignCommunityIconUpload(communityId: string, contentType: string) {
  return apiClient.post<{ uploadUrl: string; iconUrl: string; expiresIn: number }>(
    `/communities/${communityId}/icon/upload-url`,
    { contentType },
  );
}

/**
 * コミュニティアイコン画像をS3へ直接PUTし、確定後の公開URLを返す。
 * ユーザーアバターのアップロード（uploadAvatarImage、Issue #47）と同じ方式
 * （apiClientは経由せず、署名付きURL自体が書き込み認可を担う）。
 * 呼び出し元はこのURLを`updateCommunity(communityId, { icon: iconUrl })`に
 * そのまま渡して確定する。
 */
export async function uploadCommunityIconImage(
  communityId: string,
  blob: Blob,
  contentType: string,
): Promise<string> {
  const { uploadUrl, iconUrl } = await presignCommunityIconUpload(communityId, contentType);
  const res = await fetch(uploadUrl, {
    method: "PUT",
    headers: { "Content-Type": contentType },
    body: blob,
  });
  if (!res.ok) {
    throw new Error("コミュニティアイコン画像のアップロードに失敗しました");
  }
  return iconUrl;
}

/**
 * DELETE /communities/{communityId}（Issue #2）。
 * 自分以外のメンバーが在籍している場合は409 COMMUNITY_NOT_EMPTYが返る。
 */
export function deleteCommunity(communityId: string) {
  return apiClient.delete<{ communityId: string; deleted: boolean }>(
    `/communities/${communityId}`,
  );
}

/** POST /communities/{communityId}/invite */
export function createInvite(communityId: string) {
  return apiClient.post<{ url: string }>(`/communities/${communityId}/invite`);
}

/** GET /invites/{token}（Issue #23：招待受諾画面が承認要否を事前判定するためのプレビューAPI） */
export function getInvitePreview(token: string) {
  return apiClient.get<InvitePreview>(`/invites/${token}`);
}

/** POST /invites/{token}/join */
export function joinViaInvite(token: string, message?: string) {
  return apiClient.post<{ communityId: string; status: "ACTIVE" | "PENDING" }>(
    `/invites/${token}/join`,
    message ? { message } : undefined,
  );
}

/** POST /invites/{token}/revoke */
export function revokeInvite(token: string) {
  return apiClient.post<{ token: string; communityId: string; revoked: boolean }>(
    `/invites/${token}/revoke`,
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

/** POST /communities/{communityId}/owner-transfer（Issue #24 F-106） */
export function transferOwner(communityId: string, newOwnerId: string) {
  return apiClient.post<{ communityId: string; ownerId: string }>(
    `/communities/${communityId}/owner-transfer`,
    { newOwnerId },
  );
}

/** POST /communities/{communityId}/members/me/leave（Issue #25 F-104d） */
export function leaveCommunity(communityId: string) {
  return apiClient.post<{ communityId: string; userId: string; left: boolean }>(
    `/communities/${communityId}/members/me/leave`,
  );
}

/** PUT /communities/{communityId}/members/me/display-name */
export function updateMyDisplayName(communityId: string, displayName: string) {
  return apiClient.put<{ communityId: string; userId: string; displayName: string | null }>(
    `/communities/${communityId}/members/me/display-name`,
    { displayName },
  );
}

/** PUT /communities/{communityId}/members/me/auto-approve（Issue #10 F-109b） */
export function updateMyAutoApprove(communityId: string, autoApprove: boolean | null) {
  return apiClient.put<{ communityId: string; userId: string; autoApprove: boolean | null }>(
    `/communities/${communityId}/members/me/auto-approve`,
    { autoApprove },
  );
}

/** PUT /communities/{communityId}/members/me/frequency-limit（Issue #19 F-109b） */
export function updateMyFrequencyLimit(
  communityId: string,
  frequencyLimitCount: number | null,
  frequencyLimitPeriod: FrequencyLimitPeriod | null,
) {
  return apiClient.put<{
    communityId: string;
    userId: string;
    frequencyLimitCount: number | null;
    frequencyLimitPeriod: FrequencyLimitPeriod | null;
  }>(`/communities/${communityId}/members/me/frequency-limit`, {
    frequencyLimitCount,
    frequencyLimitPeriod,
  });
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
