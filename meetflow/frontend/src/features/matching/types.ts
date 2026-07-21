import { GAME_TYPE_LABELS, type GameType } from "@/features/user/types";

/**
 * backend/functions/matching_lambda/handlers/event_templates.py の
 * _to_api_template() レスポンス実体。人数条件は範囲判定
 * （minPlayers〜maxPlayersの範囲内であること。厳密な一致ではない）。
 *
 * gameTypeは麻雀コミュニティではGameType（MAHJONG4/MAHJONG3）、それ以外の
 * ジャンルのコミュニティではコミュニティのジャンルと同じ固定値1つのみ
 * （Issue #92。細分類は設けない）となるため、バックエンド同様string型で
 * 受ける。表示には`gameTypeLabel()`を使うこと。
 */
export type EventTemplate = {
  templateId: string;
  gameType: string;
  minPlayers: number;
  maxPlayers: number;
  priority: number;
  conditions: { beginnerOk?: boolean };
};

export type EventTemplateInput = {
  gameType: string;
  minPlayers: number;
  maxPlayers: number;
  priority: number;
  conditions: { beginnerOk?: boolean };
};

/** GAME_TYPE_LABELSに無いgameType（Issue #92：麻雀以外のジャンルではコミュニティの
 * ジャンル名がそのままgameTypeになる）は、値自体が既に表示用ラベルを兼ねる。 */
export function gameTypeLabel(gameType: string): string {
  return GAME_TYPE_LABELS[gameType as GameType] ?? gameType;
}

/** matching.py _to_api_candidate() が返す候補メンバー1件分 */
export type CandidateMemberInfo = {
  userId: string;
  nickname: string;
  /** 参考情報のみ（要件定義書v1.4 §17）：スコアリング・自動除外には使わない */
  fairnessCount: number;
  /** 事後検知されたダブルブッキング参考警告。承認時の同期ハードチェックとは別物 */
  conflictWarning: boolean;
};

/** matching.py _to_api_candidate() のレスポンス実体 */
export type Candidate = {
  candidateId: string;
  /** Issue #56: 手動作成候補（管理者が承認フロー無しで直接作成）はnull */
  templateId: string | null;
  /** Issue #56: 手動作成候補はスコアリングを経ないためnull */
  score: number | null;
  status: "PENDING" | "CONFIRMED" | "DISCARDED";
  reasons: string[];
  startTime: string | null;
  endTime: string | null;
  members: CandidateMemberInfo[];
  /** 候補の生成日時（ISO8601、Issue #28） */
  createdAt: string;
  /** Issue #56: 手動作成候補のみ持つ、その場で自由入力したゲーム種別 */
  gameType: GameType | null;
};

/** POST /communities/{communityId}/matching/candidates/manual のリクエスト実体（Issue #56） */
export type CreateManualCandidateInput = {
  memberIds: string[];
  startTime: string;
  endTime: string;
  gameType?: GameType;
};
