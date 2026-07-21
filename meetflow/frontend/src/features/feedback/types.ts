/**
 * feedback_lambda/handlers/feedback.py _to_api_feedback() のレスポンス実体
 * （API設計書v1.17 §12b）。
 */
export type FeedbackKind = "QUICK" | "DETAILED";
export type FeedbackRating = "BAD" | "NEUTRAL" | "GOOD";
export type FeedbackCategory = "BUG" | "FEATURE_REQUEST" | "UX_IMPROVEMENT";
export type FeedbackStatus = "UNHANDLED" | "PLANNED" | "DONE";
export type FeedbackPriority = "LOW" | "MEDIUM" | "HIGH";

export type FeedbackReply = {
  message: string;
  repliedBy: string;
  repliedAt: string;
};

export type FeedbackItem = {
  feedbackId: string;
  userId: string;
  kind: FeedbackKind;
  relatedFeature: string;
  rating: FeedbackRating | null;
  category: FeedbackCategory | null;
  content: string | null;
  attachmentKeys: string[];
  status: FeedbackStatus;
  priority: FeedbackPriority | null;
  createdAt: string;
  updatedAt: string;
  reply?: FeedbackReply | null;
  /** 詳細取得（GET /feedback/{feedbackId}）でのみ含まれる署名付き閲覧URL */
  attachmentUrls?: string[];
};

/** Issue #85: QUICK評価の週次/月次集計の粒度 */
export type QuickStatsPeriod = "WEEK" | "MONTH";

export type QuickStatsBucket = {
  /** 週(月曜始まり)/月の開始日（`YYYY-MM-DD`） */
  bucketStart: string;
  /** `relatedFeature` -> `rating` -> 件数 */
  byFeatureRating: Record<string, Partial<Record<FeedbackRating, number>>>;
};

export type FeedbackStats = {
  byCategory: Record<string, number>;
  byStatus: Record<string, number>;
  byPriority: Record<string, number>;
  quickStats: {
    period: QuickStatsPeriod;
    buckets: QuickStatsBucket[];
  };
};

export const FEEDBACK_CATEGORY_LABELS: Record<FeedbackCategory, string> = {
  BUG: "バグ報告",
  FEATURE_REQUEST: "機能提案",
  UX_IMPROVEMENT: "UX改善",
};

export const FEEDBACK_STATUS_LABELS: Record<FeedbackStatus, string> = {
  UNHANDLED: "未対応",
  PLANNED: "実装予定",
  DONE: "実装完了",
};

export const FEEDBACK_PRIORITY_LABELS: Record<FeedbackPriority, string> = {
  LOW: "低",
  MEDIUM: "中",
  HIGH: "高",
};

/** QuickFeedbackPromptの表示順・絵文字と揃える（Issue #85のグラフ凡例でも使用） */
export const FEEDBACK_RATING_LABELS: Record<FeedbackRating, string> = {
  GOOD: "😊 満足",
  NEUTRAL: "😐 ふつう",
  BAD: "😞 不満",
};

/** 該当機能の選択肢（S-28詳細投稿フォーム）。QuickFeedbackPromptの埋め込み箇所とも対応する */
export const RELATED_FEATURE_OPTIONS = [
  { value: "MATCHING_CANDIDATE", label: "マッチング候補" },
  { value: "EVENT_CONFIRM", label: "イベント確定" },
  { value: "AVAILABILITY", label: "空き予定登録" },
  { value: "COMMUNITY", label: "コミュニティ管理" },
  { value: "RESULT", label: "成績登録・集計" },
  { value: "NOTIFICATION", label: "通知" },
  { value: "OTHER", label: "その他" },
] as const;
