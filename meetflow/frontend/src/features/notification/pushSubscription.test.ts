import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getExistingPushSubscription,
  isIosInstallRequired,
  isPushSupported,
  subscribeToPush,
  unsubscribeFromPush,
} from "@/features/notification/pushSubscription";
import * as notificationApi from "@/features/notification/api";

vi.mock("@/features/notification/api");

const originalMatchMedia = window.matchMedia;

function stubUserAgent(userAgent: string) {
  Object.defineProperty(window.navigator, "userAgent", { value: userAgent, configurable: true });
}

function stubMatchMedia(matches: boolean) {
  window.matchMedia = vi.fn().mockReturnValue({ matches }) as unknown as typeof window.matchMedia;
}

afterEach(() => {
  vi.resetAllMocks();
  delete (navigator as { serviceWorker?: unknown }).serviceWorker;
  delete (window as { PushManager?: unknown }).PushManager;
  delete (globalThis as { Notification?: unknown }).Notification;
  window.matchMedia = originalMatchMedia;
});

describe("isPushSupported", () => {
  it("serviceWorkerとPushManagerの両方がある場合はtrue", () => {
    Object.defineProperty(navigator, "serviceWorker", { value: {}, configurable: true });
    Object.defineProperty(window, "PushManager", { value: class {}, configurable: true });

    expect(isPushSupported()).toBe(true);
  });

  it("serviceWorkerが無い場合はfalse", () => {
    Object.defineProperty(window, "PushManager", { value: class {}, configurable: true });

    expect(isPushSupported()).toBe(false);
  });

  it("PushManagerが無い場合はfalse", () => {
    Object.defineProperty(navigator, "serviceWorker", { value: {}, configurable: true });

    expect(isPushSupported()).toBe(false);
  });
});

describe("isIosInstallRequired", () => {
  it("iOSかつホーム画面に追加されていない場合はtrue", () => {
    stubUserAgent(
      "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
    );
    stubMatchMedia(false);

    expect(isIosInstallRequired()).toBe(true);
  });

  it("iOSでもホーム画面に追加済み（standalone）ならfalse", () => {
    stubUserAgent(
      "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
    );
    stubMatchMedia(true);

    expect(isIosInstallRequired()).toBe(false);
  });

  it("iOS以外はfalse", () => {
    stubUserAgent(
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
    );
    stubMatchMedia(false);

    expect(isIosInstallRequired()).toBe(false);
  });
});

describe("subscribeToPush", () => {
  it("通知が許可されなかった場合はエラーを投げ、購読登録APIは呼ばない", async () => {
    (globalThis as { Notification?: unknown }).Notification = {
      requestPermission: vi.fn().mockResolvedValue("denied"),
    };

    await expect(subscribeToPush()).rejects.toThrow("通知が許可されませんでした");
    expect(notificationApi.registerPushSubscription).not.toHaveBeenCalled();
  });

  it("許可された場合はpush購読を作成し、endpoint/keys/userAgentを登録APIに渡す", async () => {
    stubUserAgent("test-user-agent");
    (globalThis as { Notification?: unknown }).Notification = {
      requestPermission: vi.fn().mockResolvedValue("granted"),
    };
    const subscribe = vi.fn().mockResolvedValue({
      toJSON: () => ({
        endpoint: "https://push.example.com/abc",
        keys: { p256dh: "p256dh-value", auth: "auth-value" },
      }),
    });
    Object.defineProperty(navigator, "serviceWorker", {
      value: { ready: Promise.resolve({ pushManager: { subscribe } }) },
      configurable: true,
    });

    await subscribeToPush();

    expect(subscribe).toHaveBeenCalledWith(
      expect.objectContaining({
        userVisibleOnly: true,
        applicationServerKey: expect.any(Uint8Array),
      }),
    );
    expect(notificationApi.registerPushSubscription).toHaveBeenCalledWith({
      endpoint: "https://push.example.com/abc",
      keys: { p256dh: "p256dh-value", auth: "auth-value" },
      userAgent: "test-user-agent",
    });
  });
});

describe("getExistingPushSubscription / unsubscribeFromPush", () => {
  it("非対応環境ではgetExistingPushSubscriptionはnullを返す", async () => {
    expect(await getExistingPushSubscription()).toBeNull();
  });

  it("既存の購読が無い場合、unsubscribeFromPushは解除APIを呼ばない", async () => {
    Object.defineProperty(window, "PushManager", { value: class {}, configurable: true });
    Object.defineProperty(navigator, "serviceWorker", {
      value: { ready: Promise.resolve({ pushManager: { getSubscription: () => null } }) },
      configurable: true,
    });

    await unsubscribeFromPush();

    expect(notificationApi.unregisterPushSubscription).not.toHaveBeenCalled();
  });

  it("既存の購読がある場合、unsubscribe()を呼びendpointを解除APIに渡す", async () => {
    const unsubscribe = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(window, "PushManager", { value: class {}, configurable: true });
    Object.defineProperty(navigator, "serviceWorker", {
      value: {
        ready: Promise.resolve({
          pushManager: {
            getSubscription: () =>
              Promise.resolve({ endpoint: "https://push.example.com/xyz", unsubscribe }),
          },
        }),
      },
      configurable: true,
    });

    await unsubscribeFromPush();

    expect(unsubscribe).toHaveBeenCalled();
    expect(notificationApi.unregisterPushSubscription).toHaveBeenCalledWith(
      "https://push.example.com/xyz",
    );
  });
});
