import { getIdToken } from "@/features/auth/api";
import { ApiError } from "@/api/errors";
import type { ApiResponseBody } from "@/types/api";

async function request<T>(
  baseUrl: string,
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const idToken = await getIdToken();
  const res = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(idToken ? { Authorization: `Bearer ${idToken}` } : {}),
      ...init.headers,
    },
  });

  const body = (await res.json()) as ApiResponseBody<T>;
  if (!body.success) {
    throw new ApiError(body.error.code, body.error.message, res.status);
  }
  return body.data;
}

/**
 * API設計書v1.5に定義された統一レスポンス形式を前提にした薄いfetchラッパー。
 * トークンが無い場合はAuthorizationヘッダーを付けずに送信し、
 * バックエンドが返す401をそのままUNAUTHORIZEDとしてUI層に伝える
 * （クライアント側で先回りしてリダイレクトはしない）。
 *
 * ベースURLを引数に取るのは、Mリーグドラフト企画（docs/draft/DESIGN.md §4.11）が
 * 本体とは別のAPI Gatewayに立っているため。トークン注入・エンベロープ判定・
 * ApiErrorへの変換はどちらのAPIでも同じなので、`request`を共有して
 * ベースURLだけ差し替える。
 */
function createApiClient(baseUrl: string) {
  return {
    get: <T>(path: string) => request<T>(baseUrl, path),
    post: <T>(path: string, data?: unknown) =>
      request<T>(baseUrl, path, {
        method: "POST",
        body: data !== undefined ? JSON.stringify(data) : undefined,
      }),
    put: <T>(path: string, data?: unknown) =>
      request<T>(baseUrl, path, { method: "PUT", body: JSON.stringify(data) }),
    patch: <T>(path: string, data?: unknown) =>
      request<T>(baseUrl, path, { method: "PATCH", body: JSON.stringify(data) }),
    delete: <T>(path: string, data?: unknown) =>
      request<T>(baseUrl, path, {
        method: "DELETE",
        body: data !== undefined ? JSON.stringify(data) : undefined,
      }),
  };
}

export const apiClient = createApiClient(import.meta.env.VITE_API_BASE_URL);

/**
 * Mリーグドラフト企画専用のAPIクライアント（MeetFlowDraftStackのDraftApi）。
 * Authorizerは本体と同じCognito User Poolを参照しているため、トークンは
 * そのまま使い回せる。
 */
export const draftApiClient = createApiClient(import.meta.env.VITE_DRAFT_API_BASE_URL);
