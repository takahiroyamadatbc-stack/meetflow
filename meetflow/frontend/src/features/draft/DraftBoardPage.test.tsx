import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { ErrorModalProvider } from "@/components/feedback/ErrorModalContext";
import { DraftBoardPage } from "@/features/draft/DraftBoardPage";
import { renderWithProviders, screen, waitFor } from "@/test/render";
import type { CurrentWave, DraftDetail, DraftStatus } from "@/features/draft/types";

vi.mock("@/features/draft/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/draft/api")>();
  return {
    ...actual,
    getDraft: vi.fn(),
    listDraftPlayers: vi.fn(),
    listLotteries: vi.fn(),
    startDraft: vi.fn(),
    revealWave: vi.fn(),
    runLottery: vi.fn(),
    advanceDraft: vi.fn(),
    submitProxyPick: vi.fn(),
  };
});
const authUserId = { current: "host" };
vi.mock("@/features/auth/useAuthUser", () => ({
  useAuthUser: () => ({ status: "authenticated", userId: authUserId.current }),
}));

const draftApi = await import("@/features/draft/api");

const DRAFT_ID = "draft-1";

function baseDraft(
  status: DraftStatus,
  wave: Partial<CurrentWave> | null,
  overrides: Partial<DraftDetail> = {},
): DraftDetail {
  return {
    draftId: DRAFT_ID,
    communityId: "community-1",
    name: "Mリーグドラフト2026-27",
    season: "2026-27",
    hostUserId: "host",
    status,
    round: 1,
    wave: 1,
    rounds: 4,
    version: 3,
    participantCount: 2,
    femalePlayerCount: 13,
    femaleSurplusRemaining: 11,
    regularSeasonEndDate: null,
    createdAt: "2026-09-18T00:00:00.000Z",
    updatedAt: "2026-09-18T00:00:00.000Z",
    participants: [
      { userId: "host", displayName: "主催者", playerCount: 0, femaleCount: 0 },
      { userId: "u1", displayName: "たろう", playerCount: 0, femaleCount: 0 },
    ],
    rosters: {},
    currentWave: wave
      ? {
          round: 1,
          wave: 1,
          expectedUserIds: ["host", "u1"],
          submittedUserIds: [],
          pendingUserIds: [],
          revealed: false,
          ...wave,
        }
      : null,
    ...overrides,
  };
}

function renderPage() {
  return renderWithProviders(
    <ErrorModalProvider>
      <MemoryRouter initialEntries={[`/drafts/${DRAFT_ID}/board`]}>
        <Routes>
          <Route path="/drafts/:draftId/board" element={<DraftBoardPage />} />
        </Routes>
      </MemoryRouter>
    </ErrorModalProvider>,
  );
}

function mockDraft(draft: DraftDetail) {
  vi.mocked(draftApi.getDraft).mockResolvedValue(draft);
  vi.mocked(draftApi.listDraftPlayers).mockResolvedValue([]);
  vi.mocked(draftApi.listLotteries).mockResolvedValue([]);
}

afterEach(() => {
  authUserId.current = "host";
  vi.clearAllMocks();
});

describe("DraftBoardPage の進行ボタン", () => {
  // DESIGN.md §4.6: 状態遷移は自動では起きない。
  // 「開示」→（必要なら）「抽選」→「次へ」を主催者が押して進める。

  it("SETUPでは開始ボタンを出す", async () => {
    mockDraft(baseDraft("SETUP", null));
    vi.mocked(draftApi.startDraft).mockResolvedValue(
      baseDraft("NOMINATING", {}) as never,
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "ドラフトを開始する" }));
    await waitFor(() => expect(draftApi.startDraft).toHaveBeenCalledWith(DRAFT_ID));
  });

  it("全員提出していれば開示できる", async () => {
    mockDraft(
      baseDraft("NOMINATING", { submittedUserIds: ["host", "u1"], pendingUserIds: [] }),
    );
    vi.mocked(draftApi.revealWave).mockResolvedValue({ lotteryRequired: false } as never);
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "指名を開示する" }));
    await waitFor(() => expect(draftApi.revealWave).toHaveBeenCalledWith(DRAFT_ID));
  });

  it("未提出者がいる間は開示できず、代理指名の導線を出す", async () => {
    // DESIGN.md §4.7: 制限時間は設けず、連絡がつかない人だけ代理指名する。
    mockDraft(
      baseDraft("NOMINATING", { submittedUserIds: ["host"], pendingUserIds: ["u1"] }),
    );
    renderPage();

    expect(await screen.findByRole("button", { name: "指名を開示する" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "たろうの代理で指名する" }),
    ).toBeInTheDocument();
  });

  it("重複があれば抽選ボタンを出し、次へは出さない", async () => {
    mockDraft(
      baseDraft("REVEAL", {
        revealed: true,
        lotteryRequired: true,
        submittedUserIds: ["host", "u1"],
        picks: [
          {
            userId: "host",
            playerId: "p01",
            playerName: "選手01",
            outcome: "PENDING",
            byProxy: false,
          },
          {
            userId: "u1",
            playerId: "p01",
            playerName: "選手01",
            outcome: "PENDING",
            byProxy: false,
          },
        ],
      }),
    );
    vi.mocked(draftApi.runLottery).mockResolvedValue({ loserUserIds: ["u1"] } as never);
    const user = userEvent.setup();
    renderPage();

    expect(screen.queryByRole("button", { name: "次へ進む" })).not.toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "抽選を実行する" }));
    await waitFor(() => expect(draftApi.runLottery).toHaveBeenCalledWith(DRAFT_ID));
  });

  it("重複が無ければ抽選を挟まず次へ進める", async () => {
    mockDraft(
      baseDraft("REVEAL", {
        revealed: true,
        lotteryRequired: false,
        submittedUserIds: ["host", "u1"],
        picks: [],
      }),
    );
    vi.mocked(draftApi.advanceDraft).mockResolvedValue(
      baseDraft("NOMINATING", {}) as never,
    );
    const user = userEvent.setup();
    renderPage();

    expect(screen.queryByRole("button", { name: "抽選を実行する" })).not.toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "次へ進む" }));
    await waitFor(() => expect(draftApi.advanceDraft).toHaveBeenCalledWith(DRAFT_ID));
  });

  it("抽選後は次へ進める", async () => {
    mockDraft(baseDraft("LOTTERY", { revealed: true, lotteryRequired: false, picks: [] }));
    vi.mocked(draftApi.advanceDraft).mockResolvedValue(
      baseDraft("NOMINATING", {}) as never,
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "次へ進む" }));
    await waitFor(() => expect(draftApi.advanceDraft).toHaveBeenCalledWith(DRAFT_ID));
  });

  it("主催者以外には進行ボタンを出さない", async () => {
    authUserId.current = "u1";
    mockDraft(
      baseDraft("NOMINATING", { submittedUserIds: ["host", "u1"], pendingUserIds: [] }),
    );
    renderPage();

    expect(await screen.findByText(/進行は主催者（主催者）が操作します/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "指名を開示する" })).not.toBeInTheDocument();
  });
});
