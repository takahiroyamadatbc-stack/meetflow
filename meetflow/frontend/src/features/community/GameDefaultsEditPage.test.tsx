import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { ErrorModalProvider } from "@/components/feedback/ErrorModalContext";
import { GameDefaultsEditPage } from "@/features/community/GameDefaultsEditPage";
import { renderWithProviders, screen, waitFor, within } from "@/test/render";
import type { CommunityDetail } from "@/features/community/types";

vi.mock("@/features/community/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/community/api")>();
  return { ...actual, getCommunity: vi.fn(), updateGameDefaults: vi.fn() };
});

const communityApi = await import("@/features/community/api");

const COMMUNITY_ID = "community-1";

function baseCommunity(overrides: Partial<CommunityDetail> = {}): CommunityDetail {
  return {
    communityId: COMMUNITY_ID,
    name: "テストコミュニティ",
    description: "",
    genre: "麻雀",
    memberApprovalRequired: false,
    themeColor: null,
    icon: null,
    role: "OWNER",
    pendingRequestCount: 0,
    rankingDefaultGameType: "MAHJONG4",
    rankingDefaultPeriodType: "MONTH",
    rankingDefaultMetric: "AVERAGE_RANK",
    rankingDefaultMinGames: 0,
    gameDefaults: null,
    ...overrides,
  };
}

function renderPage() {
  return renderWithProviders(
    <MemoryRouter initialEntries={[`/communities/${COMMUNITY_ID}/game-defaults`]}>
      <ErrorModalProvider>
        <Routes>
          <Route
            path="/communities/:communityId/game-defaults"
            element={<GameDefaultsEditPage />}
          />
          <Route path="/communities/:communityId" element={<p>コミュニティ詳細画面</p>} />
        </Routes>
      </ErrorModalProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.resetAllMocks();
});

describe("GameDefaultsEditPage（Issue #115）", () => {
  it("設定済みの種目は入力欄を表示し、保存済みの値で初期化する", async () => {
    vi.mocked(communityApi.getCommunity).mockResolvedValue(
      baseCommunity({
        gameDefaults: {
          MAHJONG4: { startingPoints: 25000, returnPoints: 30000, umaByRank: [20, 10, -10, -20] },
        },
      }),
    );

    renderPage();

    const yonma = await screen.findByRole("region", { name: "四人麻雀" });
    expect(within(yonma).getByLabelText("配給原点")).toHaveValue(25000);
    expect(within(yonma).getByLabelText("返し点")).toHaveValue(30000);
    expect(within(yonma).getByLabelText("1位")).toHaveValue(20);
    expect(within(yonma).getByText("オカ（トップ取り）：+20")).toBeInTheDocument();

    const sanma = screen.getByRole("region", { name: "三人麻雀" });
    expect(within(sanma).queryByLabelText("配給原点")).not.toBeInTheDocument();
  });

  it("未設定の種目を有効にして保存すると、入力した値でupdateGameDefaultsを呼びコミュニティ詳細へ戻る", async () => {
    const user = userEvent.setup();
    vi.mocked(communityApi.getCommunity).mockResolvedValue(baseCommunity());
    vi.mocked(communityApi.updateGameDefaults).mockResolvedValue({
      communityId: COMMUNITY_ID,
      gameDefaults: null,
    });

    renderPage();

    const sanma = await screen.findByRole("region", { name: "三人麻雀" });
    await user.click(within(sanma).getByRole("checkbox"));
    const firstUma = within(sanma).getByLabelText("1位");
    await user.clear(firstUma);
    await user.type(firstUma, "15");
    const thirdUma = within(sanma).getByLabelText("3位");
    await user.clear(thirdUma);
    await user.type(thirdUma, "-15");
    await user.click(screen.getByRole("button", { name: "保存する" }));

    await waitFor(() =>
      expect(communityApi.updateGameDefaults).toHaveBeenCalledWith(COMMUNITY_ID, {
        MAHJONG3: { startingPoints: 35000, returnPoints: 40000, umaByRank: [15, 0, -15] },
      }),
    );
    await waitFor(() => expect(screen.getByText("コミュニティ詳細画面")).toBeInTheDocument());
  });

  it("ウマの合計が0でない場合は注意を表示する", async () => {
    const user = userEvent.setup();
    vi.mocked(communityApi.getCommunity).mockResolvedValue(baseCommunity());

    renderPage();

    const yonma = await screen.findByRole("region", { name: "四人麻雀" });
    await user.click(within(yonma).getByRole("checkbox"));
    await user.type(within(yonma).getByLabelText("1位"), "5");

    expect(within(yonma).getByText("ウマの合計が+5になっています（通常は0）")).toBeInTheDocument();
  });

  it("入力欄が空欄のままでは保存できない", async () => {
    const user = userEvent.setup();
    vi.mocked(communityApi.getCommunity).mockResolvedValue(baseCommunity());

    renderPage();

    const yonma = await screen.findByRole("region", { name: "四人麻雀" });
    await user.click(within(yonma).getByRole("checkbox"));
    await user.clear(within(yonma).getByLabelText("配給原点"));

    expect(screen.getByRole("button", { name: "保存する" })).toBeDisabled();
  });
});
