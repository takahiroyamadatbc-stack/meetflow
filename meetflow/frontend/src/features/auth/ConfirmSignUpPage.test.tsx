import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { ConfirmSignUpPage } from "@/features/auth/ConfirmSignUpPage";
import { renderWithProviders, screen, waitFor } from "@/test/render";

vi.mock("@/features/auth/api");
vi.mock("@/features/auth/pendingInvite");
const authApi = await import("@/features/auth/api");
const pendingInvite = await import("@/features/auth/pendingInvite");

function renderPage(state: { email?: string; nickname?: string } | null = { email: "taro@example.com" }) {
  return renderWithProviders(
    <MemoryRouter initialEntries={[{ pathname: "/signup/confirm", state }]}>
      <Routes>
        <Route path="/signup/confirm" element={<ConfirmSignUpPage />} />
        <Route path="/login" element={<p>ログイン画面</p>} />
        <Route path="/" element={<p>ホーム画面</p>} />
        <Route path="/invite/:token" element={<p>招待受諾画面</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

async function submit(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("確認コード"), "123456");
  await user.click(screen.getByRole("button", { name: "確認する" }));
}

afterEach(() => {
  vi.resetAllMocks();
});

describe("ConfirmSignUpPage", () => {
  it("メールアドレスが取得できない場合はエラーを表示し、confirmSignUpCodeを呼ばない", async () => {
    const user = userEvent.setup();
    renderPage(null);

    await submit(user);

    expect(
      await screen.findByText("メールアドレスが取得できませんでした。新規登録からやり直してください"),
    ).toBeInTheDocument();
    expect(authApi.confirmSignUpCode).not.toHaveBeenCalled();
  });

  it("COMPLETE_AUTO_SIGN_IN成功時、保留中の招待パスがあればそちらへ遷移する", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.confirmSignUpCode).mockResolvedValue({
      isSignUpComplete: true,
      nextStep: { signUpStep: "COMPLETE_AUTO_SIGN_IN" },
    } as Awaited<ReturnType<typeof authApi.confirmSignUpCode>>);
    vi.mocked(authApi.completeAutoSignIn).mockResolvedValue(
      {} as Awaited<ReturnType<typeof authApi.completeAutoSignIn>>,
    );
    vi.mocked(pendingInvite.peekPendingInvitePath).mockReturnValue("/invite/abc123");
    renderPage();

    await submit(user);

    await waitFor(() =>
      expect(authApi.confirmSignUpCode).toHaveBeenCalledWith(
        "taro@example.com",
        "123456",
        undefined,
      ),
    );
    expect(await screen.findByText("招待受諾画面")).toBeInTheDocument();
  });

  it("COMPLETE_AUTO_SIGN_IN成功時、保留中の招待パスが無ければホームへ遷移する", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.confirmSignUpCode).mockResolvedValue({
      isSignUpComplete: true,
      nextStep: { signUpStep: "COMPLETE_AUTO_SIGN_IN" },
    } as Awaited<ReturnType<typeof authApi.confirmSignUpCode>>);
    vi.mocked(authApi.completeAutoSignIn).mockResolvedValue(
      {} as Awaited<ReturnType<typeof authApi.completeAutoSignIn>>,
    );
    vi.mocked(pendingInvite.peekPendingInvitePath).mockReturnValue(null);
    renderPage();

    await submit(user);

    expect(await screen.findByText("ホーム画面")).toBeInTheDocument();
  });

  it("COMPLETE_AUTO_SIGN_IN失敗時はログイン画面へフォールバックし、メールアドレス・案内文を引き継ぐ", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.confirmSignUpCode).mockResolvedValue({
      isSignUpComplete: true,
      nextStep: { signUpStep: "COMPLETE_AUTO_SIGN_IN" },
    } as Awaited<ReturnType<typeof authApi.confirmSignUpCode>>);
    vi.mocked(authApi.completeAutoSignIn).mockRejectedValue(new Error("auto sign in failed"));
    renderPage();

    await submit(user);

    expect(await screen.findByText("ログイン画面")).toBeInTheDocument();
  });

  it("signUpStepがCOMPLETE_AUTO_SIGN_IN以外の場合は直接ログイン画面へ遷移する", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.confirmSignUpCode).mockResolvedValue({
      isSignUpComplete: true,
      nextStep: { signUpStep: "DONE" },
    } as Awaited<ReturnType<typeof authApi.confirmSignUpCode>>);
    renderPage();

    await submit(user);

    expect(await screen.findByText("ログイン画面")).toBeInTheDocument();
    expect(authApi.completeAutoSignIn).not.toHaveBeenCalled();
  });

  it("確認コードの検証に失敗した場合はエラーメッセージを表示する", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.confirmSignUpCode).mockRejectedValue(new Error("コードが正しくありません"));
    renderPage();

    await submit(user);

    expect(await screen.findByText("コードが正しくありません")).toBeInTheDocument();
  });

  it("nicknameがstateにある場合はconfirmSignUpCodeに渡す", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.confirmSignUpCode).mockResolvedValue({
      isSignUpComplete: true,
      nextStep: { signUpStep: "DONE" },
    } as Awaited<ReturnType<typeof authApi.confirmSignUpCode>>);
    renderPage({ email: "taro@example.com", nickname: "たろう" });

    await submit(user);

    await waitFor(() =>
      expect(authApi.confirmSignUpCode).toHaveBeenCalledWith(
        "taro@example.com",
        "123456",
        "たろう",
      ),
    );
  });
});
