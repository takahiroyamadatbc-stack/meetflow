import { describe, expect, it } from "vitest";
import { passwordSchema } from "@/features/auth/passwordSchema";

describe("passwordSchema", () => {
  it("大文字・小文字・数字を含む8文字以上のパスワードは検証を通過する", () => {
    const result = passwordSchema.safeParse("Passw0rd");
    expect(result.success).toBe(true);
  });

  it("7文字以下は「8文字以上で入力してください」で失敗する", () => {
    const result = passwordSchema.safeParse("Pas0rd");
    expect(result.success).toBe(false);
    expect(result.error?.issues.map((i) => i.message)).toContain("8文字以上で入力してください");
  });

  it("小文字が無い場合は「小文字を含めてください」で失敗する", () => {
    const result = passwordSchema.safeParse("PASSW0RD");
    expect(result.success).toBe(false);
    expect(result.error?.issues.map((i) => i.message)).toContain("小文字を含めてください");
  });

  it("大文字が無い場合は「大文字を含めてください」で失敗する", () => {
    const result = passwordSchema.safeParse("passw0rd");
    expect(result.success).toBe(false);
    expect(result.error?.issues.map((i) => i.message)).toContain("大文字を含めてください");
  });

  it("数字が無い場合は「数字を含めてください」で失敗する", () => {
    const result = passwordSchema.safeParse("Password");
    expect(result.success).toBe(false);
    expect(result.error?.issues.map((i) => i.message)).toContain("数字を含めてください");
  });

  it("複数条件を同時に満たさない場合はすべての違反メッセージを返す", () => {
    const result = passwordSchema.safeParse("short");
    expect(result.success).toBe(false);
    const messages = result.error?.issues.map((i) => i.message) ?? [];
    expect(messages).toContain("8文字以上で入力してください");
    expect(messages).toContain("大文字を含めてください");
    expect(messages).toContain("数字を含めてください");
  });
});
