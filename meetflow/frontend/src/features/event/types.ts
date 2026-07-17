/** イベントのライフサイクル状態（DynamoDB物理設計書v1.10 §3.10） */
export type EventStatus =
  | "DRAFT"
  | "OPEN"
  | "MATCHING"
  | "PENDING_APPROVAL"
  | "AWAITING_MEMBER_APPROVAL"
  | "CONFIRMED"
  | "IN_PROGRESS"
  | "COMPLETED"
  | "CANCELLED";

export const EVENT_STATUS_LABELS: Record<EventStatus, string> = {
  DRAFT: "下書き",
  OPEN: "募集中",
  MATCHING: "マッチング中",
  PENDING_APPROVAL: "承認待ち",
  AWAITING_MEMBER_APPROVAL: "メンバー承認待ち",
  CONFIRMED: "確定",
  IN_PROGRESS: "開催中",
  COMPLETED: "終了",
  CANCELLED: "中止",
};

/** _shared.py to_api_event() のレスポンス実体 */
export type EventDetail = {
  eventId: string;
  communityId: string;
  templateId: string | null;
  candidateId: string | null;
  status: EventStatus;
  startTime: string;
  endTime: string;
  location: { placeId: string; name: string; address: string; note: string } | null;
  locationNote: string;
  createdAt: string;
};

/** events.py list_community_events() のレスポンス実体 */
export type EventSummary = {
  eventId: string;
  startTime: string;
  locationName: string | null;
  status: EventStatus;
};

/**
 * events.py list_my_events() のレスポンス実体（Issue #12。自分が参加する
 * 確定イベントのみを返す。API設計書には無い新規エンドポイント）。
 */
export type MyEvent = {
  eventId: string;
  communityId: string;
  startTime: string;
  endTime: string;
};

/** participants.py list_participants() のレスポンス実体 */
export type ParticipantStatus =
  | "CONFIRMED"
  | "CANCEL_REQUESTED"
  | "CANCELLED"
  | "AWAITING_APPROVAL"
  | "REJECTED";

export type Participant = {
  userId: string;
  nickname: string;
  status: ParticipantStatus;
};

export const PARTICIPANT_STATUS_LABELS: Record<ParticipantStatus, string> = {
  CONFIRMED: "確定",
  CANCEL_REQUESTED: "キャンセル申請中",
  CANCELLED: "キャンセル済み",
  AWAITING_APPROVAL: "承認待ち",
  REJECTED: "辞退",
};

/** participants.py approve_participation() / reject_participation() のレスポンス実体（Issue #10） */
export type ParticipationApproveResult = {
  eventId: string;
  userId: string;
  status: "CONFIRMED";
  eventStatus: EventStatus;
};

export type ParticipationRejectResult = {
  eventId: string;
  userId: string;
  status: "REJECTED";
};

/** participants.py list_cancel_requests() のレスポンス実体 */
export type CancelRequest = {
  userId: string;
  reason: string;
  status: "PENDING" | "APPROVED" | "REJECTED";
  requestedAt: string;
};

export type CreateEventInput = {
  candidateId: string;
  locationId?: string;
  locationNote?: string;
};
