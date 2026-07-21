import { z } from "zod";

/**
 * MeetFlowAuthStackのCognito PasswordPolicy（8文字以上、大文字・小文字・
 * 数字を含む）と一致させるバリデーションルール。SignUp・パスワードリセット・
 * パスワード変更の3画面で共通利用する。
 */
export const passwordSchema = z
  .string()
  .min(8, "8文字以上で入力してください")
  .regex(/[a-z]/, "小文字を含めてください")
  .regex(/[A-Z]/, "大文字を含めてください")
  .regex(/[0-9]/, "数字を含めてください");
