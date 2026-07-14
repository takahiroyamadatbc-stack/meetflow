import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { getMyProfile, userKeys } from "@/features/user/api";
import { GAME_TYPE_LABELS } from "@/features/user/types";
import { signOutUser } from "@/features/auth/api";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { paths } from "@/routes/paths";

/** S-25 マイページ（Phase1は最小構成。プッシュ通知設定はPhase2） */
export function MyPage() {
  const navigate = useNavigate();
  const handleApiError = useApiErrorToast();
  const { data: profile, isLoading } = useQuery({
    queryKey: userKeys.me,
    queryFn: getMyProfile,
  });

  async function handleSignOut() {
    try {
      await signOutUser();
      navigate(paths.login, { replace: true });
    } catch (err) {
      handleApiError(err);
    }
  }

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4 p-4">
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <Card>
        <CardContent className="flex items-center gap-4">
          <Avatar className="size-14">
            <AvatarFallback>{profile?.nickname?.slice(0, 1) ?? "?"}</AvatarFallback>
          </Avatar>
          <div>
            <p className="text-base font-semibold">{profile?.nickname}</p>
            {profile && profile.gameTypes.length > 0 && (
              <p className="text-muted-foreground text-xs">
                {profile.gameTypes.map((g) => GAME_TYPE_LABELS[g]).join(" / ")}
              </p>
            )}
          </div>
        </CardContent>
      </Card>

      <Link to={paths.profileEdit}>
        <Card>
          <CardContent className="flex items-center justify-between">
            <span className="text-sm">プロフィール編集</span>
            <ChevronRight className="text-muted-foreground size-4" />
          </CardContent>
        </Card>
      </Link>

      <Button variant="outline" onClick={handleSignOut}>
        ログアウト
      </Button>
    </div>
  );
}
