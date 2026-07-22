import { describe, expect, it } from "vitest";
import { getErrorDisplay } from "./errors";

describe("getErrorDisplay", () => {
  it("インライン表示のコードはinlineを返す", () => {
    expect(getErrorDisplay("INVALID_TIME_RANGE")).toBe("inline");
  });

  it("モーダル表示のコードはmodalを返す", () => {
    expect(getErrorDisplay("PARTICIPANT_SCHEDULE_CONFLICT")).toBe("modal");
  });

  it("トースト表示のコードはtoastを返す", () => {
    expect(getErrorDisplay("EVENT_ALREADY_CONFIRMED")).toBe("toast");
  });

  it("末尾がNOT_FOUNDのコードはemptyを返す", () => {
    expect(getErrorDisplay("COMMUNITY_NOT_FOUND")).toBe("empty");
  });

  it("一覧に無い未知のコードはtoast（デフォルト受け皿）を返す", () => {
    expect(getErrorDisplay("SOME_UNKNOWN_CODE")).toBe("toast");
  });
});
