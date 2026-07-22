import { describe, expect, it } from "vitest";
import {
  aggregateSessionTotals,
  computeLiveResults,
  expectedPlayerCount,
  formatScoreMismatch,
  scoreMismatchDiff,
  sortByTieOrder,
} from "@/features/result/calc";
import type { GameSessionDetail } from "@/features/result/types";

describe("computeLiveResults", () => {
  // result_lambda/handlers/results.py の_compute_results()と同じ計算式であることの確認。
  const startingPoints = 25000;
  const returnPoints = 30000;
  const umaByRank = [15, 5, -5, -15];

  it("AUTO時、配給原点・返し点・ウマ・オカから合計0になるよう精算する", () => {
    const rows = [
      { userId: "a", nickname: "A", score: 35000 },
      { userId: "b", nickname: "B", score: 28000 },
      { userId: "c", nickname: "C", score: 22000 },
      { userId: "d", nickname: "D", score: 15000 },
    ];

    const result = computeLiveResults(rows, "AUTO", startingPoints, returnPoints, umaByRank);

    expect(result.map((r) => r.rankPoints)).toEqual([40, 3, -13, -30]);
    expect(result.map((r) => r.rank)).toEqual([1, 2, 3, 4]);
    expect(result.reduce((sum, r) => sum + r.rankPoints, 0)).toBe(0);
  });

  it("MANUAL時はrankPointsを計算せず常に0にする", () => {
    const rows = [
      { userId: "a", nickname: "A", score: 35000 },
      { userId: "b", nickname: "B", score: 15000 },
    ];

    const result = computeLiveResults(rows, "MANUAL", startingPoints, returnPoints, umaByRank);

    expect(result.every((r) => r.rankPoints === 0)).toBe(true);
    expect(result.map((r) => r.rank)).toEqual([1, 2]);
  });

  it("同点の場合はtieOrderで指定した優先順位でランクを決める", () => {
    const rows = [
      { userId: "a", nickname: "A", score: 30000 },
      { userId: "b", nickname: "B", score: 30000 },
      { userId: "c", nickname: "C", score: 25000 },
      { userId: "d", nickname: "D", score: 15000 },
    ];

    const result = computeLiveResults(
      rows,
      "AUTO",
      startingPoints,
      returnPoints,
      umaByRank,
      ["b", "a"],
    );

    expect(result.map((r) => r.userId)).toEqual(["b", "a", "c", "d"]);
    expect(result.map((r) => r.rank)).toEqual([1, 2, 3, 4]);
  });

  it("tieOrderに無いuserIdは最後尾扱いになる", () => {
    const rows = [
      { userId: "a", nickname: "A", score: 30000 },
      { userId: "b", nickname: "B", score: 30000 },
    ];

    const result = computeLiveResults(
      rows,
      "AUTO",
      startingPoints,
      returnPoints,
      umaByRank,
      ["b"],
    );

    expect(result.map((r) => r.userId)).toEqual(["b", "a"]);
  });

  it("boxUnderSettlement=falseの場合、マイナス点は0点として基礎点を計算する（トビ判定は生の点数のまま加減算）", () => {
    const rows = [
      { userId: "a", nickname: "A", score: 40000 },
      { userId: "b", nickname: "B", score: 30000 },
      { userId: "c", nickname: "C", score: 20000 },
      { userId: "d", nickname: "D", score: -10000 },
    ];
    const tobiAssignments = [{ bustedUserId: "d", receiverUserId: "a" }];

    const withoutBoxUnder = computeLiveResults(
      rows,
      "AUTO",
      startingPoints,
      returnPoints,
      umaByRank,
      undefined,
      { boxUnderSettlement: false, tobiPoints: 10, tobiAssignments },
    );
    const withBoxUnder = computeLiveResults(
      rows,
      "AUTO",
      startingPoints,
      returnPoints,
      umaByRank,
      undefined,
      { boxUnderSettlement: true, tobiPoints: 10, tobiAssignments },
    );

    const dWithout = withoutBoxUnder.find((r) => r.userId === "d")!;
    const dWith = withBoxUnder.find((r) => r.userId === "d")!;
    // boxUnderSettlement=falseだとマイナス点が0点扱いになる分、基礎点の下振れが無くなる
    expect(dWithout.rankPoints).toBe(-55);
    expect(dWith.rankPoints).toBe(-65);

    const aResult = withoutBoxUnder.find((r) => r.userId === "a")!;
    // 受取人側の飛び賞加点はboxUnderSettlementの影響を受けない
    expect(aResult.rankPoints).toBe(55);
  });
});

