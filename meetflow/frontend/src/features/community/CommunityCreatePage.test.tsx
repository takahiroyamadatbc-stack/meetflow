import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { ErrorModalProvider } from "@/components/feedback/ErrorModalContext";
import { CommunityCreatePage } from "@/features/community/CommunityCreatePage";
import { renderWithProviders, screen, waitFor } from "@/test/render";
import type { CommunityMutationResult } from "@/features/community/types";

vi.mock("@/features/community/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/community/api")>();
  return { ...actual, createCommunity: vi.fn() };
});

const communityApi = await import("@/features/community/api");

function renderPage() {
  return renderWithProviders(
    <MemoryRouter initialEntries={["/communities/new"]}>
      <ErrorModalProvider>
        <Routes>
          <Route path="/communities/new" element={<CommunityCreatePage />} />
          <Route path="/communities/:communityId" element={<p>コミュニティ詳細画面</p>} />
        </Routes>
      </ErrorModalProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.resetAllMocks();
});

describe("CommunityCreatePage", () => {
  it("ジャンルの初期値は麻雀（固定選択肢の先頭）", () => {
    renderPage();
    expect(screen.getByText("麻雀")).toBeInTheDocument();
  });

  it("コミュニティ名を入力せずに送信すると必須エラーを表示する", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "作成する" }));

    expect(
      await screen.findByText("コミュニティ名を入力してください"),
    ).toBeInTheDocument();
    expect(communityApi.createCommunity).not.toHaveBeenCalled();
  });

  it("正常に作成すると、themeColor未選択はundefinedとして送信し詳細画面へ遷移する", async () => {
    const user = userEvent.setup();
    vi.mocked(communityApi.createCommunity).mockResolvedValue({
      communityId: "community-1",
      name: "週末麻雀部",
      description: "",
      genre: "麻雀",
      memberApprovalRequired: false,
    } satisfies CommunityMutationResult);
    renderPage();

    await user.type(screen.getByLabelText("コミュニティ名"), "週末麻雀部");
    await user.click(screen.getByRole("button", { name: "作成する" }));

    await waitFor(() =>
      expect(communityApi.createCommunity).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "週末麻雀部",
          genre: "麻雀",
          themeColor: undefined,
        }),
      ),
    );
    expect(await screen.findByText("コミュニティ詳細画面")).toBeInTheDocument();
  });

  it("コミュニティ名重複などインライン表示エラーはコミュニティ名欄に表示する", async () => {
    const user = userEvent.setup();
    const { ApiError } = await import("@/api/errors");
    vi.mocked(communityApi.createCommunity).mockRejectedValue(
      new ApiError("INVALID_PARAMETER", "コミュニティ名が不正です", 400),
    );
    renderPage();

    await user.type(screen.getByLabelText("コミュニティ名"), "週末麻雀部");
    await user.click(screen.getByRole("button", { name: "作成する" }));

    expect(await screen.findByText("コミュニティ名が不正です")).toBeInTheDocument();
  });
});
