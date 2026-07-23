import { apiClient } from "@/api/client";
import type {
  FeedbackCategory,
  FeedbackItem,
  FeedbackRating,
  FeedbackStats,
  QuickStatsPeriod,
} from "@/features/feedback/types";

export const feedbackKeys = {
  all: ["feedback"] as const,
  list: (filters: FeedbackListFilters) => ["feedback", "list", filters] as const,
  detail: (feedbackId: string) => ["feedback", "detail", feedbackId] as const,
  stats: (period: QuickStatsPeriod) => ["feedback", "stats", period] as const,
};

type CreateQuickFeedbackInput = {
  kind: "QUICK";
  relatedFeature: string;
  rating: FeedbackRating;
};
type CreateDetailedFeedbackInput = {
  kind: "DETAILED";
  relatedFeature: string;
  category: FeedbackCategory;
  content?: string;
  attachmentKeys?: string[];
};

/** POST /feedback（F-1401/F-1402） */
export function createFeedback(
  input: CreateQuickFeedbackInput | CreateDetailedFeedbackInput,
) {
  return apiClient.post<{ feedbackId: string; createdAt: string }>("/feedback", input);
}

/** POST /feedback/attachments/presign（F-1402） */
function presignFeedbackAttachment(contentType: string) {
  return apiClient.post<{
    uploadUrl: string;
    uploadFields: Record<string, string>;
    attachmentKey: string;
    expiresIn: number;
  }>("/feedback/attachments/presign", { contentType });
}

/**
 * スクリーンショットをS3へ直接POSTする。apiClientは経由しない
 * （アップロード先の認可はCognitoトークンではなく署名付きURL自体が
 * 担うため。Lambda設計書v1.7 §9b.3）。
 * Issue #103: S3側でファイルサイズ上限（content-length-range）を強制する
 * ためpresigned POST方式（`uploadFields`をFormDataに詰めて送る）に切り替えた。
 */
export async function uploadFeedbackAttachment(file: File): Promise<string> {
  const { uploadUrl, uploadFields, attachmentKey } = await presignFeedbackAttachment(file.type);
  const formData = new FormData();
  for (const [key, value] of Object.entries(uploadFields)) {
    formData.append(key, value);
  }
  formData.append("file", file);
  const res = await fetch(uploadUrl, { method: "POST", body: formData });
  if (!res.ok) {
    throw new Error("スクリーンショットのアップロードに失敗しました");
  }
  return attachmentKey;
}

export type FeedbackListFilters = {
  status?: string;
  category?: string;
  kind?: string;
};

/** GET /feedback（運営者限定、F-1403） */
export function listFeedback(filters: FeedbackListFilters = {}) {
  const query = new URLSearchParams(
    Object.entries(filters).filter((entry): entry is [string, string] => !!entry[1]),
  ).toString();
  return apiClient
    .get<{ feedbacks: FeedbackItem[] }>(`/feedback${query ? `?${query}` : ""}`)
    .then((data) => data.feedbacks);
}

/** GET /feedback/{feedbackId}（運営者限定、F-1403） */
export function getFeedback(feedbackId: string) {
  return apiClient.get<FeedbackItem>(`/feedback/${feedbackId}`);
}

/** PATCH /feedback/{feedbackId}（運営者限定、F-1403/F-1404） */
export function updateFeedback(
  feedbackId: string,
  input: { status?: string; priority?: string; reply?: string },
) {
  return apiClient.patch<{ feedbackId: string; updatedAt: string }>(
    `/feedback/${feedbackId}`,
    input,
  );
}

/** GET /feedback/stats（運営者限定、F-1405）。periodはQUICK評価の集計粒度（Issue #85） */
export function getFeedbackStats(period: QuickStatsPeriod = "WEEK") {
  return apiClient.get<FeedbackStats>(`/feedback/stats?period=${period}`);
}
