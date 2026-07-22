import { MemoryRouter, Route, Routes } from "react-router-dom";
import { toast } from "sonner";
import { afterEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { ErrorModalProvider } from "@/components/feedback/ErrorModalContext";
import { EventDetailPage } from "@/features/event/EventDetailPage";
import { renderWithProviders, screen, waitFor, within } from "@/test/render";
import type { CancelRequest, EventDetail, Participant } from "@/features/event/types";
import type { CommunityDetail } from "@/features/community/types";
import type { Candidate } from "@/features/matching/types";

vi.mock("@/features/auth/useAuthUser");
vi.mock("@/features/event/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/event/api")>();
  return {
    ...actual,
    getEvent: vi.fn(),
    listParticipants: vi.fn(),
    listCancelRequests: vi.fn(),
    confirmEvent: vi.fn(),
    cancelEvent: vi.fn(),
    completeEvent: vi.fn(),
    reopenEvent: vi.fn(),
    approveParticipation: vi.fn(),
    rejectParticipation: vi.fn(),
    addParticipant: vi.fn(),
    removeParticipant: vi.fn(),
    updateEventMemo: vi.fn(),
  };
});
vi.mock("@/features/community/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/community/api")>();
  return { ...actual, getCommunity: vi.fn(), listMembers: vi.fn() };
});
vi.mock("@/features/matching/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/matching/api")>();
  return { ...actual, getCandidateDetail: vi.fn() };
});
vi.mock("@/features/result/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/result/api")>();
  return { ...actual, listEventSessions: vi.fn() };
});
vi.mock("@/features/feedback/QuickFeedbackPrompt", () => ({
  QuickFeedbackPrompt: () => null,
}));
vi.mock("@/features/availability/AvailabilitySubmitPrompt", () => ({
  AvailabilitySubmitPrompt: () => null,
}));

const { useAuthUser } = await import("@/features/auth/useAuthUser");
const eventApi = await import("@/features/event/api");
const communityApi = await import("@/features/community/api");
const matchingApi = await import("@/features/matching/api");
const resultApi = await import("@/features/result/api");

const EVENT_ID = "event-1";
const COMMUNITY_ID = "community-1";

function baseEvent(overrides: Partial<EventDetail> = {}): EventDetail {
  return {
    eventId: EVENT_ID,
    communityId: COMMUNITY_ID,
    templateId: "template-1",
    candidateId: "candidate-1",
    status: "CONFIRMED",
    startTime: "2026-08-01T10:00:00+09:00",
    endTime: "2026-08-01T13:00:00+09:00",
    location: null,
    locationNote: "",
    memo: "",
    createdAt: "2026-07-01T00:00:00+09:00",
    ...overrides,
  };
}

function baseCommunity(role: CommunityDetail["role"]): CommunityDetail {
  return {
    communityId: COMMUNITY_ID,
    name: "テストコミュニティ",
    description: "",
    genre: "麻雀",
    memberApprovalRequired: false,
    themeColor: null,
    icon: null,
    role,
    pendingRequestCount: 0,
    rankingDefaultGameType: "MAHJONG4",
    rankingDefaultPeriodType: "ALL_TIME",
    rankingDefaultMetric: "AVERAGE_RANK",
    rankingDefaultMinGames: 0,
  };
}

function setAuthUser(userId: string | null) {
  vi.mocked(useAuthUser).mockReturnValue({
    status: userId ? "authenticated" : "unauthenticated",
    userId,
  });
}

/** 各テストで使わないクエリはローディングのまま止まらないよう空データで解決しておく */
function setupDefaultMocks() {
  vi.mocked(communityApi.listMembers).mockResolvedValue([]);
  vi.mocked(eventApi.listCancelRequests).mockResolvedValue([]);
  vi.mocked(matchingApi.getCandidateDetail).mockResolvedValue({
    candidateId: "candidate-1",
    templateId: null,
    score: null,
    status: "PENDING",
    reasons: [],
    startTime: null,
    endTime: null,
    members: [],
    createdAt: "2026-07-01T00:00:00+09:00",
    gameType: null,
  } satisfies Candidate);
  vi.mocked(resultApi.listEventSessions).mockResolvedValue([]);
}

