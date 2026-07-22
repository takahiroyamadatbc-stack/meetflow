import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { ErrorModalProvider } from "@/components/feedback/ErrorModalContext";
import { EventTemplateFormPage } from "@/features/matching/EventTemplateFormPage";
import { renderWithProviders, screen, waitFor } from "@/test/render";
import type { CommunityDetail } from "@/features/community/types";
import type { EventTemplate } from "@/features/matching/types";

vi.mock("@/features/community/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/community/api")>();
  return { ...actual, getCommunity: vi.fn() };
});
vi.mock("@/features/matching/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/matching/api")>();
  return {
    ...actual,
    listEventTemplates: vi.fn(),
    createEventTemplate: vi.fn(),
    updateEventTemplate: vi.fn(),
  };
});

const communityApi = await import("@/features/community/api");
const matchingApi = await import("@/features/matching/api");

const COMMUNITY_ID = "community-1";
const TEMPLATE_ID = "template-1";

function baseCommunity(genre: CommunityDetail["genre"] = "麻雀"): CommunityDetail {
  return {
    communityId: COMMUNITY_ID,
    name: "テストコミュニティ",
    description: "",
    genre,
    memberApprovalRequired: false,
    themeColor: null,
    icon: null,
    role: "OWNER",
    pendingRequestCount: 0,
    rankingDefaultGameType: "MAHJONG4",
    rankingDefaultPeriodType: "ALL_TIME",
    rankingDefaultMetric: "AVERAGE_RANK",
    rankingDefaultMinGames: 0,
  };
}

function renderNewPage() {
  return renderWithProviders(
    <MemoryRouter initialEntries={[`/communities/${COMMUNITY_ID}/event-templates/new`]}>
      <ErrorModalProvider>
        <Routes>
          <Route
            path="/communities/:communityId/event-templates/new"
            element={<EventTemplateFormPage />}
          />
          <Route
            path="/communities/:communityId/event-templates"
            element={<p>開催条件一覧画面</p>}
          />
        </Routes>
      </ErrorModalProvider>
    </MemoryRouter>,
  );
}

function renderEditPage() {
  return renderWithProviders(
    <MemoryRouter
      initialEntries={[`/communities/${COMMUNITY_ID}/event-templates/${TEMPLATE_ID}/edit`]}
    >
      <ErrorModalProvider>
        <Routes>
          <Route
            path="/communities/:communityId/event-templates/:templateId/edit"
            element={<EventTemplateFormPage />}
          />
          <Route
            path="/communities/:communityId/event-templates"
            element={<p>開催条件一覧画面</p>}
          />
        </Routes>
      </ErrorModalProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.resetAllMocks();
});

describe("EventTemplateFormPage", () => {
  it("麻雀コミュニティでは四人麻雀/三人麻雀のボタンから選択できる", async () => {
    vi.mocked(communityApi.getCommunity).mockResolvedValue(baseCommunity("麻雀"));
    renderNewPage();

    expect(await screen.findByRole("button", { name: "四人麻雀" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "三人麻雀" })).toBeInTheDocument();
  });

  it("麻雀以外のコミュニティではゲーム種別選択UIを表示せず、ジャンル固定である旨を表示する", async () => {
    vi.mocked(communityApi.getCommunity).mockResolvedValue(baseCommunity("ボードゲーム"));
    renderNewPage();

    await screen.findByRole("button", { name: "作成する" });
    expect(screen.queryByRole("button", { name: "四人麻雀" })).not.toBeInTheDocument();
    expect(screen.getByText(/コミュニティのジャンルに固定/)).toBeInTheDocument();
  });

  it("最低人数が最大人数を超える場合はエラーを表示し、送信しない", async () => {
    const user = userEvent.setup();
    vi.mocked(communityApi.getCommunity).mockResolvedValue(baseCommunity("麻雀"));
    const { container } = renderNewPage();
    await screen.findByRole("button", { name: "作成する" });

    const minInput = container.querySelector('input[name="minPlayers"]') as HTMLInputElement;
    const maxInput = container.querySelector('input[name="maxPlayers"]') as HTMLInputElement;
    await user.clear(minInput);
    await user.type(minInput, "5");
    await user.clear(maxInput);
    await user.type(maxInput, "4");
    await user.click(screen.getByRole("button", { name: "作成する" }));

    expect(
      await screen.findByText("最低人数は最大人数以下にしてください"),
    ).toBeInTheDocument();
    expect(matchingApi.createEventTemplate).not.toHaveBeenCalled();
  });

  it("新規作成時はcreateEventTemplateを呼び、成功後に一覧画面へ遷移する", async () => {
    const user = userEvent.setup();
    vi.mocked(communityApi.getCommunity).mockResolvedValue(baseCommunity("麻雀"));
    vi.mocked(matchingApi.createEventTemplate).mockResolvedValue({
      templateId: TEMPLATE_ID,
      gameType: "MAHJONG4",
      minPlayers: 4,
      maxPlayers: 4,
      priority: 50,
      conditions: { beginnerOk: false },
    } satisfies EventTemplate);

    renderNewPage();
    await user.click(await screen.findByRole("button", { name: "作成する" }));

    await waitFor(() =>
      expect(matchingApi.createEventTemplate).toHaveBeenCalledWith(COMMUNITY_ID, {
        gameType: "MAHJONG4",
        minPlayers: 4,
        maxPlayers: 4,
        priority: 50,
        conditions: { beginnerOk: false },
      }),
    );
    expect(await screen.findByText("開催条件一覧画面")).toBeInTheDocument();
  });

  it("編集時は既存の値で初期化し、updateEventTemplateにtemplateIdを渡す", async () => {
    const user = userEvent.setup();
    vi.mocked(communityApi.getCommunity).mockResolvedValue(baseCommunity("麻雀"));
    vi.mocked(matchingApi.listEventTemplates).mockResolvedValue([
      {
        templateId: TEMPLATE_ID,
        gameType: "MAHJONG3",
        minPlayers: 3,
        maxPlayers: 3,
        priority: 80,
        conditions: { beginnerOk: true },
      },
    ]);
    vi.mocked(matchingApi.updateEventTemplate).mockResolvedValue({
      templateId: TEMPLATE_ID,
      gameType: "MAHJONG3",
      minPlayers: 3,
      maxPlayers: 3,
      priority: 80,
      conditions: { beginnerOk: true },
    });

    const { container } = renderEditPage();
    await screen.findByRole("button", { name: "更新する" });
    expect(container.querySelector('input[name="minPlayers"]')).toHaveValue(3);

    await user.click(screen.getByRole("button", { name: "更新する" }));

    await waitFor(() =>
      expect(matchingApi.updateEventTemplate).toHaveBeenCalledWith(
        COMMUNITY_ID,
        TEMPLATE_ID,
        expect.objectContaining({ gameType: "MAHJONG3", minPlayers: 3, maxPlayers: 3 }),
      ),
    );
  });
});
