import { useQuery } from "@tanstack/react-query";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { apiClient } from "@/api/client";
import { renderWithProviders, screen, waitFor } from "@/test/render";
import { server } from "@/test/msw/server";

/**
 * Phase 0で整備したテスト基盤（MSWサーバー + renderWithProviders）が
 * 実際のリクエスト/レスポンスサイクルを通しで検証できることを確認する。
 * 個別ドメインのテストではなく、基盤自体の疎通確認が目的。
 */
describe("テスト基盤（MSW + renderWithProviders）", () => {
  it("apiClientが統一レスポンス形式のdataを返す", async () => {
    server.use(
      http.get("http://localhost/api/ping", () =>
        HttpResponse.json({ success: true, data: { message: "pong" } }),
      ),
    );

    const result = await apiClient.get<{ message: string }>("/ping");
    expect(result.message).toBe("pong");
  });

  it("useQuery経由のコンポーネントがMSWのレスポンスを描画する", async () => {
    server.use(
      http.get("http://localhost/api/ping", () =>
        HttpResponse.json({ success: true, data: { message: "pong" } }),
      ),
    );

    function PingComponent() {
      const { data } = useQuery({
        queryKey: ["ping"],
        queryFn: () => apiClient.get<{ message: string }>("/ping"),
      });
      return <p>{data?.message ?? "loading"}</p>;
    }

    renderWithProviders(<PingComponent />);

    await waitFor(() => expect(screen.getByText("pong")).toBeInTheDocument());
  });
});
