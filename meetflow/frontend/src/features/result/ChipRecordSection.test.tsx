import { afterEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { ErrorModalProvider } from "@/components/feedback/ErrorModalContext";
import { ChipRecordSection } from "@/features/result/ChipRecordSection";
import { renderWithProviders, screen, waitFor, within } from "@/test/render";
import type { ChipRecord } from "@/features/result/types";

vi.mock("@/features/result/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/result/api")>();
  return {
    ...actual,
    createChipRecord: vi.fn(),
    updateChipRecord: vi.fn(),
    deleteChipRecord: vi.fn(),
  };
});

const resultApi = await import("@/features/result/api");

const EVENT_ID = "event-1";
const ROWS = [
  { userId: "u1", nickname: "たろう" },
  { userId: "u2", nickname: "はなこ" },
  { userId: "u3", nickname: "じろう" },
];
const NICKNAMES = new Map(ROWS.map((r) => [r.userId, r.nickname]));

function record(overrides: Partial<ChipRecord> = {}): ChipRecord {
  return {
    eventId: EVENT_ID,
    recordNo: "0001",
    gameType: "MAHJONG4",
    recordedAt: "2026-10-11T12:00:00.000Z",
    chips: [
      { userId: "u1", chipCount: 3 },
      { userId: "u2", chipCount: -3 },
    ],
    chipTotal: 0,
    ...overrides,
  };
}

function renderSection({
  chipRecords = [],
  isAdmin = true,
}: { chipRecords?: ChipRecord[]; isAdmin?: boolean } = {}) {
  return renderWithProviders(
    <ErrorModalProvider>
      <ChipRecordSection
        eventId={EVENT_ID}
        rows={ROWS}
        isAdmin={isAdmin}
        chipRecords={chipRecords}
        nicknameByUserId={NICKNAMES}
        defaultGameType="MAHJONG3"
      />
    </ErrorModalProvider>,
  );
}

afterEach(() => {
  vi.resetAllMocks();
});

describe("ChipRecordSection（Issue #116）", () => {
  it("合計が±0の場合はそのまま記録し、0枚の参加者は送らない", async () => {
    const user = userEvent.setup();
    vi.mocked(resultApi.createChipRecord).mockResolvedValue(record());

    renderSection();

    await user.type(screen.getByLabelText("たろう"), "5");
    await user.type(screen.getByLabelText("はなこ"), "-5");
    expect(screen.queryByText(/チップの合計が/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "チップを記録する" }));

    await waitFor(() =>
      expect(resultApi.createChipRecord).toHaveBeenCalledWith(EVENT_ID, {
        gameType: "MAHJONG3",
        chips: [
          { userId: "u1", chipCount: 5 },
          { userId: "u2", chipCount: -5 },
        ],
      }),
    );
    await waitFor(() => expect(screen.getByLabelText("たろう")).toHaveValue(null));
  });

  it("合計が±0でない場合は警告を出し、確認ダイアログを経て登録できる", async () => {
    const user = userEvent.setup();
    vi.mocked(resultApi.createChipRecord).mockResolvedValue(record({ chipTotal: 2 }));

    renderSection();

    await user.click(screen.getByRole("button", { name: "四人麻雀" }));
    await user.type(screen.getByLabelText("たろう"), "5");
    await user.type(screen.getByLabelText("はなこ"), "-3");

    expect(
      screen.getByText("チップの合計が+2枚です。±0になっているかご確認ください（登録は可能です）。"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "チップを記録する" }));

    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText("チップの合計が+2枚です。本当によろしいですか？")).toBeInTheDocument();
    expect(resultApi.createChipRecord).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "このまま登録する" }));

    await waitFor(() =>
      expect(resultApi.createChipRecord).toHaveBeenCalledWith(EVENT_ID, {
        gameType: "MAHJONG4",
        chips: [
          { userId: "u1", chipCount: 5 },
          { userId: "u2", chipCount: -3 },
        ],
      }),
    );
  });

  it("入力が無い場合は記録できない", () => {
    renderSection();

    expect(screen.getByRole("button", { name: "チップを記録する" })).toBeDisabled();
  });

  it("記録済みのチップを一覧表示し、合計が±0でない記録には警告を出す", () => {
    renderSection({
      chipRecords: [
        record(),
        record({
          recordNo: "0002",
          gameType: "MAHJONG3",
          chips: [{ userId: "u3", chipCount: -1 }],
          chipTotal: -1,
        }),
      ],
    });

    expect(screen.getByText("チップ記録1（四人麻雀）")).toBeInTheDocument();
    expect(screen.getByText("+3枚")).toBeInTheDocument();
    expect(screen.getByText("チップ記録2（三人麻雀）")).toBeInTheDocument();
    expect(screen.getByText("チップの合計が-1枚です（±0になっていません）")).toBeInTheDocument();
  });

  it("管理者は記録を編集できる", async () => {
    const user = userEvent.setup();
    vi.mocked(resultApi.updateChipRecord).mockResolvedValue(record());

    renderSection({ chipRecords: [record()] });

    await user.click(screen.getByRole("button", { name: "編集" }));
    // 編集フォームと新規記録フォームの両方に入力欄があるため、先頭（編集フォーム）を使う
    const taro = screen.getAllByLabelText("たろう")[0];
    expect(taro).toHaveValue(3);
    await user.clear(taro);
    await user.type(taro, "4");
    const hanako = screen.getAllByLabelText("はなこ")[0];
    await user.clear(hanako);
    await user.type(hanako, "-4");
    await user.click(screen.getByRole("button", { name: "更新する" }));

    await waitFor(() =>
      expect(resultApi.updateChipRecord).toHaveBeenCalledWith(EVENT_ID, "0001", {
        gameType: "MAHJONG4",
        chips: [
          { userId: "u1", chipCount: 4 },
          { userId: "u2", chipCount: -4 },
        ],
      }),
    );
  });

  it("管理者は確認ダイアログを経て記録を削除できる", async () => {
    const user = userEvent.setup();
    vi.mocked(resultApi.deleteChipRecord).mockResolvedValue({
      eventId: EVENT_ID,
      recordNo: "0001",
    });

    renderSection({ chipRecords: [record()] });

    await user.click(screen.getByRole("button", { name: "削除" }));
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "削除する" }));

    await waitFor(() =>
      expect(resultApi.deleteChipRecord).toHaveBeenCalledWith(EVENT_ID, "0001"),
    );
  });

  it("管理者でない場合は編集・削除の導線を出さない", () => {
    renderSection({ chipRecords: [record()], isAdmin: false });

    expect(screen.queryByRole("button", { name: "編集" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "削除" })).not.toBeInTheDocument();
  });
});
