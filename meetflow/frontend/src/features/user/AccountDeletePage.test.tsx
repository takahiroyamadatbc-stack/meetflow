import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { ErrorModalProvider } from "@/components/feedback/ErrorModalContext";
import { AccountDeletePage } from "@/features/user/AccountDeletePage";
import { renderWithProviders, screen, waitFor } from "@/test/render";

vi.mock("@/features/user/api");
vi.mock("@/features/auth/api");
const userApi = await import("@/features/user/api");
const authApi = await import("@/features/auth/api");

function renderPage() {
  return renderWithProviders(
    <MemoryRouter initialEntries={["/mypage/account-delete"]}>
      <ErrorModalProvider>
        <Routes>
          <Route path="/mypage/account-delete" element={<AccountDeletePage />} />
          <Route path="/login" element={<p>ログイン画面</p>} />
        </Routes>
      </ErrorModalProvider>
    </MemoryRouter>,
  );
}

async function openConfirmDialog(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "アカウントを削除する" }));
  return screen.findByRole("alertdialog");
}

afterEach(() => {
  vi.resetAllMocks();
});

describe("AccountDeletePage", () => {
  it("固定フレーズを入力するまで削除ボタンは無効", async () => {
    const user = userEvent.setup();
    renderPage();

    const dialog = await openConfirmDialog(user);
    const deleteButton = screen.getByRole("button", { name: "削除する" });
    expect(deleteButton).toBeDisabled();

    const input = screen.getByPlaceholderText("削除する");
    await user.type(input, "削除する");

    expect(deleteButton).toBeEnabled();
    expect(dialog).toBeInTheDocument();
  });

  it("一致しないフレーズでは削除ボタンが有効にならない", async () => {
    const user = userEvent.setup();
    renderPage();
    await openConfirmDialog(user);

    await user.type(screen.getByPlaceholderText("削除する"), "けす");

    const deleteButton = screen.getByRole("button", { name: "削除する" });
    expect(deleteButton).toBeDisabled();
  });

  it("正しいフレーズで削除すると、退会後サインアウトしてログイン画面へ遷移する", async () => {
    const user = userEvent.setup();
    vi.mocked(userApi.deleteMyAccount).mockResolvedValue({ userId: "user-1", deleted: true });
    vi.mocked(authApi.signOutUser).mockResolvedValue(undefined);
    renderPage();
    await openConfirmDialog(user);

    await user.type(screen.getByPlaceholderText("削除する"), "削除する");
    const deleteButton = screen.getByRole("button", { name: "削除する" });
    await user.click(deleteButton);

    await waitFor(() => expect(userApi.deleteMyAccount).toHaveBeenCalled());
    await waitFor(() => expect(authApi.signOutUser).toHaveBeenCalled());
    expect(await screen.findByText("ログイン画面")).toBeInTheDocument();
  });

  it("削除に失敗した場合はダイアログを閉じ、入力内容をリセットする", async () => {
    const user = userEvent.setup();
    vi.mocked(userApi.deleteMyAccount).mockRejectedValue(new Error("失敗しました"));
    renderPage();
    await openConfirmDialog(user);

    await user.type(screen.getByPlaceholderText("削除する"), "削除する");
    const deleteButton = screen.getByRole("button", { name: "削除する" });
    await user.click(deleteButton);

    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());

    // 再度開いた際に入力内容がリセットされていることを確認
    await openConfirmDialog(user);
    expect(screen.getByPlaceholderText("削除する")).toHaveValue("");
  });
});
