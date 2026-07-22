import { beforeEach, describe, expect, it } from "vitest";
import {
  consumePendingInvitePath,
  peekPendingInvitePath,
  savePendingInvitePath,
} from "@/features/auth/pendingInvite";

describe("pendingInvite", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("保存した招待先パスをpeekで取得できる", () => {
    savePendingInvitePath("/invite/abc123");
    expect(peekPendingInvitePath()).toBe("/invite/abc123");
  });

  it("何も保存されていない場合はnullを返す", () => {
    expect(peekPendingInvitePath()).toBeNull();
  });

  it("peekは何度呼んでも値を消費しない（Issue #69: LoginPage/ConfirmSignUpPage/RedirectIfAuthenticatedが同じ値を競合して読んでも消失しない）", () => {
    savePendingInvitePath("/invite/abc123");

    expect(peekPendingInvitePath()).toBe("/invite/abc123");
    expect(peekPendingInvitePath()).toBe("/invite/abc123");
    expect(peekPendingInvitePath()).toBe("/invite/abc123");
  });

  it("consumeを呼ぶと以降のpeekはnullを返す", () => {
    savePendingInvitePath("/invite/abc123");

    consumePendingInvitePath();

    expect(peekPendingInvitePath()).toBeNull();
  });

  it("保存し直すと最新のパスに上書きされる", () => {
    savePendingInvitePath("/invite/old");
    savePendingInvitePath("/invite/new");

    expect(peekPendingInvitePath()).toBe("/invite/new");
  });
});
