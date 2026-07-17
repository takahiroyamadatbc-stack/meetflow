/** MVPで扱うゲーム種別（麻雀ドメイン固定。backend/functions/result_lambda等で使用） */
export type GameType = "MAHJONG4" | "MAHJONG3";

export const GAME_TYPE_LABELS: Record<GameType, string> = {
  MAHJONG4: "四人麻雀",
  MAHJONG3: "三人麻雀",
};

/** 参加頻度上限の集計期間（Issue #19、要件定義書v1.7 §30） */
export type FrequencyLimitPeriod = "WEEK" | "MONTH";

export const FREQUENCY_LIMIT_PERIOD_LABELS: Record<FrequencyLimitPeriod, string> = {
  WEEK: "週",
  MONTH: "月",
};

/**
 * backend/functions/user_lambda/handler.py の _to_api_profile() レスポンス実体。
 * DynamoDB上は `bio` 属性だが、APIの契約上は `profile` として公開される点に注意。
 */
export type UserProfile = {
  userId: string;
  nickname: string;
  profile: string;
  icon: string;
  gameTypes: GameType[];
  beginnerOk: boolean;
  /** イベント仮確定後の参加承認を以降自動で行うかどうか（Issue #10、全体デフォルト） */
  autoApprove: boolean;
  /** ゲームジャンル単位の参加頻度上限（Issue #19、全体デフォルト、任意） */
  frequencyLimitCount: number | null;
  frequencyLimitPeriod: FrequencyLimitPeriod | null;
};

export type UpdateUserProfileInput = Partial<{
  nickname: string;
  profile: string;
  icon: string;
  gameTypes: GameType[];
  beginnerOk: boolean;
  autoApprove: boolean;
  frequencyLimitCount: number | null;
  frequencyLimitPeriod: FrequencyLimitPeriod | null;
}>;
