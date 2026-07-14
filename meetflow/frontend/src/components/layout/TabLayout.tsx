import { Outlet } from "react-router-dom";
import { TabBar } from "@/components/layout/TabBar";

/** タブバー配下のレイアウト。各タブのルートコンポーネントは<Outlet/>に描画される */
export function TabLayout() {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <main className="flex flex-1 flex-col overflow-y-auto">
        <Outlet />
      </main>
      <TabBar />
    </div>
  );
}
