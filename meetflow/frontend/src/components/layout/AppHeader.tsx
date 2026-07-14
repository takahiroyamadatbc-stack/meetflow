import brandIcon from "@/assets/brand/meetflow-icon-v2.svg";

/** タブ画面共通のブランドヘッダー（アプリアイコン+アプリ名を画面上部に固定表示） */
export function AppHeader() {
  return (
    <header className="border-border bg-background sticky top-0 z-10 flex items-center gap-2 border-b px-4 py-2">
      <img src={brandIcon} alt="" className="size-7 rounded-md" />
      <span className="text-base font-semibold tracking-tight">MeetFlow</span>
    </header>
  );
}
