import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { ErrorModalProvider } from "@/components/feedback/ErrorModalContext";
import { AvailabilityRequestCreatePage } from "@/features/availability/AvailabilityRequestCreatePage";
import { renderWithProviders, screen, waitFor } from "@/test/render";
import type { CommunityMember } from "@/features/community/types";

vi.mock("@/features/community/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/community/api")>();
  return { ...actual, listMembers: vi.fn() };
});
vi.mock("@/features/availability/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/availability/api")>();
  return { ...actual, createAvailabilityRequest: vi.fn() };
});

const communityApi = await import("@/features/community/api");
const availabilityApi = await import("@/features/availability/api");

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
    <MemoryRouter initialEntries={[`/communities/${COMMUNITY_ID}/availability-requests/new`]}>
      <ErrorModalProvider>
        <Routes>
          <Route
            path="/communities/:communityId/availability-requests/new"
            element={<AvailabilityRequestCreatePage />}
          />
          <Route
            path="/communities/:communityId/availability-requests"
            element={<p>提出リクエスト一覧画面</p>}
          />
        </Routes>
      </ErrorModalProvider>
    </MemoryRouter>,
  );
}

async function fillCommonFields(user: ReturnType<typeof userEvent.setup>, container: HTMLElement) {
  const startInput = container.querySelector('input[name="targetPeriodStart"]') as HTMLInputElement;
  const endInput = container.querySelector('input[name="targetPeriodEnd"]') as HTMLInputElement;
  const deadlineInput = container.querySelector('input[name="deadline"]') as HTMLInputElement;
  await user.type(startInput, "2026-08-01");
  await user.type(endInput, "2026-08-10");
  await user.type(deadlineInput, "2026-07-25T18:00");
}

afterEach(() => {
  vi.resetAllMocks();
});

describe("AvailabilityRequestCreatePage", () => {
  it("対象範囲のデフォルトは全員で、指名メンバーの選択欄は表示しない", async () => {
    vi.mocked(communityApi.listMembers).mockResolvedValue([baseMember()]);
    renderPage();

    await screen.findByRole("button", { name: "全員" });
    expect(screen.queryByText("対象メンバー")).not.toBeInTheDocument();
  });

  it("指名に切り替えるとメンバー選択欄が表示される", async () => {
    const user = userEvent.setup();
    vi.mocked(communityApi.listMembers).mockResolvedValue([baseMember()]);
    renderPage();

    await user.click(await screen.findByRole("button", { name: "指名" }));

    expect(await screen.findByText("対象メンバー")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "たろう" })).toBeInTheDocument();
  });

  it("指名を選んだのに誰も選択せず送信すると検証エラーを出し、APIを呼ばない", async () => {
    const user = userEvent.setup();
    vi.mocked(communityApi.listMembers).mockResolvedValue([baseMember()]);
    const { container } = renderPage();

    await fillCommonFields(user, container);
    await user.click(screen.getByRole("button", { name: "指名" }));
    await user.click(screen.getByRole("button", { name: "送信する" }));

    expect(
      await screen.findByText("対象メンバーを1人以上選択してください"),
    ).toBeInTheDocument();
    expect(availabilityApi.createAvailabilityRequest).not.toHaveBeenCalled();
  });

  it("全員を対象に送信すると、targetUserIdsはundefined・期間は開始00:00/終了23:59として送信する", async () => {
    const user = userEvent.setup();
    vi.mocked(communityApi.listMembers).mockResolvedValue([baseMember()]);
    vi.mocked(availabilityApi.createAvailabilityRequest).mockResolvedValue(
      {} as Awaited<ReturnType<typeof availabilityApi.createAvailabilityRequest>>,
    );
    const { container } = renderPage();

    await fillCommonFields(user, container);
    await user.click(screen.getByRole("button", { name: "送信する" }));

    await waitFor(() =>
      expect(availabilityApi.createAvailabilityRequest).toHaveBeenCalledWith(
        COMMUNITY_ID,
        expect.objectContaining({
          targetPeriodStart: "2026-08-01T00:00:00",
          targetPeriodEnd: "2026-08-10T23:59:59",
          targetScope: "ALL",
          targetUserIds: undefined,
          message: undefined,
        }),
      ),
    );
    expect(await screen.findByText("提出リクエスト一覧画面")).toBeInTheDocument();
  });

  it("指名メンバーを選んで送信すると、選択したuserIdの配列を送信する", async () => {
    const user = userEvent.setup();
    vi.mocked(communityApi.listMembers).mockResolvedValue([
      baseMember({ userId: "u1", nickname: "たろう" }),
      baseMember({ userId: "u2", nickname: "はなこ" }),
    ]);
    vi.mocked(availabilityApi.createAvailabilityRequest).mockResolvedValue(
      {} as Awaited<ReturnType<typeof availabilityApi.createAvailabilityRequest>>,
    );
    const { container } = renderPage();

    await fillCommonFields(user, container);
    await user.click(screen.getByRole("button", { name: "指名" }));
    await user.click(await screen.findByRole("checkbox", { name: "たろう" }));
    await user.click(screen.getByRole("button", { name: "送信する" }));

    await waitFor(() =>
      expect(availabilityApi.createAvailabilityRequest).toHaveBeenCalledWith(
        COMMUNITY_ID,
        expect.objectContaining({ targetScope: "SPECIFIED", targetUserIds: ["u1"] }),
      ),
    );
  });
});
