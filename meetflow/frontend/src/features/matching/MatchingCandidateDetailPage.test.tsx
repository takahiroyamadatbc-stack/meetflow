import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { ErrorModalProvider } from "@/components/feedback/ErrorModalContext";
import { MatchingCandidateDetailPage } from "@/features/matching/MatchingCandidateDetailPage";
import { renderWithProviders, screen, waitFor, within } from "@/test/render";
import type { CommunityDetail, Place } from "@/features/community/types";
import type { Candidate } from "@/features/matching/types";
import type { EventDetail } from "@/features/event/types";

vi.mock("@/features/community/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/community/api")>();
  return {
    ...actual,
    getCommunity: vi.fn(),
    listPlaces: vi.fn(),
    createPlace: vi.fn(),
    updatePlace: vi.fn(),
    deletePlace: vi.fn(),
  };
});
vi.mock("@/features/matching/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/matching/api")>();
  return { ...actual, getCandidateDetail: vi.fn() };
});
vi.mock("@/features/event/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/event/api")>();
  return { ...actual, createEvent: vi.fn() };
});

const communityApi = await import("@/features/community/api");
const matchingApi = await import("@/features/matching/api");
const eventApi = await import("@/features/event/api");

const COMMUNITY_ID = "community-1";
const CANDIDATE_ID = "candidate-1";

function baseCandidate(overrides: Partial<Candidate> = {}): Candidate {
  return {
    candidateId: CANDIDATE_ID,
    templateId: "template-1",
    score: 80,
    status: "PENDING",
    reasons: ["公平性が高い"],
    startTime: "2026-08-01T19:00:00+09:00",
    endTime: "2026-08-01T22:00:00+09:00",
    members: [
      { userId: "u1", nickname: "たろう", fairnessCount: 0, conflictWarning: false },
      { userId: "u2", nickname: "はなこ", fairnessCount: 0, conflictWarning: true },
    ],
    createdAt: "2026-07-01T00:00:00+09:00",
    gameType: "MAHJONG4",
    ...overrides,
  };
}

