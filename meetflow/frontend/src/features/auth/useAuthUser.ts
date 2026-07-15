import { useEffect, useState } from "react";
import { Hub } from "aws-amplify/utils";
import { getCurrentAuthUser } from "@/features/auth/api";

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

type AuthUserState = {
  status: AuthStatus;
  userId: string | null;
};

/**
 * Amplifyのセッション状態を購読する薄いフック。
 * Redux等の状態管理ライブラリは導入せず、Hubイベント購読のみで完結させる。
 */
export function useAuthUser(): AuthUserState {
  const [state, setState] = useState<AuthUserState>({ status: "loading", userId: null });

  useEffect(() => {
    let mounted = true;

    async function checkCurrentUser() {
      try {
        const user = await getCurrentAuthUser();
        if (mounted) setState({ status: "authenticated", userId: user.userId });
      } catch {
        if (mounted) setState({ status: "unauthenticated", userId: null });
      }
    }

    checkCurrentUser();

    const unsubscribe = Hub.listen("auth", ({ payload }) => {
      if (payload.event === "signedIn") {
        checkCurrentUser();
      } else if (payload.event === "signedOut") {
        setState({ status: "unauthenticated", userId: null });
      }
    });

    return () => {
      mounted = false;
      unsubscribe();
    };
  }, []);

  return state;
}
