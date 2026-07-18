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

/** POST /users/me/avatar/upload-url（Issue #47） */
function presignAvatarUpload(contentType: string) {
  return apiClient.post<{ uploadUrl: string; avatarUrl: string; expiresIn: number }>(
    "/users/me/avatar/upload-url",
    { contentType },
  );
}

/**
 * アバター画像をS3へ直接PUTし、確定後の公開URLを返す。apiClientは経由しない
 * （アップロード先の認可はCognitoトークンではなく署名付きURL自体が担うため。
 * feedback機能の添付アップロードと同じ方式）。呼び出し元はこのURLを
 * `updateMyProfile({ icon: avatarUrl })`にそのまま渡して確定する。
 */
export async function uploadAvatarImage(blob: Blob, contentType: string): Promise<string> {
  const { uploadUrl, avatarUrl } = await presignAvatarUpload(contentType);
  const res = await fetch(uploadUrl, {
    method: "PUT",
    headers: { "Content-Type": contentType },
    body: blob,
  });
  if (!res.ok) {
    throw new Error("アバター画像のアップロードに失敗しました");
  }
  return avatarUrl;
}
