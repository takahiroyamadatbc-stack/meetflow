import { apiClient } from "@/api/client";
import type { Announcement } from "@/features/announcement/types";

export const announcementKeys = {
  all: ["announcements"] as const,
  list: (includeAll: boolean) => ["announcements", includeAll] as const,
};

/** GET /announcements（F-1406）。includeAll=trueは運営者限定 */
export function listAnnouncements(includeAll = false) {
  return apiClient
    .get<{ announcements: Announcement[] }>(
      `/announcements${includeAll ? "?includeAll=true" : ""}`,
    )
    .then((data) => data.announcements);
}

/** POST /announcements（運営者限定） */
export function createAnnouncement(input: { title: string; body: string }) {
  return apiClient.post<{ announcementId: string; createdAt: string }>(
    "/announcements",
    input,
  );
}

/** PUT /announcements/{announcementId}（運営者限定） */
export function updateAnnouncement(
  announcementId: string,
  input: { title?: string; body?: string; status?: string },
) {
  return apiClient.put<{ announcementId: string; updatedAt: string }>(
    `/announcements/${announcementId}`,
    input,
  );
}
