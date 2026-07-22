import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/test/msw/server";
import { ApiError } from "@/api/errors";
import {
  createCommunity,
  createPlace,
  deletePlace,
  getCommunity,
  listCommunities,
  updateThemeColor,
} from "@/features/community/api";

const BASE = "http://localhost/api";

/**
 * community/api.tsの薄いラッパー群に対する契約テスト。ここで検証した
 * パターン（envelopeのアンラップ・リクエストボディの整形・エラー変換）は
 * 他ドメインのapi.tsも同型のため、必要になった時点で追加する
 * （全ドメインを先回りして書かない）。
 */
describe("community/api", () => {
  it("listCommunities: GET /communities のレスポンスからcommunities配列を取り出す", async () => {
    server.use(
      http.get(`${BASE}/communities`, () =>
        HttpResponse.json({
          success: true,
          data: { communities: [{ communityId: "c1", name: "テスト", role: "OWNER" }] },
        }),
      ),
    );

    const result = await listCommunities();

    expect(result).toEqual([{ communityId: "c1", name: "テスト", role: "OWNER" }]);
  });

  it("getCommunity: GET /communities/{communityId} を正しいパスで呼ぶ", async () => {
    let requestedUrl = "";
    server.use(
      http.get(`${BASE}/communities/:communityId`, ({ request, params }) => {
        requestedUrl = request.url;
        return HttpResponse.json({
          success: true,
          data: { communityId: params.communityId, name: "テスト" },
        });
      }),
    );

    const result = await getCommunity("community-1");

    expect(requestedUrl).toBe(`${BASE}/communities/community-1`);
    expect(result).toMatchObject({ communityId: "community-1" });
  });

  it("createCommunity: POST /communities にリクエストボディをそのまま渡す", async () => {
    let requestBody: unknown;
    server.use(
      http.post(`${BASE}/communities`, async ({ request }) => {
        requestBody = await request.json();
        return HttpResponse.json({
          success: true,
          data: { communityId: "community-1", name: "新規コミュニティ" },
        });
      }),
    );

    const input = {
      name: "新規コミュニティ",
      genre: "麻雀" as const,
      memberApprovalRequired: false,
    };
    const result = await createCommunity(input);

    expect(requestBody).toEqual(input);
    expect(result).toMatchObject({ communityId: "community-1" });
  });

  it("updateThemeColor: PUT /communities/{communityId}/theme-color にthemeColorを渡す", async () => {
    let requestBody: unknown;
    server.use(
      http.put(`${BASE}/communities/:communityId/theme-color`, async ({ request }) => {
        requestBody = await request.json();
        return HttpResponse.json({
          success: true,
          data: { communityId: "community-1", themeColor: "#FF0000" },
        });
      }),
    );

    await updateThemeColor("community-1", "#FF0000");

    expect(requestBody).toEqual({ themeColor: "#FF0000" });
  });

  it("createPlace: 成功エンベロープからPlaceオブジェクトをそのまま返す", async () => {
    server.use(
      http.post(`${BASE}/communities/:communityId/locations`, () =>
        HttpResponse.json({
          success: true,
          data: { placeId: "place-1", name: "たかし宅", address: "", note: "" },
        }),
      ),
    );

    const result = await createPlace("community-1", { name: "たかし宅", address: "", note: "" });

    expect(result).toEqual({ placeId: "place-1", name: "たかし宅", address: "", note: "" });
  });

  it("deletePlace: DELETEメソッドで呼び出す", async () => {
    let method = "";
    server.use(
      http.delete(`${BASE}/communities/:communityId/locations/:placeId`, ({ request }) => {
        method = request.method;
        return HttpResponse.json({ success: true, data: {} });
      }),
    );

    await deletePlace("community-1", "place-1");

    expect(method).toBe("DELETE");
  });

  it("エラーエンベロープはApiError（code/message/status）に変換される", async () => {
    server.use(
      http.get(
        `${BASE}/communities/:communityId`,
        () =>
          HttpResponse.json(
            { success: false, error: { code: "COMMUNITY_NOT_FOUND", message: "コミュニティが見つかりません" } },
            { status: 404 },
          ),
      ),
    );

    await expect(getCommunity("missing-id")).rejects.toMatchObject({
      code: "COMMUNITY_NOT_FOUND",
      message: "コミュニティが見つかりません",
      status: 404,
    } satisfies Partial<ApiError>);
  });
});
