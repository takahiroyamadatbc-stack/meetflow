import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type { NotificationItem } from "@/features/notification/types";

export const notificationKeys = {
  all: ["notifications"] as const,
};

/** GET /notifications */
export function listNotifications() {
  return apiClient
    .get<{ notifications: NotificationItem[] }>("/notifications")
    .then((data) => data.notifications);
}

/** PUT /notifications/{notificationId}/read */
export function markNotificationRead(notificationId: string) {
  return apiClient.put(`/notifications/${notificationId}/read`, {});
}

/** POST /users/me/push-subscriptions */
export function registerPushSubscription(input: {
  endpoint: string;
  keys: { p256dh: string; auth: string };
  userAgent?: string;
}) {
  return apiClient.post("/users/me/push-subscriptions", input);
}

/** DELETE /users/me/push-subscriptions（存在しないendpointの解除も冪等に成功扱い） */
export function unregisterPushSubscription(endpoint: string) {
  return apiClient.delete("/users/me/push-subscriptions", { endpoint });
}

/** タブバー・ホーム画面共通の未読件数。通知一覧と同じキャッシュを共有する */
export function useUnreadNotificationCount() {
  const { data } = useQuery({ queryKey: notificationKeys.all, queryFn: listNotifications });
  return data?.filter((n) => !n.read).length ?? 0;
}
