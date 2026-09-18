import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { ErrorModalProvider } from "@/components/feedback/ErrorModalContext";
import { DraftRoomPage } from "@/features/draft/DraftRoomPage";
import { renderWithProviders, screen, waitFor } from "@/test/render";
import type { DraftDetail, DraftPlayer } from "@/features/draft/types";

vi.mock("@/features/draft/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/draft/api")>();
  return { ...actual, getDraft: vi.fn(), listDraftPlayers: vi.fn(), submitPick: vi.fn() };
});
vi.mock("@/features/auth/useAuthUser", () => ({
  useAuthUser: () => ({ status: "authenticated", userId: "me" }),
}));

const draftApi = await import("@/features/draft/api");

const DRAFT_ID = "draft-1";

function baseDraft(overrides: Partial<DraftDetail> = {}): DraftDetail {
  return {
    draftId: DRAFT_ID,
    communityId: "community-1",
    name: "Mリーグドラフト2026-27",
    season: "2026-27",
    hostUserId: "me",
    status: "NOMINATING",
    round: 1,
    wave: 1,
    rounds: 4,
    version: 2,
    participantCount: 3,
    femalePlayerCount: 13,
    femaleSurplusRemaining: 10,
    regularSeasonEndDate: null,
    createdAt: "2026-09-18T00:00:00.000Z",
    updatedAt: "2026-09-18T00:00:00.000Z",
    participants: [
      { userId: "me", displayName: "わたし", playerCount: 0, femaleCount: 0 },
      { userId: "u1", displayName: "たろう", playerCount: 0, femaleCount: 0 },
      { userId: "u2", displayName: "はなこ", playerCount: 0, femaleCount: 0 },
    ],
    rosters: {},
    currentWave: {
      round: 1,
      wave: 1,
      expectedUserIds: ["me", "u1", "u2"],
      submittedUserIds: [],
      pendingUserIds: ["me", "u1", "u2"],
      revealed: false,
      myPick: null,
    },
    ...overrides,
  };
}

function players(): DraftPlayer[] {
  return [
    {
      playerId: "p01",
      name: "女流選手",
      kana: null,
      teamId: "t1",
      teamName: "チーム1",
      isFemale: true,
      takenByUserId: null,
    },
    {
      playerId: "p20",
      name: "空いてる選手",
      kana: null,
      teamId: "t1",
      teamName: "チーム1",
      isFemale: false,
      takenByUserId: null,
    },
    {
      playerId: "p21",
      name: "取られた選手",
      kana: null,
      teamId: "t1",
      teamName: "チーム1",
      isFemale: false,
      takenByUserId: "u1",
    },
  ];
}

function renderPage() {
  return renderWithProviders(
    <ErrorModalProvider>
      <MemoryRouter initialEntries={[`/drafts/${DRAFT_ID}`]}>
        <Routes>
          <Route path="/drafts/:draftId" element={<DraftRoomPage />} />
        </Routes>
      </MemoryRouter>
    </ErrorModalProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("DraftRoomPage", () => {
  it("自分の指名待ちなら選手を選んで指名できる", async () => {
    vi.mocked(draftApi.getDraft).mockResolvedValue(baseDraft());
    vi.mocked(draftApi.listDraftPlayers).mockResolvedValue(players());
    vi.mocked(draftApi.submitPick).mockResolvedValue({
      playerId: "p20",
      playerName: "空いてる選手",
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: /空いてる選手/ }));
    await user.click(screen.getByRole("button", { name: "この選手を指名する" }));

    await waitFor(() =>
      expect(draftApi.submitPick).toHaveBeenCalledWith(DRAFT_ID, "p20"),
    );
  });

  it("確保済みの選手は指名者名付きで無効化される", async () => {
    vi.mocked(draftApi.getDraft).mockResolvedValue(baseDraft());
    vi.mocked(draftApi.listDraftPlayers).mockResolvedValue(players());
    renderPage();

    const taken = await screen.findByRole("button", { name: /取られた選手/ });
    expect(taken).toBeDisabled();
    expect(taken).toHaveTextContent("たろうが指名済み");
  });

  it("開示前は提出状況だけ見え、他人の指名内容は出ない", async () => {
    // DESIGN.md §4.6: 開示前は主催者画面にも「何人提出完了」しか出さない。
    vi.mocked(draftApi.getDraft).mockResolvedValue(
      baseDraft({
        currentWave: {
          round: 1,
          wave: 1,
          expectedUserIds: ["me", "u1", "u2"],
          submittedUserIds: ["u1"],
          pendingUserIds: ["me", "u2"],
          revealed: false,
          myPick: null,
        },
      }),
    );
    vi.mocked(draftApi.listDraftPlayers).mockResolvedValue(players());
    renderPage();

    expect(await screen.findByText("1 / 3人 提出完了")).toBeInTheDocument();
    expect(screen.getByText(/未提出: わたし、はなこ/)).toBeInTheDocument();
  });

  it("提出済みなら指名UIを出さず待機メッセージを出す", async () => {
    vi.mocked(draftApi.getDraft).mockResolvedValue(
      baseDraft({
        currentWave: {
          round: 1,
          wave: 1,
          expectedUserIds: ["me", "u1", "u2"],
          submittedUserIds: ["me"],
          pendingUserIds: ["u1", "u2"],
          revealed: false,
          myPick: { playerId: "p20", playerName: "空いてる選手" },
        },
      }),
    );
    vi.mocked(draftApi.listDraftPlayers).mockResolvedValue(players());
    renderPage();

    expect(
      await screen.findByText("指名を提出しました。全員の提出を待っています。"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "この選手を指名する" }),
    ).not.toBeInTheDocument();
  });

  it("最終巡で女性を持っていない場合は男性選手を選べない", async () => {
    // DESIGN.md §4.3(a) 動的強制。サーバーも同じ判定で弾くが、
    // 押してからエラーになる前に理由を出す。
    vi.mocked(draftApi.getDraft).mockResolvedValue(
      baseDraft({
        round: 4,
        participants: [
          { userId: "me", displayName: "わたし", playerCount: 3, femaleCount: 0 },
          { userId: "u1", displayName: "たろう", playerCount: 3, femaleCount: 1 },
          { userId: "u2", displayName: "はなこ", playerCount: 3, femaleCount: 1 },
        ],
        currentWave: {
          round: 4,
          wave: 1,
          expectedUserIds: ["me"],
          submittedUserIds: [],
          pendingUserIds: ["me"],
          revealed: false,
          myPick: null,
        },
      }),
    );
    vi.mocked(draftApi.listDraftPlayers).mockResolvedValue(players());
    renderPage();

    const male = await screen.findByRole("button", { name: /空いてる選手/ });
    expect(male).toBeDisabled();
    expect(male).toHaveTextContent("この巡は女性選手しか指名できません");
    expect(screen.getByRole("button", { name: /女流選手/ })).toBeEnabled();
  });
});
