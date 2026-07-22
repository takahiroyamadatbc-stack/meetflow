import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { ErrorModalProvider } from "@/components/feedback/ErrorModalContext";
import { RankingSettingsEditPage } from "@/features/community/RankingSettingsEditPage";
import { fireEvent, renderWithProviders, screen, waitFor } from "@/test/render";
import type { CommunityDetail } from "@/features/community/types";

// レンダー本体で直接setState(条件ガード付き)を行う初期化パターン(48-54行目)が
// 実際に正しく初期化・保存できるか、無限ループ等を起こさないかを検証する。
// このパターン自体はReact公式docs「Adjusting some state when a prop changes」で
// 推奨されている手法のため、バグとしての修正はせず現状の挙動をテストで固定する。
vi.mock("@/features/community/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/community/api")>();
  return { ...actual, getCommunity: vi.fn(), updateRankingSettings: vi.fn() };
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
    rankingDefaultMinGames: 5,
    ...overrides,
  };
}

function renderPage() {
  return renderWithProviders(
    <MemoryRouter initialEntries={[`/communities/${COMMUNITY_ID}/ranking-settings`]}>
      <ErrorModalProvider>
        <Routes>
          <Route
            path="/communities/:communityId/ranking-settings"
            element={<RankingSettingsEditPage />}
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

describe("RankingSettingsEditPage", () => {
  it("コミュニティのデフォルト値でフォームを初期化する", async () => {
    vi.mocked(communityApi.getCommunity).mockResolvedValue(baseCommunity());

    renderPage();

    await waitFor(() => expect(screen.getByRole("button", { name: "保存する" })).toBeEnabled());
    // SelectValueは選択中のitemがマウントされるまで生の値をそのまま表示する
    // （ラベルへの変換はSelectItem側にあり、ポップアップを開くまでDOMに無いため）。
    expect(screen.getByText("MAHJONG4")).toBeInTheDocument();
    expect(screen.getByText("MONTH")).toBeInTheDocument();
    expect(screen.getByText("AVERAGE_RANK")).toBeInTheDocument();
    expect(screen.getByRole("spinbutton")).toHaveValue(5);
  });

  it("最低対局数を変更して保存すると、変更後の値でupdateRankingSettingsを呼ぶ", async () => {
    const user = userEvent.setup();
    vi.mocked(communityApi.getCommunity).mockResolvedValue(baseCommunity());
    vi.mocked(communityApi.updateRankingSettings).mockResolvedValue({
      communityId: COMMUNITY_ID,
      gameType: "MAHJONG4",
      periodType: "MONTH",
      metric: "AVERAGE_RANK",
      minGames: 10,
    });

    renderPage();

    const minGamesInput = await screen.findByRole("spinbutton");
    await user.clear(minGamesInput);
    await user.type(minGamesInput, "10");
    await user.click(screen.getByRole("button", { name: "保存する" }));

    await waitFor(() =>
      expect(communityApi.updateRankingSettings).toHaveBeenCalledWith(COMMUNITY_ID, {
        gameType: "MAHJONG4",
        periodType: "MONTH",
        metric: "AVERAGE_RANK",
        minGames: 10,
      }),
    );
  });

  it("保存に成功するとコミュニティ詳細画面へ遷移する", async () => {
    const user = userEvent.setup();
    vi.mocked(communityApi.getCommunity).mockResolvedValue(baseCommunity());
    vi.mocked(communityApi.updateRankingSettings).mockResolvedValue({
      communityId: COMMUNITY_ID,
      gameType: "MAHJONG4",
      periodType: "MONTH",
      metric: "AVERAGE_RANK",
      minGames: 10,
    });

    renderPage();

    await user.click(await screen.findByRole("button", { name: "保存する" }));

    await waitFor(() => expect(screen.getByText("コミュニティ詳細画面")).toBeInTheDocument());
  });

  it("負の最低対局数は0に切り下げる", async () => {
    vi.mocked(communityApi.getCommunity).mockResolvedValue(
      baseCommunity({ rankingDefaultMinGames: 0 }),
    );

    renderPage();

    const minGamesInput = await screen.findByRole("spinbutton");
    fireEvent.change(minGamesInput, { target: { value: "-5" } });

    expect(minGamesInput).toHaveValue(0);
  });
});
