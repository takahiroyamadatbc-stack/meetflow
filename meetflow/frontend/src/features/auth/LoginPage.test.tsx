import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { LoginPage } from "@/features/auth/LoginPage";
import { renderWithProviders, screen } from "@/test/render";

vi.mock("@/features/auth/api");
vi.mock("@/features/auth/pendingInvite");
const authApi = await import("@/features/auth/api");
const pendingInvite = await import("@/features/auth/pendingInvite");

function renderPage(initialEntry: { pathname: string; state?: unknown } = { pathname: "/login" }) {
  return renderWithProviders(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup/confirm" element={<p>確認コード入力画面</p>} />
        <Route path="/" element={<p>ホーム画面</p>} />
        <Route path="/invite/:token" element={<p>招待受諾画面</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("メールアドレス"), "taro@example.com");
  await user.type(screen.getByLabelText("パスワード"), "Passw0rd");
  await user.click(screen.getByRole("button", { name: "ログイン" }));
}

afterEach(() => {
  vi.resetAllMocks();
});

describe("LoginPage", () => {
  it("保留中の招待パスが無ければホームへ遷移する", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.signInUser).mockResolvedValue(
      {} as Awaited<ReturnType<typeof authApi.signInUser>>,
    );
    vi.mocked(pendingInvite.peekPendingInvitePath).mockReturnValue(null);
    renderPage();

    await fillAndSubmit(user);

    expect(await screen.findByText("ホーム画面")).toBeInTheDocument();
  });

  it("保留中の招待パスがあれば優先してそちらへ遷移する", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.signInUser).mockResolvedValue(
      {} as Awaited<ReturnType<typeof authApi.signInUser>>,
    );
    vi.mocked(pendingInvite.peekPendingInvitePath).mockReturnValue("/invite/abc123");
    renderPage();

    await fillAndSubmit(user);

    expect(await screen.findByText("招待受諾画面")).toBeInTheDocument();
  });

  it("UserNotConfirmedExceptionの場合は確認コード入力画面へ遷移する", async () => {
    const user = userEvent.setup();
    const err = new Error("not confirmed");
    err.name = "UserNotConfirmedException";
    vi.mocked(authApi.signInUser).mockRejectedValue(err);
    renderPage();

    await fillAndSubmit(user);

    expect(await screen.findByText("確認コード入力画面")).toBeInTheDocument();
  });

  it("NotAuthorizedExceptionの場合はメールアドレス/パスワード不一致のメッセージを表示する", async () => {
    const user = userEvent.setup();
    const err = new Error("bad credentials");
    err.name = "NotAuthorizedException";
    vi.mocked(authApi.signInUser).mockRejectedValue(err);
    renderPage();

    await fillAndSubmit(user);

    expect(
      await screen.findByText("メールアドレスまたはパスワードが違います"),
    ).toBeInTheDocument();
  });

  it("locationStateにinfoMessageがある場合は案内文を表示する", () => {
    renderPage({ pathname: "/login", state: { infoMessage: "アカウントを確認しました" } });

    expect(screen.getByText("アカウントを確認しました")).toBeInTheDocument();
  });
});
