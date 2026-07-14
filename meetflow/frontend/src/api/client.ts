import { getIdToken } from "@/features/auth/api";
import { ApiError } from "@/api/errors";
import type { ApiResponseBody } from "@/types/api";

const BASE_URL = import.meta.env.VITE_API_BASE_URL;

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const idToken = await getIdToken();
  const res = await fetch(`${BASE_URL}${path}`, {
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
 */
export const apiClient = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, data?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: data !== undefined ? JSON.stringify(data) : undefined,
    }),
  put: <T>(path: string, data?: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(data) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