function renderEventDetailPage() {
  return renderWithProviders(
    <MemoryRouter initialEntries={[`/events/${EVENT_ID}`]}>
      <ErrorModalProvider>
        <Routes>
          <Route path="/events/:eventId" element={<EventDetailPage />} />
        </Routes>
      </ErrorModalProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.resetAllMocks();
});

describe("EventDetailPage", () => {
  it("読み込み中はスケルトンを表示する", () => {
    setAuthUser("user-1");
    vi.mocked(eventApi.getEvent).mockReturnValue(new Promise(() => {}));
    setupDefaultMocks();

    const { container } = renderEventDetailPage();

    expect(container.querySelector('[data-slot="skeleton"]')).toBeTruthy();
  });

  it("イベントが見つからない場合は空状態を表示する", async () => {
    setAuthUser("user-1");
    setupDefaultMocks();
    vi.mocked(eventApi.getEvent).mockRejectedValue(new Error("EVENT_NOT_FOUND"));

    renderEventDetailPage();

    await waitFor(() =>
      expect(screen.getByText("イベントが見つかりません")).toBeInTheDocument(),
    );
  });

  describe("PENDING_APPROVAL（候補メンバーの選択と仮確定）", () => {
    it("候補メンバーは初期状態で全員選択済みで、全員の選択を外すと仮確定ボタンが無効になる", async () => {
      const user = userEvent.setup();
      setAuthUser("admin-1");
      setupDefaultMocks();
      vi.mocked(eventApi.getEvent).mockResolvedValue(
        baseEvent({ status: "PENDING_APPROVAL" }),
      );
      vi.mocked(eventApi.listParticipants).mockResolvedValue([]);
      vi.mocked(communityApi.getCommunity).mockResolvedValue(baseCommunity("OWNER"));
      vi.mocked(matchingApi.getCandidateDetail).mockResolvedValue({
        candidateId: "candidate-1",
        templateId: "template-1",
        score: 80,
        status: "PENDING",
        reasons: [],
        startTime: null,
        endTime: null,
        members: [
          { userId: "m1", nickname: "たろう", fairnessCount: 0, conflictWarning: false },
          { userId: "m2", nickname: "はなこ", fairnessCount: 0, conflictWarning: false },
        ],
        createdAt: "2026-07-01T00:00:00+09:00",
        gameType: "MAHJONG4",
      });

      renderEventDetailPage();

      const confirmButton = await screen.findByRole("button", { name: "このイベントを仮確定する" });
      const taroCheckbox = await screen.findByRole("checkbox", { name: "たろう" });
      const hanakoCheckbox = screen.getByRole("checkbox", { name: "はなこ" });
      expect(taroCheckbox).toBeChecked();
      expect(hanakoCheckbox).toBeChecked();
      expect(confirmButton).toBeEnabled();

      await user.click(taroCheckbox);
      await user.click(hanakoCheckbox);
      expect(confirmButton).toBeDisabled();
    });

    it("仮確定後、全員自動承認済みならCONFIRMED、そうでなければ承認待ちのメッセージを出す", async () => {
      const user = userEvent.setup();
      const toastSuccessSpy = vi.spyOn(toast, "success");
      setAuthUser("admin-1");
      setupDefaultMocks();
      vi.mocked(eventApi.getEvent).mockResolvedValue(
        baseEvent({ status: "PENDING_APPROVAL", candidateId: null }),
      );
      vi.mocked(eventApi.listParticipants).mockResolvedValue([]);
      vi.mocked(communityApi.getCommunity).mockResolvedValue(baseCommunity("OWNER"));
      vi.mocked(eventApi.confirmEvent).mockResolvedValue(
        baseEvent({ status: "AWAITING_MEMBER_APPROVAL", candidateId: null }),
      );

      renderEventDetailPage();

      const confirmButton = await screen.findByRole("button", { name: "このイベントを仮確定する" });
      await user.click(confirmButton);

      await waitFor(() =>
        expect(toastSuccessSpy).toHaveBeenCalledWith(
          "イベントを仮確定しました。参加予定者全員の承認を待っています",
        ),
      );
    });
  });

  describe("AWAITING_MEMBER_APPROVAL", () => {
    it("承認待ちの本人には承認・辞退ボタンを表示する", async () => {
      setAuthUser("user-1");
      setupDefaultMocks();
      vi.mocked(eventApi.getEvent).mockResolvedValue(
        baseEvent({ status: "AWAITING_MEMBER_APPROVAL" }),
      );
      vi.mocked(eventApi.listParticipants).mockResolvedValue([
        { userId: "user-1", nickname: "自分", status: "AWAITING_APPROVAL" },
      ]);
      vi.mocked(communityApi.getCommunity).mockResolvedValue(baseCommunity("MEMBER"));

      renderEventDetailPage();

      expect(await screen.findByRole("button", { name: "参加を承認する" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "参加を辞退する" })).toBeInTheDocument();
    });

    it("管理者には承認済み人数の待機メッセージを表示する", async () => {
      setAuthUser("admin-1");
      setupDefaultMocks();
      vi.mocked(eventApi.getEvent).mockResolvedValue(
        baseEvent({ status: "AWAITING_MEMBER_APPROVAL" }),
      );
      vi.mocked(eventApi.listParticipants).mockResolvedValue([
        { userId: "m1", nickname: "たろう", status: "CONFIRMED" },
        { userId: "m2", nickname: "はなこ", status: "AWAITING_APPROVAL" },
      ]);
      vi.mocked(eventApi.listCancelRequests).mockResolvedValue([]);
      vi.mocked(communityApi.getCommunity).mockResolvedValue(baseCommunity("OWNER"));

      renderEventDetailPage();

      expect(
        await screen.findByText("参加予定者全員の承認をお待ちください（1/2人が承認済み）"),
      ).toBeInTheDocument();
    });
  });

  describe("CONFIRMED", () => {
    it("参加者本人にはキャンセル申請の導線を表示し、参加者削除ボタンは表示しない", async () => {
      setAuthUser("user-1");
      setupDefaultMocks();
      vi.mocked(eventApi.getEvent).mockResolvedValue(baseEvent({ status: "CONFIRMED" }));
      vi.mocked(eventApi.listParticipants).mockResolvedValue([
        { userId: "user-1", nickname: "自分", status: "CONFIRMED" },
      ]);
      vi.mocked(communityApi.getCommunity).mockResolvedValue(baseCommunity("MEMBER"));

      renderEventDetailPage();

      expect(
        await screen.findByRole("button", { name: "参加をキャンセル申請する" }),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /さんを削除/ }),
      ).not.toBeInTheDocument();
    });

    it("管理者には未処理キャンセル申請件数バッジ・成績カード・対局終了/中止ボタンを表示する", async () => {
      setAuthUser("admin-1");
      setupDefaultMocks();
      vi.mocked(eventApi.getEvent).mockResolvedValue(baseEvent({ status: "CONFIRMED" }));
      vi.mocked(eventApi.listParticipants).mockResolvedValue([
        { userId: "m1", nickname: "たろう", status: "CONFIRMED" },
      ]);
      vi.mocked(eventApi.listCancelRequests).mockResolvedValue([
        { userId: "m1", reason: "急用", status: "PENDING", requestedAt: "2026-07-20T00:00:00+09:00" },
      ] satisfies CancelRequest[]);
      vi.mocked(communityApi.getCommunity).mockResolvedValue(baseCommunity("OWNER"));

      renderEventDetailPage();

      const cancelRequestLink = await screen.findByRole("link", { name: /キャンセル申請一覧/ });
      await waitFor(() => expect(within(cancelRequestLink).getByText("1")).toBeInTheDocument());
      expect(screen.getByRole("button", { name: "本日の対局を終了する" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "イベントを中止する" })).toBeInTheDocument();
      expect(screen.getByText("対局成績")).toBeInTheDocument();
    });

    it("参加者を削除し、最低人数を下回った場合は警告トーストを出す", async () => {
      const user = userEvent.setup();
      const toastWarningSpy = vi.spyOn(toast, "warning");
      setAuthUser("admin-1");
      setupDefaultMocks();
      vi.mocked(eventApi.getEvent).mockResolvedValue(baseEvent({ status: "CONFIRMED" }));
      vi.mocked(eventApi.listParticipants).mockResolvedValue([
        { userId: "m1", nickname: "たろう", status: "CONFIRMED" },
      ]);
      vi.mocked(eventApi.listCancelRequests).mockResolvedValue([]);
      vi.mocked(communityApi.getCommunity).mockResolvedValue(baseCommunity("OWNER"));
      vi.mocked(eventApi.removeParticipant).mockResolvedValue({
        eventId: EVENT_ID,
        userId: "m1",
        status: "CANCELLED",
        remainingParticipantCount: 2,
        belowMinPlayers: true,
      });

      renderEventDetailPage();

      const removeButton = await screen.findByRole("button", { name: "たろうさんを削除" });
      await user.click(removeButton);
      const confirmButton = await screen.findByRole("button", { name: "削除する" });
      await user.click(confirmButton);

      await waitFor(() =>
        expect(toastWarningSpy).toHaveBeenCalledWith(
          "参加者を削除しました。参加人数が開催条件の最低人数を下回っています(残り2人)",
        ),
      );
    });
  });

  describe("COMPLETED", () => {
    it("管理者には「開催予定に戻す」ボタンを表示し、確認後にreopenEventを呼ぶ", async () => {
      const user = userEvent.setup();
      setAuthUser("admin-1");
      setupDefaultMocks();
      vi.mocked(eventApi.getEvent).mockResolvedValue(baseEvent({ status: "COMPLETED" }));
      vi.mocked(eventApi.listParticipants).mockResolvedValue([]);
      vi.mocked(communityApi.getCommunity).mockResolvedValue(baseCommunity("OWNER"));
      vi.mocked(eventApi.reopenEvent).mockResolvedValue({ eventId: EVENT_ID, status: "CONFIRMED" });

      renderEventDetailPage();

      const reopenButton = await screen.findByRole("button", { name: "開催予定に戻す" });
      await user.click(reopenButton);
      const confirmButton = await screen.findByRole("button", { name: "開催予定に戻す" });
      await user.click(confirmButton);

      await waitFor(() => expect(eventApi.reopenEvent).toHaveBeenCalledWith(EVENT_ID));
    });
  });

  describe("ひとことメモ", () => {
    it("管理者はメモを編集して保存できる", async () => {
      const user = userEvent.setup();
      setAuthUser("admin-1");
      setupDefaultMocks();
      vi.mocked(eventApi.getEvent).mockResolvedValue(
        baseEvent({ status: "CONFIRMED", memo: "旧メモ" }),
      );
      vi.mocked(eventApi.listParticipants).mockResolvedValue([]);
      vi.mocked(eventApi.listCancelRequests).mockResolvedValue([]);
      vi.mocked(communityApi.getCommunity).mockResolvedValue(baseCommunity("OWNER"));
      vi.mocked(eventApi.updateEventMemo).mockResolvedValue(
        baseEvent({ status: "CONFIRMED", memo: "新しいメモ" }),
      );

      renderEventDetailPage();

      await user.click(await screen.findByRole("button", { name: "編集する" }));
      const textarea = screen.getByPlaceholderText("例：持ち物、集合時間の補足、注意事項など");
      await user.clear(textarea);
      await user.type(textarea, "新しいメモ");
      await user.click(screen.getByRole("button", { name: "保存する" }));

      await waitFor(() =>
        expect(eventApi.updateEventMemo).toHaveBeenCalledWith(EVENT_ID, "新しいメモ"),
      );
    });

    it("メモが無く管理者でもない場合はメモカード自体を表示しない", async () => {
      setAuthUser("user-1");
      setupDefaultMocks();
      vi.mocked(eventApi.getEvent).mockResolvedValue(baseEvent({ status: "CONFIRMED", memo: "" }));
      vi.mocked(eventApi.listParticipants).mockResolvedValue([
        { userId: "user-1", nickname: "自分", status: "CONFIRMED" } satisfies Participant,
      ]);
      vi.mocked(communityApi.getCommunity).mockResolvedValue(baseCommunity("MEMBER"));

      renderEventDetailPage();

      await screen.findByText("参加者");
      expect(screen.queryByText("ひとことメモ")).not.toBeInTheDocument();
    });
  });
});
