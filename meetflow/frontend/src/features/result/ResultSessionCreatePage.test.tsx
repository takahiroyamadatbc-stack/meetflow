import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { ErrorModalProvider } from "@/components/feedback/ErrorModalContext";
import { ResultSessionCreatePage } from "@/features/result/ResultSessionCreatePage";
import { renderWithProviders, screen, waitFor, within } from "@/test/render";
import type { EventDetail, Participant } from "@/features/event/types";
import type { CommunityDetail } from "@/features/community/types";
import type { GameSessionDetail, LastGameSettings } from "@/features/result/types";

vi.mock("@/features/event/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/event/api")>();
  return { ...actual, getEvent: vi.fn(), listParticipants: vi.fn() };
});
vi.mock("@/features/community/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/community/api")>();
  return { ...actual, getCommunity: vi.fn() };
});
vi.mock("@/features/result/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/result/api")>();
  return {
    ...actual,
    createSession: vi.fn(),
    updateSession: vi.fn(),
    deleteSession: vi.fn(),
    listEventSessions: vi.fn(),
    getLastGameSettings: vi.fn(),
  };
});

const eventApi = await import("@/features/event/api");
const communityApi = await import("@/features/community/api");
const resultApi = await import("@/features/result/api");

const EVENT_ID = "event-1";
const COMMUNITY_ID = "community-1";

function baseEvent(): EventDetail {
  return {
    eventId: EVENT_ID,
    communityId: COMMUNITY_ID,
    templateId: "template-1",
    candidateId: "candidate-1",
    status: "CONFIRMED",
    startTime: "2026-08-01T10:00:00+09:00",
    endTime: "2026-08-01T13:00:00+09:00",
    location: null,
    locationNote: "",
    memo: "",
    createdAt: "2026-07-01T00:00:00+09:00",
  };
}

function baseCommunity(role: CommunityDetail["role"] = "OWNER"): CommunityDetail {
  return {
    communityId: COMMUNITY_ID,
    name: "テストコミュニティ",
    description: "",
    genre: "麻雀",
    memberApprovalRequired: false,
    themeColor: null,
    icon: null,
    role,
    pendingRequestCount: 0,
    rankingDefaultGameType: "MAHJONG4",
    rankingDefaultPeriodType: "ALL_TIME",
    rankingDefaultMetric: "AVERAGE_RANK",
    rankingDefaultMinGames: 0,
  };
}

const FOUR_PARTICIPANTS: Participant[] = [
  { userId: "u1", nickname: "たろう", status: "CONFIRMED" },
  { userId: "u2", nickname: "はなこ", status: "CONFIRMED" },
  { userId: "u3", nickname: "じろう", status: "CONFIRMED" },
  { userId: "u4", nickname: "さぶろう", status: "CONFIRMED" },
];

const NOT_FOUND_SETTINGS: LastGameSettings = { found: false };

function setupDefaultMocks() {
  vi.mocked(eventApi.getEvent).mockResolvedValue(baseEvent());
  vi.mocked(communityApi.getCommunity).mockResolvedValue(baseCommunity());
  vi.mocked(eventApi.listParticipants).mockResolvedValue(FOUR_PARTICIPANTS);
  vi.mocked(resultApi.listEventSessions).mockResolvedValue([]);
  vi.mocked(resultApi.getLastGameSettings).mockResolvedValue(NOT_FOUND_SETTINGS);
}

function renderNewSessionPage() {
  return renderWithProviders(
    <MemoryRouter initialEntries={[`/events/${EVENT_ID}/sessions/new`]}>
      <ErrorModalProvider>
        <Routes>
          <Route path="/events/:eventId/sessions/new" element={<ResultSessionCreatePage />} />
          <Route path="/events/:eventId" element={<p>イベント詳細画面</p>} />
        </Routes>
      </ErrorModalProvider>
    </MemoryRouter>,
  );
}

function renderEditSessionPage(sessionNo: string) {
  return renderWithProviders(
    <MemoryRouter initialEntries={[`/events/${EVENT_ID}/sessions/${sessionNo}/edit`]}>
      <ErrorModalProvider>
        <Routes>
          <Route
            path="/events/:eventId/sessions/:sessionNo/edit"
            element={<ResultSessionCreatePage />}
          />
          <Route path="/events/:eventId" element={<p>イベント詳細画面</p>} />
        </Routes>
      </ErrorModalProvider>
    </MemoryRouter>,
  );
}

function scoreInput(container: HTMLElement, index: number): HTMLInputElement {
  return container.querySelector(`input[name="rows.${index}.score"]`) as HTMLInputElement;
}

