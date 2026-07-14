import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuthUser } from "@/features/auth/useAuthUser";
import { paths } from "@/routes/paths";
import brandIcon from "@/assets/brand/meetflow-icon-v2.svg";

/** 未ログイン時は/loginへリダイレクトし、ログイン後に元のURLへ戻れるようにするルートガード */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuthUser();
  const location = useLocation();

  if (status === "loading") {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3">
        <img src={brandIcon} alt="" className="size-12 animate-pulse rounded-xl" />
        <p className="text-muted-foreground text-sm">読み込み中...</p>
      </div>
    );
  }

  if (status === "unauthenticated") {
    return <Navigate to={paths.login} state={{ from: location }} replace />;
  }

  return <>{children}</>;
}
