import { QueryClient } from "@tanstack/react-query";

/**
 * 一覧APIはページネーション無し（全件返却）のため、TanStack Queryの用途は
 * 無限スクロールではなくキャッシュ共有・楽観的更新・ローディング/エラー状態の
 * 一元管理である。envelopeエラーは即座にUIへ反映すべきなので暗黙リトライはしない。
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      staleTime: 30_000,
    },
    mutations: {
      retry: false,
    },
  },
});
