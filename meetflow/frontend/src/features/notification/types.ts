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
  /** AVAILABILITY_REQUEST等、イベント単位ではなくコミュニティ単位の遷移先を持つ通知用（Issue #73） */
  relatedCommunityId: string | null;
  createdAt: string;
};