afterEach(() => {
  vi.resetAllMocks();
});

describe("ResultSessionCreatePage（トップレベルの分岐）", () => {
  it("読み込み中はスケルトンを表示する", () => {
    setupDefaultMocks();
    vi.mocked(eventApi.getEvent).mockReturnValue(new Promise(() => {}));

    const { container } = renderNewSessionPage();

    expect(container.querySelector('[data-slot="skeleton"]')).toBeTruthy();
  });

  it("情報の取得に失敗した場合は空状態を表示する", async () => {
    setupDefaultMocks();
    vi.mocked(communityApi.getCommunity).mockRejectedValue(new Error("failed"));

    renderNewSessionPage();

    expect(await screen.findByText("情報の取得に失敗しました")).toBeInTheDocument();
  });

  it("対局に参加しているメンバーがいない場合は空状態を表示する", async () => {
    setupDefaultMocks();
    vi.mocked(eventApi.listParticipants).mockResolvedValue(
      FOUR_PARTICIPANTS.map((p) => ({ ...p, status: "CANCELLED" })),
    );

    renderNewSessionPage();

    expect(
      await screen.findByText("対局に参加しているメンバーがいません"),
    ).toBeInTheDocument();
  });

  it("編集対象の対局が見つからない場合は空状態を表示する", async () => {
    setupDefaultMocks();
    vi.mocked(resultApi.listEventSessions).mockResolvedValue([]);

    renderEditSessionPage("999");

    expect(
      await screen.findByText("指定した対局が見つかりません"),
    ).toBeInTheDocument();
  });
});

