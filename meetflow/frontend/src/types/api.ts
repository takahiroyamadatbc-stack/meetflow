/**
 * API設計書v1.5 §2の統一レスポンス形式に対応する共通型。
 * バックエンドの success_response / error_response（meetflow_common.errors）が
 * 返す envelope をそのまま表現する。
 */
export type ApiSuccessBody<T> = {
  success: true;
  data: T;
};

export type ApiErrorBody = {
  success: false;
  error: {
    code: string;
    message: string;
  };
};

export type ApiResponseBody<T> = ApiSuccessBody<T> | ApiErrorBody;

/** メンバーシップのロール（Lambda設計書、DynamoDB物理設計書で共通） */
export type MembershipRole = "OWNER" | "ADMIN" | "MEMBER";