describe("sortByTieOrder", () => {
  it("同点者のみtieOrderの順序で並び替え、点数降順自体は変えない", () => {
    const items = [
      { userId: "a", score: 30000 },
      { userId: "b", score: 30000 },
      { userId: "c", score: 40000 },
    ];

    const result = sortByTieOrder(items, ["b", "a"]);

    expect(result.map((i) => i.userId)).toEqual(["c", "b", "a"]);
  });
});

describe("scoreMismatchDiff", () => {
  it("合計が配給原点×人数と一致する場合は0を返す", () => {
    const rows = [{ score: 25000 }, { score: 25000 }, { score: 25000 }, { score: 25000 }];
    expect(scoreMismatchDiff(rows, 25000)).toBe(0);
  });

  it("超過分は正の値を返す", () => {
    const rows = [{ score: 26000 }, { score: 25000 }];
    expect(scoreMismatchDiff(rows, 25000)).toBe(1000);
  });

  it("不足分は負の値を返す", () => {
    const rows = [{ score: 24000 }, { score: 25000 }];
    expect(scoreMismatchDiff(rows, 25000)).toBe(-1000);
  });
});

describe("formatScoreMismatch", () => {
  it("正の差分は「多い」と表示する", () => {
    expect(formatScoreMismatch(20)).toBe("20点多い");
  });

  it("負の差分は絶対値を「足りない」と表示する", () => {
    expect(formatScoreMismatch(-30)).toBe("30点足りない");
  });
});

describe("expectedPlayerCount", () => {
  it("MAHJONG3は3人", () => {
    expect(expectedPlayerCount("MAHJONG3")).toBe(3);
  });

  it("MAHJONG4は4人", () => {
    expect(expectedPlayerCount("MAHJONG4")).toBe(4);
  });
});

describe("aggregateSessionTotals", () => {
  it("複数半荘のポイント・チップ・平均着順をユーザー単位で合算する", () => {
    const sessions: GameSessionDetail[] = [
      {
        eventId: "event-1",
        sessionNo: "1",
        gameType: "MAHJONG4",
        calcMode: "AUTO",
        results: [
          { userId: "a", rank: 1, score: 35000, rankPoints: 40 },
          { userId: "b", rank: 2, score: 28000, rankPoints: 3 },
        ],
        chips: [{ userId: "a", chipCount: 2 }],
      },
      {
        eventId: "event-1",
        sessionNo: "2",
        gameType: "MAHJONG4",
        calcMode: "AUTO",
        results: [
          { userId: "a", rank: 3, score: 20000, rankPoints: -13.3 },
          { userId: "b", rank: 1, score: 40000, rankPoints: 45 },
        ],
        chips: [{ userId: "b", chipCount: 1 }],
      },
    ];
    const nicknameByUserId = new Map([
      ["a", "たろう"],
      ["b", "はなこ"],
    ]);

    const result = aggregateSessionTotals(sessions, nicknameByUserId);

    // 合計ポイントが大きい順（bが上位）
    expect(result.map((r) => r.userId)).toEqual(["b", "a"]);

    const b = result.find((r) => r.userId === "b")!;
    expect(b.nickname).toBe("はなこ");
    expect(b.games).toBe(2);
    expect(b.totalRankPoints).toBe(48);
    expect(b.totalChips).toBe(1);
    expect(b.averageRank).toBe(1.5);

    const a = result.find((r) => r.userId === "a")!;
    expect(a.totalRankPoints).toBe(26.7);
    expect(a.totalChips).toBe(2);
    expect(a.averageRank).toBe(2);
  });

  it("nicknameByUserIdに無いuserIdはuserIdをそのまま表示名にする", () => {
    const sessions: GameSessionDetail[] = [
      {
        eventId: "event-1",
        sessionNo: "1",
        gameType: "MAHJONG4",
        calcMode: "MANUAL",
        results: [{ userId: "unknown-user", rank: 1, score: 25000, rankPoints: 0 }],
        chips: [],
      },
    ];

    const result = aggregateSessionTotals(sessions, new Map());

    expect(result[0].nickname).toBe("unknown-user");
  });

  it("対局が0件のユーザーは扱わない（chipsのみのエントリでもgames起点にはならない）", () => {
    const sessions: GameSessionDetail[] = [
      {
        eventId: "event-1",
        sessionNo: "1",
        gameType: "MAHJONG4",
        calcMode: "MANUAL",
        results: [],
        chips: [{ userId: "a", chipCount: 3 }],
      },
    ];

    const result = aggregateSessionTotals(sessions, new Map());

    expect(result).toHaveLength(1);
    expect(result[0].games).toBe(0);
    expect(result[0].totalChips).toBe(3);
    expect(result[0].averageRank).toBe(0);
  });
});
