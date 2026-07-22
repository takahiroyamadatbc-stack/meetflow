import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EmptyState } from "./EmptyState";

describe("EmptyState", () => {
  it("messageを表示する", () => {
    render(<EmptyState message="コミュニティが見つかりません" />);
    expect(screen.getByText("コミュニティが見つかりません")).toBeInTheDocument();
  });

  it("descriptionが無い場合は表示しない", () => {
    render(<EmptyState message="コミュニティが見つかりません" />);
    expect(screen.queryByText(/参加できます/)).not.toBeInTheDocument();
  });

  it("descriptionがある場合は表示する", () => {
    render(
      <EmptyState
        message="コミュニティが見つかりません"
        description="招待URLから参加できます"
      />,
    );
    expect(screen.getByText("招待URLから参加できます")).toBeInTheDocument();
  });

  it("actionが渡された場合は描画する", () => {
    render(<EmptyState message="コミュニティが見つかりません" action={<button>再読み込み</button>} />);
    expect(screen.getByRole("button", { name: "再読み込み" })).toBeInTheDocument();
  });
});
