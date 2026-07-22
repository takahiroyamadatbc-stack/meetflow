import type { HttpHandler } from "msw";

/**
 * 各テストファイルは`server.use(...)`で個別ハンドラーを追加する想定のため、
 * ここではドメイン共通のデフォルトハンドラーは持たない（空配列がベース）。
 */
export const handlers: HttpHandler[] = [];
