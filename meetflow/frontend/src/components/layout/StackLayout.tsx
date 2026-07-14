import { Outlet, useMatches } from "react-router-dom";
import { BackHeader } from "@/components/layout/BackHeader";

type RouteHandle = { title?: string };

/**
 * タブバーを表示しないスタック遷移画面（作成/詳細/編集系）のレイアウト。
 * 各ルート定義の handle.title を見出しとして表示する
 * （router.tsxで各ルートに handle: { title: "..." } を設定する）。
 */
export function StackLayout() {
  const matches = useMatches();
  const current = [...matches].reverse().find((m) => (m.handle as RouteHandle)?.title);
  const title = (current?.handle as RouteHandle)?.title ?? "";

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <BackHeader title={title} />
      <main className="flex flex-1 flex-col overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}
