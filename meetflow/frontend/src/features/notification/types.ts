/**
 * notifications.py _to_api_notification() のレスポンス実体。
 * messageはサーバー側で既に日本語化済みなので、フロントでtype→文言の
 * 再マッピングは行わない（type_subscriber.pyの_MESSAGES参照）。
 */
export type NotificationItem = {
  notificationId: string;
  type: "CONFIRMED" | "CANCELLED" | "CANCEL_APPROVED" | "CANDIDATE_CONFLICT" | "AVAILABILITY_REQUEST";
  message: string;
  read: boolean;
  relatedEventId: string | null;
  createdAt: string;
};
