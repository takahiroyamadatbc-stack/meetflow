import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { SignUpPage } from "@/features/auth/SignUpPage";
import { renderWithProviders, screen, waitFor } from "@/test/render";

vi.mock("@/features/auth/api");
const authApi = await import("@/features/auth/api");

function renderPage() {
  return renderWithProviders(
    <MemoryRouter initialEntries={["/signup"]}>
      <Routes>
        <Route path="/signup" element={<SignUpPage />} />
        <Route path="/signup/confirm" element={<p>確認コード入力画面</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

async function fillValidForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("ニックネーム"), "たろう");
  await user.type(screen.getByLabelText("メールアドレス"), "taro@example.com");
  await user.type(screen.getByLabelText("パスワード"), "Passw0rd");
  await user.type(screen.getByLabelText("パスワード（確認用）"), "Passw0rd");
}

afterEach(() => {
  vi.resetAllMocks();
});

describe("SignUpPage", () => {
  it("パスワードと確認用パスワードが一致しない場合はエラーを表示し、送信しない", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText("ニックネーム"), "たろう");
    await user.type(screen.getByLabelText("メールアドレス"), "taro@example.com");
    await user.type(screen.getByLabelText("パスワード"), "Passw0rd");
    await user.type(screen.getByLabelText("パスワード（確認用）"), "Different1");
    await user.click(screen.getByRole("button", { name: "登録する" }));

    expect(await screen.findByText("パスワードが一致しません")).toBeInTheDocument();
    expect(authApi.signUpUser).not.toHaveBeenCalled();
  });

  it("正常に送信すると確認コード入力画面へ遷移する", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.signUpUser).mockResolvedValue(
      {} as Awaited<ReturnType<typeof authApi.signUpUser>>,
    );
    renderPage();

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: "登録する" }));

    await waitFor(() =>
      expect(authApi.signUpUser).toHaveBeenCalledWith(
        "taro@example.com",
        "Passw0rd",
        "たろう",
      ),
    );
    expect(await screen.findByText("確認コード入力画面")).toBeInTheDocument();
  });

  it("UsernameExistsExceptionの場合、確認コードを再送信して確認コード画面へ遷移する（Issue #61）", async () => {
    const user = userEvent.setup();
    const err = new Error("already exists");
    err.name = "UsernameExistsException";
    vi.mocked(authApi.signUpUser).mockRejectedValue(err);
    vi.mocked(authApi.resendSignUpConfirmationCode).mockResolvedValue(
      {} as Awaited<ReturnType<typeof authApi.resendSignUpConfirmationCode>>,
    );
    renderPage();

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: "登録する" }));

    await waitFor(() =>
      expect(authApi.resendSignUpConfirmationCode).toHaveBeenCalledWith("taro@example.com"),
    );
    expect(await screen.findByText("確認コード入力画面")).toBeInTheDocument();
  });

  it("UsernameExistsExceptionかつ再送信にも失敗した場合は「登録済み」エラーを表示する", async () => {
    const user = userEvent.setup();
    const err = new Error("already exists");
    err.name = "UsernameExistsException";
    vi.mocked(authApi.signUpUser).mockRejectedValue(err);
    vi.mocked(authApi.resendSignUpConfirmationCode).mockRejectedValue(new Error("already confirmed"));
    renderPage();

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: "登録する" }));

    expect(
      await screen.findByText("このメールアドレスは登録済みです"),
    ).toBeInTheDocument();
  });

  it("その他のエラーはメッセージをそのまま表示する", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.signUpUser).mockRejectedValue(new Error("ネットワークエラー"));
    renderPage();

    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: "登録する" }));

    expect(await screen.findByText("ネットワークエラー")).toBeInTheDocument();
  });
});
