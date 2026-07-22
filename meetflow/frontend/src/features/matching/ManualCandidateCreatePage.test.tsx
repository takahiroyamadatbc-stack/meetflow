import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { ErrorModalProvider } from "@/components/feedback/ErrorModalContext";
import { ManualCandidateCreatePage } from "@/features/matching/ManualCandidateCreatePage";
import { renderWithProviders, screen, waitFor } from "@/test/render";
import type { CommunityMember } from "@/features/community/types";
import type { Candidate } from "@/features/matching/types";

vi.mock("@/features/community/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/community/api")>();
  return { ...actual, listMembers: vi.fn() };
});
vi.mock("@/features/matching/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/matching/api")>();
  return { ...actual, createManualCandidate: vi.fn() };
});

const communityApi = await import("@/features/community/api");
const matchingApi = await import("@/features/matching/api");

const COMMUNITY_ID = "community-1";

function baseMember(overrides: Partial<CommunityMember> = {}): CommunityMember {
  return {
    userId: "u1",
    nickname: "たろう",
    role: "MEMBER",
    status: "ACTIVE",
    joinedAt: "2026-01-01T00:00:00+09:00",
    icon: "",
    bio: "",
    gameTypes: [],
    ...overrides,
  };
}

function renderPage() {
  return renderWithProviders(
    <MemoryRouter initialEntries={[`/communities/${COMMUNITY_ID}/matching/candidates/manual`]}>
      <ErrorModalProvider>
        <Routes>
          <Route
            path="/communities/:communityId/matching/candidates/manual"
            element={<ManualCandidateCreatePage />}
          />
          <Route
            path="/communities/:communityId/matching/candidates/:candidateId"
            element={<p>候補詳細画面</p>}
          />
        </Routes>
      </ErrorModalProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.resetAllMocks();
});

describe("ManualCandidateCreatePage", () => {
  it("退会済み(SUSPENDED)メンバーは選択肢に表示しない", async () => {
    vi.mocked(communityApi.listMembers).mockResolvedValue([
      baseMember({ userId: "u1", nickname: "たろう", status: "ACTIVE" }),
      baseMember({ userId: "u2", nickname: "はなこ", status: "SUSPENDED" }),
    ]);

    renderPage();

    await screen.findByText("たろう");
    expect(screen.queryByText("はなこ")).not.toBeInTheDocument();
  });

  it("メンバーを1人も選択せず送信すると検証エラーを出す", async () => {
    const user = userEvent.setup();
    vi.mocked(communityApi.listMembers).mockResolvedValue([baseMember()]);

    renderPage();
    await screen.findByText("たろう");
    await user.click(screen.getByRole("button", { name: "この内容でイベントを作成する" }));

    expect(
      await screen.findByText("メンバーを1人以上選択してください"),
    ).toBeInTheDocument();
    expect(matchingApi.createManualCandidate).not.toHaveBeenCalled();
  });

  it("終了日時が開始日時以前の場合は検証エラーを出す", async () => {
    const user = userEvent.setup();
    vi.mocked(communityApi.listMembers).mockResolvedValue([baseMember()]);

    const { container } = renderPage();
    await screen.findByText("たろう");
    await user.click(screen.getByRole("checkbox", { name: "たろう" }));
    const startInput = container.querySelector('input[name="startTime"]') as HTMLInputElement;
    const endInput = container.querySelector('input[name="endTime"]') as HTMLInputElement;
    await user.type(startInput, "2026-08-01T19:00");
    await user.type(endInput, "2026-08-01T18:00");
    await user.click(screen.getByRole("button", { name: "この内容でイベントを作成する" }));

    expect(
      await screen.findByText("終了日時は開始日時より後にしてください"),
    ).toBeInTheDocument();
    expect(matchingApi.createManualCandidate).not.toHaveBeenCalled();
  });

  it("ゲーム種別が未指定の場合はundefinedとして送信する", async () => {
    const user = userEvent.setup();
    vi.mocked(communityApi.listMembers).mockResolvedValue([baseMember()]);
    vi.mocked(matchingApi.createManualCandidate).mockResolvedValue({
      candidateId: "candidate-1",
    } as Candidate);

    const { container } = renderPage();
    await screen.findByText("たろう");
    await user.click(screen.getByRole("checkbox", { name: "たろう" }));
    const startInput = container.querySelector('input[name="startTime"]') as HTMLInputElement;
    const endInput = container.querySelector('input[name="endTime"]') as HTMLInputElement;
    await user.type(startInput, "2026-08-01T19:00");
    await user.type(endInput, "2026-08-01T22:00");
    await user.click(screen.getByRole("button", { name: "この内容でイベントを作成する" }));

    await waitFor(() =>
      expect(matchingApi.createManualCandidate).toHaveBeenCalledWith(COMMUNITY_ID, {
        memberIds: ["u1"],
        startTime: "2026-08-01T19:00",
        endTime: "2026-08-01T22:00",
        gameType: undefined,
      }),
    );
    expect(await screen.findByText("候補詳細画面")).toBeInTheDocument();
  });
});
