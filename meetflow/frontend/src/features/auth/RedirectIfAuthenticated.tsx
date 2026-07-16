import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuthUser } from "@/features/auth/useAuthUser";
import { paths } from "@/routes/paths";
import brandIcon from "@/assets/brand/meetflow-icon-v2.svg";

/**
 * ログイン済みユーザーがログイン/サインアップ系画面に来た場合はホームへ逃がすルートガード。
 * これが無いと、既にセッションが確立した状態でsignIn()を呼んだ際にAmplifyが
 * UserAlreadyAuthenticatedException("There is already a signed in user")を
 * 投げるだけで、画面はログインフォームに留まり続けてしまう。
 */
export function RedirectIfAuthenticated({ children }: { children: ReactNode }) {
  const { status } = useAuthUser();

  if (status === "loading") {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3">
        <img src={brandIcon} alt="" className="size-12 animate-pulse rounded-xl" />
        <p className="text-muted-foreground text-sm">読み込み中...</p>
      </div>
    );
  }

  if (status === "authenticated") {
    return <Navigate to={paths.home} replace />;
  }

  return <>{children}</>;
}
