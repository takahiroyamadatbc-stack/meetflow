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
    self.registration.showNotification(payload.title || "MeetFlow", {
      body: payload.body || "",
      icon: "/icon-192x192.png",
      badge: "/favicon-32x32.png",
    }),
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