describe("HanchanEntryForm（新規半荘登録）", () => {
  it("保存済み設定が無い場合、MAHJONG4のデフォルト値（配給原点25000・返し点30000）で初期化する", async () => {
    setupDefaultMocks();

    const { container } = renderNewSessionPage();

    await screen.findByRole("button", { name: "この半荘を登録する" });
    expect(container.querySelector('input[name="startingPoints"]')).toHaveValue(25000);
    expect(container.querySelector('input[name="returnPoints"]')).toHaveValue(30000);
  });

  it("保存済み設定がある場合はそこから初期化する", async () => {
    setupDefaultMocks();
    vi.mocked(resultApi.getLastGameSettings).mockResolvedValue({
      found: true,
      gameType: "MAHJONG4",
      calcMode: "AUTO",
      startingPoints: 27000,
      returnPoints: 32000,
      umaByRank: [20, 10, -10, -20],
      boxUnderSettlement: true,
      tobiPoints: 5,
    });

    const { container } = renderNewSessionPage();

    await screen.findByRole("button", { name: "この半荘を登録する" });
    expect(container.querySelector('input[name="startingPoints"]')).toHaveValue(27000);
    expect(container.querySelector('input[name="returnPoints"]')).toHaveValue(32000);
  });

  it("保存済み設定が無い場合、ゲーム種別を変更すると対象種別のデフォルト配給原点・返し点に更新する（Issue #64）", async () => {
    const user = userEvent.setup();
    setupDefaultMocks();

    const { container } = renderNewSessionPage();
    await screen.findByRole("button", { name: "この半荘を登録する" });

    await user.click(screen.getByRole("button", { name: "三人麻雀" }));

    expect(container.querySelector('input[name="startingPoints"]')).toHaveValue(35000);
    expect(container.querySelector('input[name="returnPoints"]')).toHaveValue(40000);
  });

  it("保存済み設定がある場合、ゲーム種別を変更しても配給原点・返し点は上書きしない", async () => {
    const user = userEvent.setup();
    setupDefaultMocks();
    vi.mocked(resultApi.getLastGameSettings).mockResolvedValue({
      found: true,
      gameType: "MAHJONG4",
      calcMode: "AUTO",
      startingPoints: 27000,
      returnPoints: 32000,
      umaByRank: [0, 0, 0, 0],
      boxUnderSettlement: true,
      tobiPoints: 0,
    });

    const { container } = renderNewSessionPage();
    await screen.findByRole("button", { name: "この半荘を登録する" });

    await user.click(screen.getByRole("button", { name: "三人麻雀" }));

    expect(container.querySelector('input[name="startingPoints"]')).toHaveValue(27000);
    expect(container.querySelector('input[name="returnPoints"]')).toHaveValue(32000);
  });

  it("手動計算から自動計算に切り替えると、参加中の点数欄に配給原点が入る", async () => {
    const user = userEvent.setup();
    setupDefaultMocks();

    const { container } = renderNewSessionPage();
    await screen.findByRole("button", { name: "この半荘を登録する" });

    // MANUALに切り替えても既存の点数はクリアされない（クリアはAUTO移行時のみの挙動）
    await user.click(screen.getByRole("button", { name: "手動計算（点数のみ）" }));
    const score0 = scoreInput(container, 0);
    await user.clear(score0);
    expect(score0).toHaveValue(null);

    await user.click(screen.getByRole("button", { name: "自動計算（ウマ・オカ）" }));
    expect(scoreInput(container, 0)).toHaveValue(25000);
    expect(scoreInput(container, 3)).toHaveValue(25000);
  });

  it("配給原点を変更すると、変更前の配給原点のままだった点数欄だけ新しい値に追従する（Issue #65）", async () => {
    const user = userEvent.setup();
    setupDefaultMocks();

    const { container } = renderNewSessionPage();
    await screen.findByRole("button", { name: "この半荘を登録する" });
    // デフォルトで4人全員AUTO・25000で埋まっている状態から、1人だけ個別に点数を書き換える
    const score0 = scoreInput(container, 0);
    await user.clear(score0);
    await user.type(score0, "40000");

    const startingPointsInput = container.querySelector(
      'input[name="startingPoints"]',
    ) as HTMLInputElement;
    await user.clear(startingPointsInput);
    await user.type(startingPointsInput, "20000");

    // 個別入力済み(40000)の欄は上書きされず、他の欄(25000のまま)は追従する
    expect(score0).toHaveValue(40000);
    expect(scoreInput(container, 1)).toHaveValue(20000);
    expect(scoreInput(container, 2)).toHaveValue(20000);
    expect(scoreInput(container, 3)).toHaveValue(20000);
  });

  it("参加者が対象人数を超える場合、対象人数に達すると追加でチェックできない", async () => {
    const user = userEvent.setup();
    setupDefaultMocks();
    vi.mocked(eventApi.listParticipants).mockResolvedValue([
      ...FOUR_PARTICIPANTS,
      { userId: "u5", nickname: "ごろう", status: "CONFIRMED" },
    ]);

    renderNewSessionPage();
    await screen.findByRole("button", { name: "この半荘を登録する" });

    const checkboxes = screen.getAllByRole("checkbox");
    // 先頭4人(u1-u4)がデフォルトで選択済み、5人目(u5)はまだ未選択
    expect(checkboxes).toHaveLength(5);
    expect(checkboxes[4]).not.toBeChecked();
    expect(checkboxes[4]).toHaveAttribute("aria-disabled", "true");

    // 1人分のチェックを外せば5人目を選べるようになる
    await user.click(checkboxes[0]);
    expect(checkboxes[4]).not.toHaveAttribute("aria-disabled", "true");
  });

  it("参加者が未選択のまま送信するとエラートーストを出し、APIは呼ばない", async () => {
    const user = userEvent.setup();
    setupDefaultMocks();
    // 参加者選択チェックボックスは対象人数を超える場合のみ表示されるため、5人構成で検証する
    vi.mocked(eventApi.listParticipants).mockResolvedValue([
      ...FOUR_PARTICIPANTS,
      { userId: "u5", nickname: "ごろう", status: "CONFIRMED" },
    ]);

    renderNewSessionPage();
    const checkboxes = await screen.findAllByRole("checkbox");
    // 先頭4人(u1-u4)がデフォルト選択済みなので、全員分のチェックを外す
    // (Base UIのCheckboxはrole="checkbox"のspanでネイティブinputではないため、
    // 選択状態はDOMプロパティ.checkedではなくaria-checked属性で判定する)
    for (const checkbox of checkboxes) {
      if (checkbox.getAttribute("aria-checked") === "true") {
        await user.click(checkbox);
      }
    }
    await user.click(screen.getByRole("button", { name: "この半荘を登録する" }));

    expect(resultApi.createSession).not.toHaveBeenCalled();
  });

  it("点数合計が配給原点×人数と一致しない場合は確認ダイアログを出し、確定すると登録する", async () => {
    const user = userEvent.setup();
    setupDefaultMocks();
    vi.mocked(resultApi.createSession).mockResolvedValue({} as GameSessionDetail);

    const { container } = renderNewSessionPage();
    await screen.findByRole("button", { name: "この半荘を登録する" });

    const score0 = scoreInput(container, 0);
    await user.clear(score0);
    await user.type(score0, "40000");

    await user.click(screen.getByRole("button", { name: "この半荘を登録する" }));

    const dialog = await screen.findByRole("alertdialog");
    expect(
      within(dialog).getByText("点数の合計が配給原点と一致していません"),
    ).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "登録する" }));

    await waitFor(() => expect(resultApi.createSession).toHaveBeenCalled());
  });

  it("登録に成功すると、ゲーム種別・計算方法・配給原点は維持したまま点数欄がリセットされる", async () => {
    const user = userEvent.setup();
    setupDefaultMocks();
    vi.mocked(resultApi.createSession).mockResolvedValue({} as GameSessionDetail);

    const { container } = renderNewSessionPage();
    await screen.findByRole("button", { name: "この半荘を登録する" });

    await user.click(screen.getByRole("button", { name: "この半荘を登録する" }));

    await waitFor(() => expect(resultApi.createSession).toHaveBeenCalled());
    expect(container.querySelector('input[name="startingPoints"]')).toHaveValue(25000);
    expect(scoreInput(container, 0)).toHaveValue(25000);
  });
});

