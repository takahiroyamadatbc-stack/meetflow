import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { ErrorModalProvider } from "@/components/feedback/ErrorModalContext";
import { DraftStandingsPage } from "@/features/draft/DraftStandingsPage";
import { renderWithProviders, screen, waitFor } from "@/test/render";
import type { DraftDetail, Standings } from "@/features/draft/types";

vi.mock("@/features/draft/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/draft/api")>();
  return {
    ...actual,
    getDraft: vi.fn(),
    getStandings: vi.fn(),
    refreshStandings: vi.fn(),
    submitManualResult: vi.fn(),
  };
});
const authUserId = { current: "host" };
vi.mock("@/features/auth/useAuthUser", () => ({
  useAuthUser: () => ({ status: "authenticated", userId: authUserId.current }),
}));

const draftApi = await import("@/features/draft/api");

const DRAFT_ID = "draft-1";

function baseStandings(overrides: Partial<Standings> = {}): Standings {
  return {
    season: "2026-27",
    regularSeasonEndDate: null,
    standings: [
      {
        userId: "host",
        displayName: "主催者",
        totalPoints: 120.5,
        rank: 1,
        players: [
          {
            playerId: "honda",
            playerName: "本田朋広",
            teamName: "TEAM RAIDEN / 雷電",
            isFemale: false,
            points: 100.5,
            games: 3,
          },
          {
            playerId: "tojo",
            playerName: "東城りお",
            teamName: "BEAST X",
            isFemale: true,
            points: 20.0,
            games: 2,
          },
        ],
      },
      {
        userId: "u1",
        displayName: "たろう",
        totalPoints: -30.2,
        rank: 2,
        players: [],
      },
    ],
    lastUpdatedAt: "2026-09-18T01:00:00.000Z",
    lastError: null,
    lastErrorAt: null,
    mismatchedPlayers: [],
    unmatchedPlayerNames: [],
    playedGamedayCount: 3,
    scheduledGamedayCount: 13,
    latestPlayedDate: "2026-09-17",
    inGameWindow: false,
    latestConfirmedDate: "2026-09-17",
    canRefresh: true,
    ...overrides,
  };
}

function baseDraft(): DraftDetail {
  return {
    draftId: DRAFT_ID,
    communityId: "community-1",
    name: "Mリーグドラフト2026-27",
    season: "2026-27",
    hostUserId: "host",
    status: "COMPLETED",
    round: 4,
    wave: 1,
    rounds: 4,
    version: 9,
    participantCount: 2,
    femalePlayerCount: 13,
    femaleSurplusRemaining: 11,
    regularSeasonEndDate: null,
    createdAt: "2026-09-18T00:00:00.000Z",
    updatedAt: "2026-09-18T00:00:00.000Z",
    participants: [],
    rosters: {},
    currentWave: null,
  };
}

function renderPage() {
  return renderWithProviders(
    <ErrorModalProvider>
      <MemoryRouter initialEntries={[`/drafts/${DRAFT_ID}/standings`]}>
        <Routes>
          <Route path="/drafts/:draftId/standings" element={<DraftStandingsPage />} />
        </Routes>
      </MemoryRouter>
    </ErrorModalProvider>,
  );
}

afterEach(() => {
  authUserId.current = "host";
  vi.clearAllMocks();
});

