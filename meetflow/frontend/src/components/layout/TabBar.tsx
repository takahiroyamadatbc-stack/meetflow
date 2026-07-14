import { NavLink } from "react-router-dom";
import { Bell, Calendar, Home, User, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import { paths } from "@/routes/paths";

const TABS = [
  { to: paths.home, label: "ホーム", Icon: Home, end: true },
  { to: paths.communityList, label: "コミュニティ", Icon: Users, end: false },
  { to: paths.availabilityList, label: "予定", Icon: Calendar, end: false },
  { to: paths.notifications, label: "通知", Icon: Bell, end: false },
  { to: paths.myPage, label: "マイページ", Icon: User, end: false },
] as const;

/** 画面下部固定のタブバー（画面設計書v1.3：ホーム/コミュニティ/予定/通知/マイページ） */
export function TabBar() {
  return (
    <nav className="bg-background border-border sticky bottom-0 z-10 flex border-t">
      {TABS.map(({ to, label, Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) =>
            cn(
              "text-muted-foreground flex flex-1 flex-col items-center gap-1 py-2 text-xs",
              isActive && "text-primary",
            )
          }
        >
          <Icon className="size-5" />
          {label}
        </NavLink>
      ))}
    </nav>
  );
}