describe("SessionEditForm（登録済み半荘の編集）", () => {
  function existingSession(): GameSessionDetail {
    return {
      eventId: EVENT_ID,
      sessionNo: "1",
      gameType: "MAHJONG4",
      calcMode: "AUTO",
      startingPoints: 25000,
      returnPoints: 30000,
      umaByRank: [15, 5, -5, -15],
      boxUnderSettlement: true,
      tobiPoints: 0,
      results: [
        { userId: "u1", rank: 1, score: 40000, rankPoints: 40 },
        { userId: "u2", rank: 2, score: 25000, rankPoints: 0 },
        { userId: "u3", rank: 3, score: 20000, rankPoints: -10 },
        { userId: "u4", rank: 4, score: 15000, rankPoints: -30 },
      ],
      chips: [{ userId: "u1", chipCount: 2 }],
    };
  }

  it("既存の登録内容から初期値を復元する", async () => {
    setupDefaultMocks();
    vi.mocked(resultApi.listEventSessions).mockResolvedValue([existingSession()]);

    const { container } = renderEditSessionPage("1");

    await screen.findByRole("button", { name: "更新する" });
    expect(container.querySelector('input[name="startingPoints"]')).toHaveValue(25000);
    expect(container.querySelector('input[name="rows.0.score"]')).toHaveValue(40000);
    expect(container.querySelector('input[name="rows.0.chipCount"]')).toHaveValue(2);
  });

  it("管理者でない場合は更新ボタンを表示せず、案内文を表示する", async () => {
    setupDefaultMocks();
    vi.mocked(communityApi.getCommunity).mockResolvedValue(baseCommunity("MEMBER"));
    vi.mocked(resultApi.listEventSessions).mockResolvedValue([existingSession()]);

    renderEditSessionPage("1");

    expect(
      await screen.findByText("入力内容はこの場で確認できますが、登録・編集は管理者のみ実行できます。"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "更新する" })).not.toBeInTheDocument();
  });

  it("更新に成功するとイベント詳細画面へ遷移する", async () => {
    const user = userEvent.setup();
    setupDefaultMocks();
    vi.mocked(resultApi.listEventSessions).mockResolvedValue([existingSession()]);
    vi.mocked(resultApi.updateSession).mockResolvedValue({} as GameSessionDetail);

    renderEditSessionPage("1");

    await user.click(await screen.findByRole("button", { name: "更新する" }));

    await waitFor(() => expect(screen.getByText("イベント詳細画面")).toBeInTheDocument());
  });

  it("点数合計が不一致の場合は確認ダイアログを出す", async () => {
    const user = userEvent.setup();
    setupDefaultMocks();
    vi.mocked(resultApi.listEventSessions).mockResolvedValue([existingSession()]);
    vi.mocked(resultApi.updateSession).mockResolvedValue({} as GameSessionDetail);

    const { container } = renderEditSessionPage("1");
    await screen.findByRole("button", { name: "更新する" });
    // 既存データ(合計100000=配給原点25000×4人)を意図的に不一致にする
    const score0 = container.querySelector('input[name="rows.0.score"]') as HTMLInputElement;
    await user.clear(score0);
    await user.type(score0, "50000");

    await user.click(screen.getByRole("button", { name: "更新する" }));

    const dialog = await screen.findByRole("alertdialog");
    expect(
      within(dialog).getByText("点数の合計が配給原点と一致していません"),
    ).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "更新する" }));

    await waitFor(() => expect(resultApi.updateSession).toHaveBeenCalled());
  });
});