describe("DraftStandingsPage", () => {
  it("順位・合計ポイント・選手内訳を表示する", async () => {
    vi.mocked(draftApi.getDraft).mockResolvedValue(baseDraft());
    vi.mocked(draftApi.getStandings).mockResolvedValue(baseStandings());
    renderPage();

    expect(await screen.findByText("+120.5pt")).toBeInTheDocument();
    expect(screen.getByText("-30.2pt")).toBeInTheDocument();
    expect(screen.getByText("1位")).toBeInTheDocument();
    expect(screen.getByText("本田朋広")).toBeInTheDocument();
    expect(screen.getByText("+100.5pt / 3半荘")).toBeInTheDocument();
    expect(screen.getByText("消化 3節 ／ 残り 13節")).toBeInTheDocument();
  });

  it("更新を押すと取得APIを呼ぶ", async () => {
    vi.mocked(draftApi.getDraft).mockResolvedValue(baseDraft());
    vi.mocked(draftApi.getStandings).mockResolvedValue(baseStandings());
    vi.mocked(draftApi.refreshStandings).mockResolvedValue({
      refreshed: true,
      latestPlayedDate: "2026-09-17",
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "最新の成績を取得" }));
    await waitFor(() => expect(draftApi.refreshStandings).toHaveBeenCalledWith(DRAFT_ID));
  });

  it("今日すでに取得済みなら更新ボタンを押せない", async () => {
    // DESIGN.md §4.8: 取得は1日1回まで。
    vi.mocked(draftApi.getDraft).mockResolvedValue(baseDraft());
    vi.mocked(draftApi.getStandings).mockResolvedValue(baseStandings({ canRefresh: false }));
    renderPage();

    expect(await screen.findByRole("button", { name: "今日は取得済みです" })).toBeDisabled();
  });

  it("取得に失敗していても古いデータと最終更新を出す", async () => {
    // DESIGN.md §7: 失敗時は古いデータを出し続けつつ、最終更新を必ず出す。
    vi.mocked(draftApi.getDraft).mockResolvedValue(baseDraft());
    vi.mocked(draftApi.getStandings).mockResolvedValue(
      baseStandings({ lastError: "サイト構造の変更の可能性" }),
    );
    renderPage();

    expect(
      await screen.findByText("公式サイトからの取得に失敗しています"),
    ).toBeInTheDocument();
    expect(screen.getByText("サイト構造の変更の可能性")).toBeInTheDocument();
    // 成績自体は消さない
    expect(screen.getByText("+120.5pt")).toBeInTheDocument();
    expect(screen.getByText(/最終更新:/)).toBeInTheDocument();
  });

  it("集計範囲が未設定ならその旨を出す", async () => {
    // DESIGN.md §4.15: 入れ忘れるとセミファイナルの点が混ざる。
    vi.mocked(draftApi.getDraft).mockResolvedValue(baseDraft());
    vi.mocked(draftApi.getStandings).mockResolvedValue(baseStandings());
    renderPage();

    expect(
      await screen.findByText(/シーズン全体（レギュラーシーズン終了日が未設定）/),
    ).toBeInTheDocument();
  });

  it("対局の時間帯なら対局中バッジを出す", async () => {
    // DESIGN.md §4.9: 19時は最新確定日を変えず、バッジの表示判定にだけ使う。
    vi.mocked(draftApi.getDraft).mockResolvedValue(baseDraft());
    vi.mocked(draftApi.getStandings).mockResolvedValue(baseStandings({ inGameWindow: true }));
    renderPage();

    expect(await screen.findByText("対局中")).toBeInTheDocument();
  });

  it("手動入力は主催者にだけ出す", async () => {
    vi.mocked(draftApi.getDraft).mockResolvedValue(baseDraft());
    vi.mocked(draftApi.getStandings).mockResolvedValue(baseStandings());
    renderPage();
    expect(
      await screen.findByRole("button", { name: "結果を手動で入力する" }),
    ).toBeInTheDocument();
  });

  it("主催者以外には手動入力を出さない", async () => {
    authUserId.current = "u1";
    vi.mocked(draftApi.getDraft).mockResolvedValue(baseDraft());
    vi.mocked(draftApi.getStandings).mockResolvedValue(baseStandings());
    renderPage();

    expect(await screen.findByText("+120.5pt")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "結果を手動で入力する" }),
    ).not.toBeInTheDocument();
  });

  it("主催者は着順を入力せずに結果を手動登録できる", async () => {
    // DESIGN.md §7のフォールバック。着順はポイントの降順から導出する。
    vi.mocked(draftApi.getDraft).mockResolvedValue(baseDraft());
    vi.mocked(draftApi.getStandings).mockResolvedValue(baseStandings());
    vi.mocked(draftApi.submitManualResult).mockResolvedValue({
      date: "20260916",
      no: 2,
      gameCount: 1,
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "結果を手動で入力する" }));
    await user.type(screen.getByLabelText("対局日"), "2026-09-16");
    await user.type(screen.getByLabelText("節番号"), "2");
    const names = ["本田朋広", "東城りお", "石井一馬", "渡辺太"];
    const points = ["30", "10", "-10", "-30"];
    for (let index = 0; index < names.length; index += 1) {
      await user.type(screen.getByLabelText(`第1回戦 選手${index + 1}`), names[index]);
      await user.type(screen.getByLabelText(`第1回戦 ポイント${index + 1}`), points[index]);
    }
    await user.click(screen.getByRole("button", { name: "登録する" }));

    await waitFor(() =>
      expect(draftApi.submitManualResult).toHaveBeenCalledWith(DRAFT_ID, {
        date: "2026-09-16",
        no: 2,
        games: [
          {
            label: "第1回戦",
            rows: [
              { rank: 1, name: "本田朋広", point: 30 },
              { rank: 2, name: "東城りお", point: 10 },
              { rank: 3, name: "石井一馬", point: -10 },
              { rank: 4, name: "渡辺太", point: -30 },
            ],
          },
        ],
      }),
    );
  });
});
