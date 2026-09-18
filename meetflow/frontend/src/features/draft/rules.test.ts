import { describe, expect, it } from "vitest";
import {
  consumesSurplus,
  mustPickFemale,
  pickBlockReason,
} from "@/features/draft/rules";
import type { DraftPlayer } from "@/features/draft/types";

/**
 * 指名ルールの表示側判定（docs/draft/DESIGN.md §4.3）。
 * 最終的な可否はサーバーが決めるが、同じ境界で判定していないと
 * 「押せるのにエラーになる」「押せないのに通るはず」がズレるため、
 * バックエンドの rules.py と同じケースを並べて固定する。
 */

const ROUNDS = 4;

function player(overrides: Partial<DraftPlayer> = {}): DraftPlayer {
  return {
    playerId: "p01",
    name: "選手01",
    kana: null,
    teamId: "team1",
    teamName: "チーム1",
    isFemale: false,
    takenByUserId: null,
    ...overrides,
  };
}

describe("mustPickFemale", () => {
  it.each([
    [1, false, false],
    [2, false, false],
    // 3巡目終了時点で女性ゼロ = 4巡目に入った時点で強制（§4.3(a)）
    [3, false, false],
    [4, false, true],
    // 既に確保していれば最終巡でも自由
    [4, true, false],
  ])("round=%i hasFemale=%s → %s", (round, hasFemale, expected) => {
    expect(mustPickFemale(round, ROUNDS, hasFemale)).toBe(expected);
  });
});

describe("consumesSurplus", () => {
  it("女性を持っている人の追加女流指名だけが余剰枠を消費する", () => {
    expect(consumesSurplus(true, true)).toBe(true);
    // 1人目の女性は必要指名であって余剰ではない
    expect(consumesSurplus(false, true)).toBe(false);
    expect(consumesSurplus(true, false)).toBe(false);
  });
});

describe("pickBlockReason", () => {
  const base = { round: 1, rounds: ROUNDS, hasFemale: false, femaleSurplusRemaining: 10 };

  it("空いている選手は指名できる", () => {
    expect(pickBlockReason(player(), base)).toBeNull();
  });

  it("確保済みの選手は指名できない", () => {
    expect(pickBlockReason(player({ takenByUserId: "u1" }), base)).toBe("TAKEN");
  });

  it("最終巡で女性ゼロなら男性を指名できない", () => {
    expect(pickBlockReason(player(), { ...base, round: 4 })).toBe("FEMALE_REQUIRED");
    expect(pickBlockReason(player({ isFemale: true }), { ...base, round: 4 })).toBeNull();
  });

  it("余剰枠ゼロなら追加の女流指名はできない", () => {
    const state = { ...base, hasFemale: true, femaleSurplusRemaining: 0 };
    expect(pickBlockReason(player({ isFemale: true }), state)).toBe("SURPLUS_EXHAUSTED");
    // 男性は余剰枠と無関係なので指名できる
    expect(pickBlockReason(player(), state)).toBeNull();
  });

  it("余剰枠ゼロでも1人目の女性は指名できる", () => {
    // ここを塞ぐと女性を持たない人が詰む（§4.3の不変条件）
    expect(
      pickBlockReason(player({ isFemale: true }), {
        ...base,
        hasFemale: false,
        femaleSurplusRemaining: 0,
      }),
    ).toBeNull();
  });

  it("確保済み判定は他の理由より優先される", () => {
    expect(
      pickBlockReason(player({ takenByUserId: "u1" }), { ...base, round: 4 }),
    ).toBe("TAKEN");
  });
});
