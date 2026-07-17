/**
 * API呼び出しで発生したエラーを表す例外。
 * エラーコード一覧v1.2 §2の統一エラーレスポンス
 * {"success":false,"error":{"code":"...","message":"..."}} をラップする。
 */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

/** エラーコード一覧v1.2 §10「フロントエンド表示方針」の4分類 */
export type ErrorDisplay = "inline" | "toast" | "modal" | "empty";

/** インライン（フォーム項目下）で表示するエラーコード（同§10表） */
const INLINE_CODES = new Set([
  "INVALID_PARAMETER",
  "INVALID_TIME_RANGE",
  "INVALID_PLAYER_RANGE",
  "RESULT_VALIDATION_ERROR",
  "PROFILE_VALIDATION_ERROR",
  "DISPLAY_NAME_ALREADY_TAKEN",
]);

/** モーダル（明示的な操作が必要）で表示するエラーコード（同§10表） */
const MODAL_CODES = new Set([
  "UNAUTHORIZED",
  "FORBIDDEN",
  "PARTICIPANT_SCHEDULE_CONFLICT",
  "MEMBER_HAS_UPCOMING_EVENTS",
]);

/** トースト（一時的なエラー）で表示するエラーコード（同§10表） */
const TOAST_CODES = new Set([
  "INTERNAL_ERROR",
  "AVAILABILITY_OVERLAP",
  "ALREADY_MEMBER",
  "JOIN_REQUEST_ALREADY_PENDING",
  "CANCEL_REQUEST_ALREADY_PENDING",
  "CANCEL_REQUEST_ALREADY_PROCESSED",
  "CANDIDATE_ALREADY_USED",
  "EVENT_ALREADY_CONFIRMED",
  "EVENT_ALREADY_CANCELLED",
  "COMMUNITY_NOT_EMPTY",
]);

/** 空状態画面で表示するエラーコード（`*_NOT_FOUND`系は接尾辞で判定） */
const EMPTY_CODES = new Set(["NO_CANDIDATES_FOUND"]);

/**
 * エラーコードから表示方式を判定する。一覧に無いコードは
 * `INTERNAL_ERROR`同様「トーストのデフォルト受け皿」として扱う
 * （エラーコード一覧v1.2 §2の注記に対応）。
 */
export function getErrorDisplay(code: string): ErrorDisplay {
  if (INLINE_CODES.has(code)) return "inline";
  if (MODAL_CODES.has(code)) return "modal";
  if (TOAST_CODES.has(code)) return "toast";
  if (EMPTY_CODES.has(code) || code.endsWith("_NOT_FOUND")) return "empty";
  return "toast";
}
