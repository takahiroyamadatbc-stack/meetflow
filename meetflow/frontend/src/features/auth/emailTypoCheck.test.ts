import { describe, expect, it } from "vitest";
import { suggestEmailCorrection } from "@/features/auth/emailTypoCheck";

describe("suggestEmailCorrection", () => {
  it("著名ドメインの典型的なタイポを検知して修正候補を返す", () => {
    expect(suggestEmailCorrection("taro@gmial.com")).toBe("taro@gmail.com");
  });

  it("TLD部分のタイポも検知する", () => {
    expect(suggestEmailCorrection("taro@gmail.co")).toBe("taro@gmail.com");
  });

  it("既に既知ドメインと一致する場合は提案しない", () => {
    expect(suggestEmailCorrection("taro@gmail.com")).toBeNull();
    expect(suggestEmailCorrection("taro@yahoo.co.jp")).toBeNull();
  });

  it("どの候補とも十分近くない場合は提案しない", () => {
    expect(suggestEmailCorrection("taro@example.com")).toBeNull();
    expect(suggestEmailCorrection("taro@my-company.co.jp")).toBeNull();
  });

  it("@が無い、またはドメイン部分が空の場合は提案しない", () => {
    expect(suggestEmailCorrection("taro")).toBeNull();
    expect(suggestEmailCorrection("taro@")).toBeNull();
  });

  it("大文字小文字を無視して判定する", () => {
    expect(suggestEmailCorrection("Taro@GMIAL.COM")).toBe("Taro@gmail.com");
  });

  it("短いドメイン(au.com)は同じ文字数かつ編集距離1のときのみ提案する", () => {
    expect(suggestEmailCorrection("taro@au.co")).toBeNull(); // 文字数が異なる
    expect(suggestEmailCorrection("taro@av.com")).toBe("taro@au.com"); // 同じ文字数・距離1
  });

  it("ローカル部はそのままに、ドメイン部分だけ修正候補に差し替える", () => {
    expect(suggestEmailCorrection("taro.yamada+test@gmial.com")).toBe(
      "taro.yamada+test@gmail.com",
    );
  });
});
