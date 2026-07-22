import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { ErrorModalProvider } from "@/components/feedback/ErrorModalContext";
import { ProfileEditPage } from "@/features/user/ProfileEditPage";
import { renderWithProviders, screen, waitFor } from "@/test/render";
import type { UserProfile } from "@/features/user/types";

vi.mock("@/features/user/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/user/api")>();
  return { ...actual, getMyProfile: vi.fn(), updateMyProfile: vi.fn(), deleteMyAvatar: vi.fn() };
});

const userApi = await import("@/features/user/api");

function baseProfile(overrides: Partial<UserProfile> = {}): UserProfile {
  return {
    userId: "user-1",
    nickname: "たろう",
    profile: "",
    icon: "",
    gameTypes: ["MAHJONG4"],
    beginnerOk: false,
    autoApprove: false,
    frequencyLimitCount: null,
    frequencyLimitPeriod: null,
    ...overrides,
  };
}

function renderPage() {
  return renderWithProviders(
    <MemoryRouter initialEntries={["/mypage/profile"]}>
      <ErrorModalProvider>
        <Routes>
          <Route path="/mypage/profile" element={<ProfileEditPage />} />
          <Route path="/mypage" element={<p>マイページ</p>} />
        </Routes>
      </ErrorModalProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.resetAllMocks();
});

describe("ProfileEditPage", () => {
  it("読み込み中はスケルトンを表示する", () => {
    vi.mocked(userApi.getMyProfile).mockReturnValue(new Promise(() => {}));

    const { container } = renderPage();

    expect(container.querySelector('[data-slot="skeleton"]')).toBeTruthy();
  });

  it("frequencyLimitCountがnullの場合、上限設定はオフで回数・期間欄は表示しない", async () => {
    vi.mocked(userApi.getMyProfile).mockResolvedValue(baseProfile());

    renderPage();

    await screen.findByLabelText("ニックネーム");
    expect(screen.queryByPlaceholderText("回数")).not.toBeInTheDocument();
  });

  it("frequencyLimitCountが設定済みの場合、上限設定はオンで回数・期間欄に既存値が入る", async () => {
    vi.mocked(userApi.getMyProfile).mockResolvedValue(
      baseProfile({ frequencyLimitCount: 3, frequencyLimitPeriod: "MONTH" }),
    );

    renderPage();

    const countInput = await screen.findByPlaceholderText("回数");
    expect(countInput).toHaveValue(3);
  });

  it("上限設定をオンにすると回数・期間欄が表示される", async () => {
    const user = userEvent.setup();
    vi.mocked(userApi.getMyProfile).mockResolvedValue(baseProfile());

    renderPage();
    await screen.findByLabelText("ニックネーム");
    expect(screen.queryByPlaceholderText("回数")).not.toBeInTheDocument();

    await user.click(screen.getByRole("switch", { name: "参加頻度に上限を設ける" }));

    expect(screen.getByPlaceholderText("回数")).toBeInTheDocument();
  });

  it("上限設定オンで回数未入力のまま保存するとインラインエラーを出し、送信しない", async () => {
    const user = userEvent.setup();
    vi.mocked(userApi.getMyProfile).mockResolvedValue(baseProfile());

    renderPage();
    await screen.findByLabelText("ニックネーム");
    await user.click(screen.getByRole("switch", { name: "参加頻度に上限を設ける" }));
    await user.click(screen.getByRole("button", { name: "保存する" }));

    expect(await screen.findByText("上限回数を入力してください")).toBeInTheDocument();
    expect(userApi.updateMyProfile).not.toHaveBeenCalled();
  });

  it("上限設定をオフのまま保存すると、回数・期間はnullとして送信する", async () => {
    const user = userEvent.setup();
    vi.mocked(userApi.getMyProfile).mockResolvedValue(
      baseProfile({ frequencyLimitCount: 5, frequencyLimitPeriod: "MONTH" }),
    );
    vi.mocked(userApi.updateMyProfile).mockResolvedValue(baseProfile());

    renderPage();
    await screen.findByLabelText("ニックネーム");
    // 既存値ありの状態からオフに切り替える
    await user.click(screen.getByRole("switch", { name: "参加頻度に上限を設ける" }));
    await user.click(screen.getByRole("button", { name: "保存する" }));

    await waitFor(() =>
      expect(userApi.updateMyProfile).toHaveBeenCalledWith(
        expect.objectContaining({ frequencyLimitCount: null, frequencyLimitPeriod: null }),
        expect.anything(),
      ),
    );
  });

  it("上限設定オンで回数を入力して保存すると、その値で送信する", async () => {
    const user = userEvent.setup();
    vi.mocked(userApi.getMyProfile).mockResolvedValue(baseProfile());
    vi.mocked(userApi.updateMyProfile).mockResolvedValue(baseProfile());

    renderPage();
    await screen.findByLabelText("ニックネーム");
    await user.click(screen.getByRole("switch", { name: "参加頻度に上限を設ける" }));
    await user.type(screen.getByPlaceholderText("回数"), "4");
    await user.click(screen.getByRole("button", { name: "保存する" }));

    await waitFor(() =>
      expect(userApi.updateMyProfile).toHaveBeenCalledWith(
        expect.objectContaining({ frequencyLimitCount: 4, frequencyLimitPeriod: "WEEK" }),
        expect.anything(),
      ),
    );
  });

  it("保存に成功するとマイページへ遷移する", async () => {
    const user = userEvent.setup();
    vi.mocked(userApi.getMyProfile).mockResolvedValue(baseProfile());
    vi.mocked(userApi.updateMyProfile).mockResolvedValue(baseProfile());

    renderPage();
    await screen.findByLabelText("ニックネーム");
    await user.click(screen.getByRole("button", { name: "保存する" }));

    expect(await screen.findByText("マイページ")).toBeInTheDocument();
  });

  it("ニックネーム重複などインライン表示エラーはニックネーム欄にエラー表示する", async () => {
    const user = userEvent.setup();
    const { ApiError } = await import("@/api/errors");
    vi.mocked(userApi.getMyProfile).mockResolvedValue(baseProfile());
    vi.mocked(userApi.updateMyProfile).mockRejectedValue(
      new ApiError("DISPLAY_NAME_ALREADY_TAKEN", "このニックネームは既に使用されています", 409),
    );

    renderPage();
    await screen.findByLabelText("ニックネーム");
    await user.click(screen.getByRole("button", { name: "保存する" }));

    expect(
      await screen.findByText("このニックネームは既に使用されています"),
    ).toBeInTheDocument();
  });

  it("プロフィール画像が無い場合は削除ボタンを表示しない", async () => {
    vi.mocked(userApi.getMyProfile).mockResolvedValue(baseProfile({ icon: "" }));

    renderPage();

    await screen.findByLabelText("ニックネーム");
    expect(
      screen.queryByRole("button", { name: "プロフィール画像を削除" }),
    ).not.toBeInTheDocument();
  });

  it("プロフィール画像がある場合、削除ボタンからdeleteMyAvatarを呼べる", async () => {
    const user = userEvent.setup();
    vi.mocked(userApi.getMyProfile).mockResolvedValue(
      baseProfile({ icon: "https://example.com/avatar.png" }),
    );
    vi.mocked(userApi.deleteMyAvatar).mockResolvedValue(baseProfile({ icon: "" }));

    renderPage();
    await screen.findByLabelText("ニックネーム");
    await user.click(screen.getByRole("button", { name: "プロフィール画像を削除" }));

    await waitFor(() => expect(userApi.deleteMyAvatar).toHaveBeenCalled());
  });
});
