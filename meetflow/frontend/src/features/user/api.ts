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

/**
 * DELETE /users/me（Issue #82）
 * アカウント削除（Cognitoユーザー自体の退会）。所属コミュニティで
 * オーナーを務めている、または未来の確定イベント参加が残っている場合は
 * サーバー側でブロックされる（それぞれLAST_OWNER_CANNOT_LEAVE /
 * MEMBER_HAS_UPCOMING_EVENTSとしてエラーになる）。
 */
export function deleteMyAccount() {
  return apiClient.delete<{ userId: string; deleted: true }>("/users/me");
}

/** POST /users/me/avatar/upload-url（Issue #47） */
function presignAvatarUpload(contentType: string) {
  return apiClient.post<{
    uploadUrl: string;
    uploadFields: Record<string, string>;
    avatarUrl: string;
    expiresIn: number;
  }>("/users/me/avatar/upload-url", { contentType });
}

/**
 * アバター画像をS3へ直接POSTし、確定後の公開URLを返す。apiClientは経由しない
 * （アップロード先の認可はCognitoトークンではなく署名付きURL自体が担うため。
 * feedback機能の添付アップロードと同じ方式）。呼び出し元はこのURLを
 * `updateMyProfile({ icon: avatarUrl })`にそのまま渡して確定する。
 * Issue #103: S3側でファイルサイズ上限（content-length-range）を強制する
 * ためpresigned POST方式（`uploadFields`をFormDataに詰めて送る）に切り替えた。
 */
export async function uploadAvatarImage(blob: Blob, contentType: string): Promise<string> {
  const { uploadUrl, uploadFields, avatarUrl } = await presignAvatarUpload(contentType);
  const formData = new FormData();
  for (const [key, value] of Object.entries(uploadFields)) {
    formData.append(key, value);
  }
  formData.append("file", blob);
  const res = await fetch(uploadUrl, { method: "POST", body: formData });
  if (!res.ok) {
    throw new Error("アバター画像のアップロードに失敗しました");
  }
  return avatarUrl;
}

/**
 * DELETE /users/me/avatar（Issue #76）
 * DB上のicon参照とS3上のファイルの両方をバックエンドで削除し、
 * 更新後のプロフィールを返す。
 */
export function deleteMyAvatar() {
  return apiClient.delete<UserProfile>("/users/me/avatar");
}
