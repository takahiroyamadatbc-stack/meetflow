import { apiClient } from "@/api/client";
import type { UpdateUserProfileInput, UserProfile } from "@/features/user/types";

export const userKeys = {
  me: ["users", "me"] as const,
};

/** GET /users/me */
export function getMyProfile() {
  return apiClient.get<UserProfile>("/users/me");
}

/** PUT /users/me */
export function updateMyProfile(input: UpdateUserProfileInput) {
  return apiClient.put<UserProfile>("/users/me", input);
}
