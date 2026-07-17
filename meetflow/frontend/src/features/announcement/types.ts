/**
 * feedback_lambda/handlers/announcements.py _to_api_announcement() の
 * レスポンス実体（API設計書v1.17 §12c）。
 */
export type AnnouncementStatus = "DRAFT" | "PUBLISHED" | "ARCHIVED";

export type Announcement = {
  announcementId: string;
  title: string;
  body: string;
  status: AnnouncementStatus;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
};

export const ANNOUNCEMENT_STATUS_LABELS: Record<AnnouncementStatus, string> = {
  DRAFT: "下書き",
  PUBLISHED: "公開中",
  ARCHIVED: "取り下げ済み",
};
