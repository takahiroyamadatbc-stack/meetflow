import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { ErrorModalProvider } from "@/components/feedback/ErrorModalContext";
import { DraftListPage } from "@/features/draft/DraftListPage";
import { renderWithProviders, screen, waitFor } from "@/test/render";
import type { CommunityDetail } from "@/features/community/types";
import type { MembershipRole } from "@/types/api";
import type { DraftSummary } from "@/features/draft/types";

vi.mock("@/features/draft/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/draft/api")>();
  return { ...actual, listDrafts: vi.fn(), deleteDraft: vi.fn() };
});
vi.mock("@/features/community/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/community/api")>();
  return { ...actual, getCommunity: vi.fn() };
});

const draftApi = await import("@/features/draft/api");
const communityApi = await import("@/features/community/api");

const COMMUNITY_ID = "community-1";
const DRAFT_ID = "draft-1";

function draft(overrides: Partial<DraftSummary> = {}): DraftSummary {
  return {
    draftId: DRAFT_ID,
    communityId: COMMUNITY_ID,
    name: "Mリーグドラフト2026-27",
    season: "2026-27",
    hostUserId: "host",
    status: "SETUP",
    round: 0,
    wave: 0,
    rounds: 4,
    version: 1,
    participantCount: 3,
    femalePlayerCount: 13,
    femaleSurplusRemaining: 10,
    regularSeasonEndDate: null,
    createdAt: "2026-09-18T00:00:00.000Z",
    updatedAt: "2026-09-18T00:00:00.000Z",
    ...overrides,
  };
}

function mockPage(role: MembershipRole, drafts: DraftSummary[] = [draft()]) {
  vi.mocked(communityApi.getCommunity).mockResolvedValue({
    role,
  } as unknown as CommunityDetail);
  vi.mocked(draftApi.listDrafts).mockResolvedValue(drafts);
}

function renderPage() {
  return renderWithProviders(
    <ErrorModalProvider>
      <MemoryRouter initialEntries={[`/communities/${COMMUNITY_ID}/drafts`]}>
        <Routes>
          <Route path="/communities/:communityId/drafts" element={<DraftListPage />} />
        </Routes>
      </MemoryRouter>
    </ErrorModalProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("DraftListPage の削除", () => {
  // 作成（DESIGN.md §4.13）と揃えてOWNER/ADMINのみ。
  // 消えると戻せないので、必ず確認ダイアログを挟む。

  it("確認ダイアログでOKするまで削除しない", async () => {
    mockPage("OWNER");
    vi.mocked(draftApi.deleteDraft).mockResolvedValue({
      draftId: DRAFT_ID,
      deletedItemCount: 44,
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "削除" }));
    // ダイアログが出ただけの段階では呼ばれていない
    expect(
      await screen.findByText("「Mリーグドラフト2026-27」を削除しますか？"),
    ).toBeInTheDocument();
    expect(draftApi.deleteDraft).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "削除する" }));
    await waitFor(() => expect(draftApi.deleteDraft).toHaveBeenCalledWith(DRAFT_ID));
  });

  it("確認ダイアログでキャンセルすれば削除しない", async () => {
    mockPage("OWNER");
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "削除" }));
    await user.click(screen.getByRole("button", { name: "キャンセル" }));

    expect(draftApi.deleteDraft).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(
        screen.queryByText("「Mリーグドラフト2026-27」を削除しますか？"),
      ).not.toBeInTheDocument(),
    );
  });

  it("一般メンバーには削除ボタンを出さない", async () => {
    mockPage("MEMBER");
    renderPage();

    expect(await screen.findByText("Mリーグドラフト2026-27")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "削除" })).not.toBeInTheDocument();
  });

  it("削除ボタンを押してもドラフト画面には遷移しない", async () => {
    // 削除ボタンをカードのLinkの中に置くと、消すつもりが開いてしまう。
    mockPage("ADMIN");
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "削除" }));

    // 遷移していればカード（とダイアログ）は消えている
    expect(
      screen.getByText("「Mリーグドラフト2026-27」を削除しますか？"),
    ).toBeInTheDocument();
  });
});
