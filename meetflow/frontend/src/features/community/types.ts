import type { MembershipRole } from "@/types/api";
import type { GameType } from "@/features/user/types";

/**
 * backend/functions/community_lambda/handlers/communities.py の list_communities()
 * レスポンス実体。memberApprovalRequired・メンバー数・communityTypeは
 * 一覧には含まれない（Phase1実装計画の食い違い#2/#3を参照）。
 */
export type CommunitySummary = {
  communityId: string;
  name: string;
  description: string;
  genre: string;
  role: MembershipRole;
};

/**
 * create_community() / update_community() のレスポンス実体。
 * 一覧と違いmemberApprovalRequiredを含むが、roleは含まない
 * （作成者が暗黙にOWNERであるため返却されない）。
 */
export type CommunityMutationResult = {
  communityId: string;
  name: string;
  description: string;
  genre: string;
  memberApprovalRequired: boolean;
};

/** get_community() のレスポンス実体（一覧・作成/更新の両方のフィールドを含む） */
export type CommunityDetail = CommunityMutationResult & {
  role: MembershipRole;
};

export type CreateCommunityInput = {
  name: string;
  description?: string;
  genre?: string;
  memberApprovalRequired?: boolean;
};

/** members.py list_members() のレスポンス実体 */
export type CommunityMember = {
  userId: string;
  nickname: string;
  role: MembershipRole;
  status: "ACTIVE" | "SUSPENDED";
  joinedAt: string;
};

export type UpdateMemberInput = {
  role?: "ADMIN" | "MEMBER";
  status?: "ACTIVE" | "SUSPENDED";
  remove?: boolean;
};

/** join_requests.py list_join_requests() のレスポンス実体 */
export type JoinRequest = {
  requestId: string;
  userId: string;
  nickname: string;
  bio: string;
  gameTypes: GameType[];
  beginnerOk: boolean;
  message: string;
  status: "PENDING" | "APPROVED" | "REJECTED";
  requestedAt: string;
};

/** places.py _to_api_place() のレスポンス実体 */
export type Place = {
  placeId: string;
  name: string;
  address: string;
  note: string;
};

export type CreatePlaceInput = {
  name: string;
  address?: string;
  note?: string;
};
