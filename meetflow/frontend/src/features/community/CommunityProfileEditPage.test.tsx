import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { ErrorModalProvider } from "@/components/feedback/ErrorModalContext";
import { CommunityProfileEditPage } from "@/features/community/CommunityProfileEditPage";
import { renderWithProviders, screen, waitFor } from "@/test/render";
import type { CommunityDetail } from "@/features/community/types";

vi.mock("@/features/community/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/community/api")>();
  return { ...actual, getCommunity: vi.fn(), updateCommunity: vi.fn(), updateThemeColor: vi.fn() };
});

const communityApi = await import("@/features/community/api");

const COMMUNITY_ID = "community-1";

function baseCommunity(overrides: Partial<CommunityDetail> = {}): CommunityDetail {
  return {
    communityId: COMMUNITY_ID,
    name: "テストコミュニティ",
    description: "既存のひとこと",
    genre: "麻雀",
    memberApprovalRequired: false,
    themeColor: "#FF0000",
    icon: null,
    role: "OWNER",
    pendingRequestCount: 0,
    rankingDefaultGameType: "MAHJONG4",
    rankingDefaultPeriodType: "ALL_TIME",
    rankingDefaultMetric: "AVERAGE_RANK",
    rankingDefaultMinGames: 0,
    ...overrides,
  };
}

function renderPage() {
  return renderWithProviders(
    <MemoryRouter initialEntries={[`/communities/${COMMUNITY_ID}/profile-edit`]}>
      <ErrorModalProvider>
        <Routes>
          <Route
            path="/communities/:communityId/profile-edit"
            element={<CommunityProfileEditPage />}
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

describe("CommunityProfileEditPage", () => {
  it("読み込み中はスケルトンを表示する", () => {
    vi.mocked(communityApi.getCommunity).mockReturnValue(new Promise(() => {}));

    const { container } = renderPage();

    expect(container.querySelector('[data-slot="skeleton"]')).toBeTruthy();
  });

  it("既存の値でひとこと欄を初期化する", async () => {
    vi.mocked(communityApi.getCommunity).mockResolvedValue(baseCommunity());

    renderPage();

    expect(await screen.findByLabelText("ひとこと")).toHaveValue("既存のひとこと");
  });

  it("保存すると説明文更新とテーマカラー更新の両方を呼ぶ", async () => {
    const user = userEvent.setup();
    vi.mocked(communityApi.getCommunity).mockResolvedValue(baseCommunity());
    vi.mocked(communityApi.updateCommunity).mockResolvedValue({
      communityId: COMMUNITY_ID,
      name: "テストコミュニティ",
      description: "新しいひとこと",
      genre: "麻雀",
      memberApprovalRequired: false,
    });
    vi.mocked(communityApi.updateThemeColor).mockResolvedValue({
      communityId: COMMUNITY_ID,
      themeColor: "#FF0000",
    });

    renderPage();
    const descriptionInput = await screen.findByLabelText("ひとこと");
    await user.clear(descriptionInput);
    await user.type(descriptionInput, "新しいひとこと");
    await user.click(screen.getByRole("button", { name: "保存する" }));

    await waitFor(() =>
      expect(communityApi.updateCommunity).toHaveBeenCalledWith(COMMUNITY_ID, {
        description: "新しいひとこと",
        icon: null,
      }),
    );
    expect(communityApi.updateThemeColor).toHaveBeenCalledWith(COMMUNITY_ID, "#FF0000");
    expect(await screen.findByText("コミュニティ詳細画面")).toBeInTheDocument();
  });

  it("テーマカラーがnullの場合は空文字としてupdateThemeColorへ送信する", async () => {
    const user = userEvent.setup();
    vi.mocked(communityApi.getCommunity).mockResolvedValue(baseCommunity({ themeColor: null }));
    vi.mocked(communityApi.updateCommunity).mockResolvedValue({
      communityId: COMMUNITY_ID,
      name: "テストコミュニティ",
      description: "既存のひとこと",
      genre: "麻雀",
      memberApprovalRequired: false,
    });
    vi.mocked(communityApi.updateThemeColor).mockResolvedValue({
      communityId: COMMUNITY_ID,
      themeColor: null,
    });

    renderPage();
    await screen.findByLabelText("ひとこと");
    await user.click(screen.getByRole("button", { name: "保存する" }));

    await waitFor(() =>
      expect(communityApi.updateThemeColor).toHaveBeenCalledWith(COMMUNITY_ID, ""),
    );
  });
});
