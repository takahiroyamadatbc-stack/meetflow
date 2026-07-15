/** MVPで扱うゲーム種別（麻雀ドメイン固定。backend/functions/result_lambda等で使用） */
export type GameType = "MAHJONG4" | "MAHJONG3";

export const GAME_TYPE_LABELS: Record<GameType, string> = {
  MAHJONG4: "四人麻雀",
  MAHJONG3: "三人麻雀",
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
};

export type UpdateUserProfileInput = Partial<{
  nickname: string;
  profile: string;
  icon: string;
  gameTypes: GameType[];
  beginnerOk: boolean;
}>;
