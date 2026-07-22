// vitestの各テストファイル実行前に読み込まれるセットアップ。
// jest-domのカスタムマッチャー（toBeInTheDocument等）をexpectに登録する。
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "./msw/server";

// API呼び出しをネットワークレベルでインターセプトするMSWサーバーを全テスト共通で起動する。
// 個々のテストが`server.use(...)`で追加したハンドラーは afterEach でリセットする。
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// test.globalsを有効化していないため、@testing-library/reactの自動cleanupが
// 効かない（内部でglobalThis.afterEachを検出できない）。明示的に呼び出す。
afterEach(() => cleanup());
