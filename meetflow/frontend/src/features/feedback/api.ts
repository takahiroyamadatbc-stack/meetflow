import { apiClient } from "@/api/client";
import type {
  FeedbackCategory,
  FeedbackItem,
  FeedbackRating,
  FeedbackStats,
} from "@/features/feedback/types";

export const feedbackKeys = {
  all: ["feedback"] as const,
  list: (filters: FeedbackListFilters) => ["feedback", "list", filters] as const,
  detail: (feedbackId: string) => ["feedback", "detail", feedbackId] as const,
  stats: ["feedback", "stats"] as const,
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
  return apiClient.post<{ uploadUrl: string; attachmentKey: string; expiresIn: number }>(
    "/feedback/attachments/presign",
    { contentType },
  );
}

/**
 * スクリーンショットをS3へ直接PUTする。apiClientは経由しない
 * （アップロード先の認可はCognitoトークンではなく署名付きURL自体が
 * 担うため。Lambda設計書v1.7 §9b.3）。
 */
export async function uploadFeedbackAttachment(file: File): Promise<string> {
  const { uploadUrl, attachmentKey } = await presignFeedbackAttachment(file.type);
  const res = await fetch(uploadUrl, {
    method: "PUT",
    headers: { "Content-Type": file.type },
    body: file,
  });
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

/** GET /feedback/stats（運営者限定、F-1405） */
export function getFeedbackStats() {
  return apiClient.get<FeedbackStats>("/feedback/stats");
}
