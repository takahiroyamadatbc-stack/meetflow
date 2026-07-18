// MeetFlow Service Worker（要件定義書v1.4 27章）。
// PWAインストール要件を満たすfetchハンドラと、Web Push受信時の通知表示のみを担う。
// オフラインキャッシュ戦略は導入しない（要件定義書のスコープ外）。

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

// ブラウザのインストール可否判定にfetchハンドラの存在が必要なため、
// 素通りするだけの実装を置く。
self.addEventListener("fetch", () => {});

self.addEventListener("push", (event) => {
  // notification_lambda/handlers/push_sender.py が送信するpayload形式
  // { title, body, type } に対応する。
  let payload = { title: "MeetFlow", body: "" };
  if (event.data) {
    try {
      payload = event.data.json();
    } catch {
      payload.body = event.data.text();
    }
  }

  event.waitUntil(
    (async () => {
      await self.registration.showNotification(payload.title || "MeetFlow", {
        body: payload.body || "",
        icon: "/icon-192x192.png",
        badge: "/favicon-32x32.png",
      });
      // Issue #50: ホーム画面アイコンのOSレベルバッジを、現在表示中の
      // 通知件数で更新する（未対応環境ではsetAppBadge自体が存在しない）。
      if ("setAppBadge" in navigator) {
        const notifications = await self.registration.getNotifications();
        try {
          await navigator.setAppBadge(notifications.length);
        } catch {
          // Badging API非対応環境（iOS Safari等）では何もしない
        }
      }
    })(),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if ("focus" in client) return client.focus();
      }
      if (self.clients.openWindow) return self.clients.openWindow("/notifications");
    }),
  );
});
