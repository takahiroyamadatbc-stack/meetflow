import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { ErrorModalProvider } from "@/components/feedback/ErrorModalContext";
import { JoinRequestListPage } from "@/features/community/JoinRequestListPage";
import { renderWithProviders, screen, waitFor } from "@/test/render";
import type { JoinRequest } from "@/features/community/types";

vi.mock("@/features/community/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/community/api")>();
  return {
    ...actual,
    listJoinRequests: vi.fn(),
    approveJoinRequest: vi.fn(),
    rejectJoinRequest: vi.fn(),
  };
});

const communityApi = await import("@/features/community/api");

const COMMUNITY_ID = "community-1";

function baseRequest(overrides: Partial<JoinRequest> = {}): JoinRequest {
  return {
    requestId: "req-1",
    userId: "u1",
    nickname: "たろう",
    bio: "",
    gameTypes: [],
    beginnerOk: false,
    message: "",
    status: "PENDING",
    requestedAt: "2026-07-01T00:00:00+09:00",
    ...overrides,
  };
}

function renderPage() {
  return renderWithProviders(
    <MemoryRouter initialEntries={[`/communities/${COMMUNITY_ID}/join-requests`]}>
      <ErrorModalProvider>
        <Routes>
          <Route
            path="/communities/:communityId/join-requests"
            element={<JoinRequestListPage />}
          />
        </Routes>
      </ErrorModalProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.resetAllMocks();
});

describe("JoinRequestListPage", () => {
  it("未処理のリクエストが無い場合は空状態を表示する", async () => {
    vi.mocked(communityApi.listJoinRequests).mockResolvedValue([]);

    renderPage();

    expect(
      await screen.findByText("未処理の参加リクエストはありません"),
    ).toBeInTheDocument();
  });

  it("承認すると一覧から即座に取り除かれる（楽観的更新）", async () => {
    const user = userEvent.setup();
    vi.mocked(communityApi.listJoinRequests).mockResolvedValue([
      baseRequest({ requestId: "req-1", nickname: "たろう" }),
      baseRequest({ requestId: "req-2", nickname: "はなこ" }),
    ]);
    // 承認APIを解決させないことで、楽観的更新（Promise解決を待たない即時反映）を確認する
    vi.mocked(communityApi.approveJoinRequest).mockReturnValue(new Promise(() => {}));

    renderPage();
    await screen.findByText("たろう");

    // たろうが一覧の先頭のため、最初の「承認」ボタンがたろうのカードのもの
    await user.click(screen.getAllByRole("button", { name: "承認" })[0]);

    await waitFor(() => expect(screen.queryByText("たろう")).not.toBeInTheDocument());
    expect(screen.getByText("はなこ")).toBeInTheDocument();
  });

  it("承認に失敗した場合は一覧に戻す（ロールバック）", async () => {
    const user = userEvent.setup();
    vi.mocked(communityApi.listJoinRequests).mockResolvedValue([
      baseRequest({ requestId: "req-1", nickname: "たろう" }),
    ]);
    vi.mocked(communityApi.approveJoinRequest).mockRejectedValue(new Error("failed"));

    renderPage();
    await screen.findByText("たろう");
    await user.click(screen.getByRole("button", { name: "承認" }));

    await waitFor(() => expect(communityApi.approveJoinRequest).toHaveBeenCalled());
    expect(await screen.findByText("たろう")).toBeInTheDocument();
  });

  it("却下すると一覧から即座に取り除かれる", async () => {
    const user = userEvent.setup();
    vi.mocked(communityApi.listJoinRequests).mockResolvedValue([
      baseRequest({ requestId: "req-1", nickname: "たろう" }),
    ]);
    vi.mocked(communityApi.rejectJoinRequest).mockResolvedValue(undefined);

    renderPage();
    await screen.findByText("たろう");
    await user.click(screen.getByRole("button", { name: "却下" }));

    await waitFor(() => expect(screen.queryByText("たろう")).not.toBeInTheDocument());
    expect(communityApi.rejectJoinRequest).toHaveBeenCalledWith(COMMUNITY_ID, "req-1");
  });
});