function baseCommunity(role: CommunityDetail["role"] = "OWNER"): CommunityDetail {
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

function basePlace(overrides: Partial<Place> = {}): Place {
  return { placeId: "place-1", name: "たかし宅", address: "", note: "全自動卓あり", ...overrides };
}

function setupDefaultMocks() {
  vi.mocked(matchingApi.getCandidateDetail).mockResolvedValue(baseCandidate());
  vi.mocked(communityApi.getCommunity).mockResolvedValue(baseCommunity());
  vi.mocked(communityApi.listPlaces).mockResolvedValue([basePlace()]);
}

function renderPage() {
  return renderWithProviders(
    <MemoryRouter
      initialEntries={[`/communities/${COMMUNITY_ID}/matching/candidates/${CANDIDATE_ID}`]}
    >
      <ErrorModalProvider>
        <Routes>
          <Route
            path="/communities/:communityId/matching/candidates/:candidateId"
            element={<MatchingCandidateDetailPage />}
          />
          <Route path="/events/:eventId" element={<p>イベント詳細画面</p>} />
        </Routes>
      </ErrorModalProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.resetAllMocks();
});

describe("MatchingCandidateDetailPage", () => {
  it("読み込み中はスケルトンを表示する", () => {
    setupDefaultMocks();
    vi.mocked(matchingApi.getCandidateDetail).mockReturnValue(new Promise(() => {}));

    const { container } = renderPage();

    expect(container.querySelector('[data-slot="skeleton"]')).toBeTruthy();
  });

  it("候補が見つからない場合は空状態を表示する", async () => {
    setupDefaultMocks();
    vi.mocked(matchingApi.getCandidateDetail).mockRejectedValue(new Error("not found"));

    renderPage();

    expect(await screen.findByText("候補が見つかりません")).toBeInTheDocument();
  });

  describe("review（候補確認）", () => {
    it("スコア・重複警告バッジ・生成理由を表示し、PENDINGなら「この候補で作成する」を表示する", async () => {
      setupDefaultMocks();

      renderPage();

      expect(await screen.findByText("80点")).toBeInTheDocument();
      expect(screen.getByText("公平性が高い")).toBeInTheDocument();
      expect(screen.getByText("重複の可能性")).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "この候補で作成する" }),
      ).toBeInTheDocument();
    });

    it("PENDING以外の候補では「既にイベント化されています」と表示し、作成ボタンは出さない", async () => {
      setupDefaultMocks();
      vi.mocked(matchingApi.getCandidateDetail).mockResolvedValue(
        baseCandidate({ status: "CONFIRMED" }),
      );

      renderPage();

      expect(
        await screen.findByText("この候補は既にイベント化されています"),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "この候補で作成する" }),
      ).not.toBeInTheDocument();
    });

    it("手動作成候補（score=null）は「手動作成」と表示する", async () => {
      setupDefaultMocks();
      vi.mocked(matchingApi.getCandidateDetail).mockResolvedValue(
        baseCandidate({ score: null }),
      );

      renderPage();

      expect(await screen.findByText("手動作成")).toBeInTheDocument();
    });
  });

  describe("place（会場選択）", () => {
    async function goToPlaceStep(user: ReturnType<typeof userEvent.setup>) {
      renderPage();
      await user.click(await screen.findByRole("button", { name: "この候補で作成する" }));
      await screen.findByText("会場を選択してください");
    }

    it("会場一覧を表示し、管理者には編集・削除ボタンを表示する", async () => {
      const user = userEvent.setup();
      setupDefaultMocks();

      await goToPlaceStep(user);

      expect(screen.getByText("たかし宅")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "編集" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "削除" })).toBeInTheDocument();
    });

    it("管理者でない場合は編集・削除ボタンを表示しない", async () => {
      const user = userEvent.setup();
      setupDefaultMocks();
      vi.mocked(communityApi.getCommunity).mockResolvedValue(baseCommunity("MEMBER"));

      await goToPlaceStep(user);

      expect(screen.queryByRole("button", { name: "編集" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "削除" })).not.toBeInTheDocument();
    });

    it("会場を削除すると確認ダイアログを経てdeletePlaceを呼ぶ", async () => {
      const user = userEvent.setup();
      setupDefaultMocks();
      vi.mocked(communityApi.deletePlace).mockResolvedValue(undefined);

      await goToPlaceStep(user);
      await user.click(screen.getByRole("button", { name: "削除" }));
      const dialog = await screen.findByRole("alertdialog");
      await user.click(within(dialog).getByRole("button", { name: "削除する" }));

      await waitFor(() =>
        expect(communityApi.deletePlace).toHaveBeenCalledWith(COMMUNITY_ID, "place-1"),
      );
    });

    it("会場編集フォームは既存の値で初期化され、保存するとupdatePlaceを呼ぶ", async () => {
      const user = userEvent.setup();
      setupDefaultMocks();
      vi.mocked(communityApi.updatePlace).mockResolvedValue(basePlace());

      const { container } = renderPage();
      await user.click(await screen.findByRole("button", { name: "この候補で作成する" }));
      await screen.findByText("会場を選択してください");
      await user.click(screen.getByRole("button", { name: "編集" }));

      const nameInput = container.querySelector('input[name="name"]') as HTMLInputElement;
      expect(nameInput).toHaveValue("たかし宅");
      await user.clear(nameInput);
      await user.type(nameInput, "新会場");
      await user.click(screen.getByRole("button", { name: "保存する" }));

      await waitFor(() =>
        expect(communityApi.updatePlace).toHaveBeenCalledWith(COMMUNITY_ID, "place-1", {
          name: "新会場",
          address: "",
          note: "全自動卓あり",
        }),
      );
    });

    it("新しい会場を登録すると自動的に選択状態になる", async () => {
      const user = userEvent.setup();
      setupDefaultMocks();
      const newPlace = basePlace({ placeId: "place-2", name: "新会場", note: "" });
      vi.mocked(communityApi.createPlace).mockResolvedValue(newPlace);
      // 作成成功時にinvalidateQueriesで再取得が走るため、2回目以降は新会場を含めて返す
      vi.mocked(communityApi.listPlaces)
        .mockResolvedValueOnce([basePlace()])
        .mockResolvedValue([basePlace(), newPlace]);

      const { container } = renderPage();
      await user.click(await screen.findByRole("button", { name: "この候補で作成する" }));
      await screen.findByText("会場を選択してください");
      await user.click(screen.getByRole("button", { name: "＋新しい会場を登録する" }));
      const nameInput = container.querySelector('input[name="name"]') as HTMLInputElement;
      await user.type(nameInput, "新会場");
      await user.click(screen.getByRole("button", { name: "会場を登録する" }));

      await waitFor(() => expect(communityApi.createPlace).toHaveBeenCalled());
      // 作成成功後は選択状態(border-primary)になっていることをconfirmステップの表示で確認する
      await user.click(await screen.findByRole("button", { name: "次へ" }));
      expect(await screen.findByText("会場：新会場")).toBeInTheDocument();
    });
  });

  describe("confirm（作成確認）", () => {
    async function goToConfirmStep(user: ReturnType<typeof userEvent.setup>) {
      renderPage();
      await user.click(await screen.findByRole("button", { name: "この候補で作成する" }));
      await screen.findByText("会場を選択してください");
      await user.click(screen.getByText("たかし宅"));
      await user.click(screen.getByRole("button", { name: "次へ" }));
      await screen.findByText(/参加者：/);
    }

    it("選択した会場・参加者一覧を表示し、作成するとcreateEventにcandidateId/locationIdを渡す", async () => {
      const user = userEvent.setup();
      setupDefaultMocks();
      vi.mocked(eventApi.createEvent).mockResolvedValue({
        eventId: "new-event-1",
      } as EventDetail);

      await goToConfirmStep(user);

      expect(screen.getByText("会場：たかし宅")).toBeInTheDocument();
      expect(screen.getByText("参加者：たろう、はなこ")).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: "このイベントを作成する" }));

      await waitFor(() =>
        expect(eventApi.createEvent).toHaveBeenCalledWith({
          candidateId: CANDIDATE_ID,
          locationId: "place-1",
          locationNote: undefined,
        }),
      );
    });

    it("作成に成功すると作成されたイベントの詳細画面へ遷移する", async () => {
      const user = userEvent.setup();
      setupDefaultMocks();
      vi.mocked(eventApi.createEvent).mockResolvedValue({
        eventId: "new-event-1",
      } as EventDetail);

      await goToConfirmStep(user);
      await user.click(screen.getByRole("button", { name: "このイベントを作成する" }));

      await waitFor(() => expect(screen.getByText("イベント詳細画面")).toBeInTheDocument());
    });

    it("「戻る」を押すと会場選択ステップに戻る", async () => {
      const user = userEvent.setup();
      setupDefaultMocks();

      await goToConfirmStep(user);
      await user.click(screen.getByRole("button", { name: "戻る" }));

      expect(await screen.findByText("会場を選択してください")).toBeInTheDocument();
    });
  });
});
