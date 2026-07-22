import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { PasswordResetPage } from "@/features/auth/PasswordResetPage";
import { renderWithProviders, screen, waitFor } from "@/test/render";

vi.mock("@/features/auth/api");
const authApi = await import("@/features/auth/api");

function renderPage() {
  return renderWithProviders(
    <MemoryRouter initialEntries={["/password-reset"]}>
      <Routes>
        <Route path="/password-reset" element={<PasswordResetPage />} />
        <Route path="/login" element={<p>ログイン画面</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

async function submitEmailStep(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("メールアドレス"), "taro@example.com");
  await user.click(screen.getByRole("button", { name: "確認コードを送信する" }));
  await screen.findByLabelText("確認コード");
}

afterEach(() => {
  vi.resetAllMocks();
});

describe("PasswordResetPage", () => {
  it("メール送信に成功すると確認コード・新パスワード入力欄に切り替わる", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.requestPasswordReset).mockResolvedValue(
      {} as Awaited<ReturnType<typeof authApi.requestPasswordReset>>,
    );
    renderPage();

    await submitEmailStep(user);

    expect(screen.getByLabelText("新しいパスワード")).toBeInTheDocument();
    expect(
      screen.getByText("taro@example.com宛に届いた確認コードと、新しいパスワードを入力してください。"),
    ).toBeInTheDocument();
  });

  // Issue #100: メールアドレス入力ステップと確認コード入力ステップの<Form>が
  // 同じツリー位置・同じコンポーネント型のためReactに同一インスタンス扱いされ、
  // 確認コード欄に入力できなくなるバグがあった（key追加で修正済み）。
  // このテストは実際にユーザーが入力できることを回帰確認する。
  it("確認コード・新パスワード欄に実際に入力できる（Issue #100の回帰確認）", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.requestPasswordReset).mockResolvedValue(
      {} as Awaited<ReturnType<typeof authApi.requestPasswordReset>>,
    );
    renderPage();
    await submitEmailStep(user);

    await user.type(screen.getByLabelText("確認コード"), "123456");
    await user.type(screen.getByLabelText("新しいパスワード"), "Passw0rd");

    expect(screen.getByLabelText("確認コード")).toHaveValue("123456");
    expect(screen.getByLabelText("新しいパスワード")).toHaveValue("Passw0rd");
  });

  it("新パスワードと確認用パスワードが一致しない場合はエラーを表示し送信しない", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.requestPasswordReset).mockResolvedValue(
      {} as Awaited<ReturnType<typeof authApi.requestPasswordReset>>,
    );
    renderPage();
    await submitEmailStep(user);

    await user.type(screen.getByLabelText("確認コード"), "123456");
    await user.type(screen.getByLabelText("新しいパスワード"), "Passw0rd");
    await user.type(screen.getByLabelText("新しいパスワード（確認用）"), "Different1");
    await user.click(screen.getByRole("button", { name: "パスワードを再設定する" }));

    expect(await screen.findByText("パスワードが一致しません")).toBeInTheDocument();
    expect(authApi.confirmPasswordReset).not.toHaveBeenCalled();
  });

  it("CodeMismatchExceptionの場合は確認コード不正のメッセージを表示する", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.requestPasswordReset).mockResolvedValue(
      {} as Awaited<ReturnType<typeof authApi.requestPasswordReset>>,
    );
    const err = new Error("mismatch");
    err.name = "CodeMismatchException";
    vi.mocked(authApi.confirmPasswordReset).mockRejectedValue(err);
    renderPage();
    await submitEmailStep(user);

    await user.type(screen.getByLabelText("確認コード"), "123456");
    await user.type(screen.getByLabelText("新しいパスワード"), "Passw0rd");
    await user.type(screen.getByLabelText("新しいパスワード（確認用）"), "Passw0rd");
    await user.click(screen.getByRole("button", { name: "パスワードを再設定する" }));

    expect(await screen.findByText("確認コードが正しくありません")).toBeInTheDocument();
  });

  it("ExpiredCodeExceptionの場合は有効期限切れのメッセージを表示する", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.requestPasswordReset).mockResolvedValue(
      {} as Awaited<ReturnType<typeof authApi.requestPasswordReset>>,
    );
    const err = new Error("expired");
    err.name = "ExpiredCodeException";
    vi.mocked(authApi.confirmPasswordReset).mockRejectedValue(err);
    renderPage();
    await submitEmailStep(user);

    await user.type(screen.getByLabelText("確認コード"), "123456");
    await user.type(screen.getByLabelText("新しいパスワード"), "Passw0rd");
    await user.type(screen.getByLabelText("新しいパスワード（確認用）"), "Passw0rd");
    await user.click(screen.getByRole("button", { name: "パスワードを再設定する" }));

    expect(
      await screen.findByText("確認コードの有効期限が切れています。もう一度最初からやり直してください"),
    ).toBeInTheDocument();
  });

  it("再設定に成功するとログイン画面へ遷移し、メールアドレス・案内文を引き継ぐ", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.requestPasswordReset).mockResolvedValue(
      {} as Awaited<ReturnType<typeof authApi.requestPasswordReset>>,
    );
    vi.mocked(authApi.confirmPasswordReset).mockResolvedValue(undefined);
    renderPage();
    await submitEmailStep(user);

    await user.type(screen.getByLabelText("確認コード"), "123456");
    await user.type(screen.getByLabelText("新しいパスワード"), "Passw0rd");
    await user.type(screen.getByLabelText("新しいパスワード（確認用）"), "Passw0rd");
    await user.click(screen.getByRole("button", { name: "パスワードを再設定する" }));

    await waitFor(() =>
      expect(authApi.confirmPasswordReset).toHaveBeenCalledWith(
        "taro@example.com",
        "123456",
        "Passw0rd",
      ),
    );
    expect(await screen.findByText("ログイン画面")).toBeInTheDocument();
  });
});
