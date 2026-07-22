import { describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { renderWithProviders, screen } from "@/test/render";
import { TimeSlotSheet } from "@/features/availability/components/TimeSlotSheet";

describe("TimeSlotSheet", () => {
  it("初期値（19:00〜22:00）は妥当な範囲のため登録ボタンが有効", () => {
    const onSubmit = vi.fn();
    renderWithProviders(
      <TimeSlotSheet open onOpenChange={() => {}} selectedDateCount={2} onSubmit={onSubmit} />,
    );

    expect(screen.getByRole("button", { name: "登録する" })).toBeEnabled();
    expect(
      screen.queryByText("終了時刻は開始時刻より後にしてください"),
    ).not.toBeInTheDocument();
  });

  it("終了時刻が開始時刻以前の場合、登録ボタンを無効化しエラーメッセージを表示する（Issue #99）", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderWithProviders(
      <TimeSlotSheet open onOpenChange={() => {}} selectedDateCount={2} onSubmit={onSubmit} />,
    );

    const endHourInput = screen.getByLabelText("終了時刻");
    await user.clear(endHourInput);
    await user.type(endHourInput, "18:00");

    expect(screen.getByRole("button", { name: "登録する" })).toBeDisabled();
    expect(
      screen.getByText("終了時刻は開始時刻より後にしてください"),
    ).toBeInTheDocument();
    expect(endHourInput).toHaveAttribute("aria-invalid", "true");

    await user.click(screen.getByRole("button", { name: "登録する" }));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("開始時刻と終了時刻が同じ場合も無効（範囲として不正）", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <TimeSlotSheet open onOpenChange={() => {}} selectedDateCount={2} onSubmit={vi.fn()} />,
    );

    const endHourInput = screen.getByLabelText("終了時刻");
    await user.clear(endHourInput);
    await user.type(endHourInput, "19:00");

    expect(screen.getByRole("button", { name: "登録する" })).toBeDisabled();
  });

  it("不正な範囲を修正すると再び登録ボタンが有効になり、値を渡して送信できる", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderWithProviders(
      <TimeSlotSheet open onOpenChange={() => {}} selectedDateCount={2} onSubmit={onSubmit} />,
    );

    const endHourInput = screen.getByLabelText("終了時刻");
    await user.clear(endHourInput);
    await user.type(endHourInput, "18:00");
    expect(screen.getByRole("button", { name: "登録する" })).toBeDisabled();

    await user.clear(endHourInput);
    await user.type(endHourInput, "23:00");
    const submitButton = screen.getByRole("button", { name: "登録する" });
    expect(submitButton).toBeEnabled();

    await user.click(submitButton);
    expect(onSubmit).toHaveBeenCalledWith({
      startHour: "19:00",
      endHour: "23:00",
      gameTypes: [],
      comment: "",
    });
  });

  it("編集モードではタイトル・ボタンラベルが変わり、initialValueが初期表示される", () => {
    renderWithProviders(
      <TimeSlotSheet
        open
        onOpenChange={() => {}}
        selectedDateCount={1}
        onSubmit={vi.fn()}
        isEditMode
        initialValue={{
          startHour: "20:00",
          endHour: "23:30",
          gameTypes: ["MAHJONG4"],
          comment: "よろしくお願いします",
        }}
      />,
    );

    expect(screen.getByText("空き予定を編集")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "変更を保存する" })).toBeEnabled();
    expect(screen.getByLabelText("開始時刻")).toHaveValue("20:00");
    expect(screen.getByLabelText("終了時刻")).toHaveValue("23:30");
    expect(screen.getByLabelText("コメント（任意）")).toHaveValue("よろしくお願いします");
  });
});
