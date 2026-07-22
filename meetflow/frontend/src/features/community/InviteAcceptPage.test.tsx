import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { ErrorModalProvider } from "@/components/feedback/ErrorModalContext";
import { InviteAcceptPage } from "@/features/community/InviteAcceptPage";
import { renderWithProviders, screen, waitFor } from "@/test/render";
import type { InvitePreview } from "@/features/community/types";

vi.mock("@/features/community/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/community/api")>();
  return { ...actual, getInvitePreview: vi.fn(), joinViaInvite: vi.fn() };
});
vi.mock("@/features/auth/pendingInvite");

const communityApi = await import("@/features/community/api");
const pendingInvite = await import("@/features/auth/pendingInvite");

const TOKEN = "invite-token-1";

function basePreview(overrides: Partial<InvitePreview> = {}): InvitePreview {
  return {
    communityId: "community-1",
    communityName: "週末麻雀部",
    communityDescription: "",
    communityGenre: "麻雀",
    communityIcon: null,
    approvalRequired: false,
    invitedByDisplayName: "たろう",
    alreadyMember: false,
    joinRequestPending: false,
    ...overrides,
  };
}

function renderPage() {
  return renderWithProviders(
    <MemoryRouter initialEntries={[`/invite/${TOKEN}`]}>
      <ErrorModalProvider>
        <Routes>
          <Route path="/invite/:token" element={<InviteAcceptPage />} />
          <Route path="/" element={<p>ホーム画面</p>} />
          <Route path="/communities/:communityId" element={<p>コミュニティ詳細画面</p>} />
        </Routes>
      </ErrorModalProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.resetAllMocks();
});

describe("InviteAcceptPage", () => {
  it("到着時に保留中の招待パスを消費する", async () => {
    vi.mocked(communityApi.getInvitePreview).mockResolvedValue(basePreview());

    renderPage();

    await waitFor(() => expect(pendingInvite.consumePendingInvitePath).toHaveBeenCalled());
  });

  it("招待URLが無効な場合は空状態を表示する", async () => {
    vi.mocked(communityApi.getInvitePreview).mockRejectedValue(new Error("not found"));

    renderPage();

    expect(await screen.findByText("招待URLが無効です")).toBeInTheDocument();
  });

  it("既に参加済みの場合は専用の案内とコミュニティへの導線を表示する", async () => {
    const user = userEvent.setup();
    vi.mocked(communityApi.getInvitePreview).mockResolvedValue(
      basePreview({ alreadyMember: true }),
    );

    renderPage();

    expect(
      await screen.findByText("既にこのコミュニティに参加しています"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "コミュニティへ" }));
    expect(await screen.findByText("コミュニティ詳細画面")).toBeInTheDocument();
  });

  it("参加リクエストが承認待ちの場合は専用の案内を表示する", async () => {
    vi.mocked(communityApi.getInvitePreview).mockResolvedValue(
      basePreview({ joinRequestPending: true }),
    );

    renderPage();

    expect(
      await screen.findByText("参加リクエストを承認待ちです。管理者の承認をお待ちください"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "参加する" })).not.toBeInTheDocument();
  });

  it("承認不要の場合は参加メッセージ欄を表示せず、参加後はコミュニティ詳細へ遷移する", async () => {
    const user = userEvent.setup();
    vi.mocked(communityApi.getInvitePreview).mockResolvedValue(
      basePreview({ approvalRequired: false }),
    );
    vi.mocked(communityApi.joinViaInvite).mockResolvedValue({
      communityId: "community-1",
      status: "ACTIVE",
    });

    renderPage();
    await screen.findByText("参加しますか？");
    expect(screen.queryByPlaceholderText("参加メッセージ（任意）")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "参加する" }));

    await waitFor(() => expect(communityApi.joinViaInvite).toHaveBeenCalledWith(TOKEN, undefined));
    expect(await screen.findByText("コミュニティ詳細画面")).toBeInTheDocument();
  });

  it("承認が必要な場合は参加メッセージ欄を表示し、入力内容を送信する", async () => {
    const user = userEvent.setup();
    vi.mocked(communityApi.getInvitePreview).mockResolvedValue(
      basePreview({ approvalRequired: true }),
    );
    vi.mocked(communityApi.joinViaInvite).mockResolvedValue({
      communityId: "community-1",
      status: "PENDING",
    });

    renderPage();
    const messageInput = await screen.findByPlaceholderText("参加メッセージ（任意）");
    await user.type(messageInput, "よろしくお願いします");
    await user.click(screen.getByRole("button", { name: "参加する" }));

    await waitFor(() =>
      expect(communityApi.joinViaInvite).toHaveBeenCalledWith(TOKEN, "よろしくお願いします"),
    );
    expect(await screen.findByText("ホーム画面")).toBeInTheDocument();
  });

  it("招待者情報が無い場合は「〇〇さんから」を含まない見出しにする", async () => {
    vi.mocked(communityApi.getInvitePreview).mockResolvedValue(
      basePreview({ invitedByDisplayName: null }),
    );

    renderPage();

    expect(
      await screen.findByText("コミュニティ週末麻雀部に招待されています"),
    ).toBeInTheDocument();
  });
});
