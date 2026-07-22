import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/test/msw/server";
import {
  confirmEvent,
  createEvent,
  getEvent,
  listMyEvents,
  listParticipants,
  removeParticipant,
} from "@/features/event/api";

const BASE = "http://localhost/api";

/** event/api.tsの契約テスト。community/api.tsと同型のパターンのため、代表的な数関数のみ検証する。 */
describe("event/api", () => {
  it("listMyEvents: GET /users/me/events のレスポンスからevents配列を取り出す", async () => {
    server.use(
      http.get(`${BASE}/users/me/events`, () =>
        HttpResponse.json({
          success: true,
          data: { events: [{ eventId: "event-1", communityId: "community-1" }] },
        }),
      ),
    );

    const result = await listMyEvents();

    expect(result).toEqual([{ eventId: "event-1", communityId: "community-1" }]);
  });

  it("createEvent: POST /events にリクエストボディをそのまま渡す", async () => {
    let requestBody: unknown;
    server.use(
      http.post(`${BASE}/events`, async ({ request }) => {
        requestBody = await request.json();
        return HttpResponse.json({ success: true, data: { eventId: "event-1" } });
      }),
    );

    const input = { candidateId: "candidate-1", locationId: "place-1" };
    const result = await createEvent(input);

    expect(requestBody).toEqual(input);
    expect(result).toMatchObject({ eventId: "event-1" });
  });

  it("getEvent: GET /events/{eventId} を正しいパスで呼ぶ", async () => {
    let requestedUrl = "";
    server.use(
      http.get(`${BASE}/events/:eventId`, ({ request, params }) => {
        requestedUrl = request.url;
        return HttpResponse.json({ success: true, data: { eventId: params.eventId } });
      }),
    );

    await getEvent("event-1");

    expect(requestedUrl).toBe(`${BASE}/events/event-1`);
  });

  it("listParticipants: GET /events/{eventId}/participants のレスポンスからparticipants配列を取り出す", async () => {
    server.use(
      http.get(`${BASE}/events/:eventId/participants`, () =>
        HttpResponse.json({
          success: true,
          data: { participants: [{ userId: "u1", nickname: "たろう", status: "CONFIRMED" }] },
        }),
      ),
    );

    const result = await listParticipants("event-1");

    expect(result).toEqual([{ userId: "u1", nickname: "たろう", status: "CONFIRMED" }]);
  });

  it("removeParticipant: userIdをパスに含めてPOSTする", async () => {
    let requestedUrl = "";
    let method = "";
    server.use(
      http.post(`${BASE}/events/:eventId/participants/:userId/remove`, ({ request }) => {
        requestedUrl = request.url;
        method = request.method;
        return HttpResponse.json({
          success: true,
          data: {
            eventId: "event-1",
            userId: "u1",
            status: "CANCELLED",
            remainingParticipantCount: 3,
            belowMinPlayers: false,
          },
        });
      }),
    );

    await removeParticipant("event-1", "u1");

    expect(requestedUrl).toBe(`${BASE}/events/event-1/participants/u1/remove`);
    expect(method).toBe("POST");
  });

  it("エラーエンベロープはApiError（code/message/status）に変換される", async () => {
    server.use(
      http.post(
        `${BASE}/events/:eventId/confirm`,
        () =>
          HttpResponse.json(
            {
              success: false,
              error: {
                code: "PARTICIPANT_SCHEDULE_CONFLICT",
                message: "参加者の予定が重複しています",
              },
            },
            { status: 409 },
          ),
      ),
    );

    await expect(confirmEvent("event-1")).rejects.toMatchObject({
      code: "PARTICIPANT_SCHEDULE_CONFLICT",
      message: "参加者の予定が重複しています",
      status: 409,
    });
  });
});
