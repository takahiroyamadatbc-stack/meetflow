import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { getMyProfile, userKeys } from "@/features/user/api";
import { ProfileCard } from "@/features/user/components/ProfileCard";
import { signOutUser } from "@/features/auth/api";
import { useIsOperator } from "@/features/auth/useIsOperator";
import {
  getExistingPushSubscription,
  isIosInstallRequired,
  isPushSupported,
  subscribeToPush,
  unsubscribeFromPush,
} from "@/features/notification/pushSubscription";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { paths } from "@/routes/paths";

/** S-25 マイページ */
export function MyPage() {
  const navigate = useNavigate();
  const handleApiError = useApiErrorToast();
  const isOperator = useIsOperator();
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
      {profile && (
        <ProfileCard
          nickname={profile.nickname}
          icon={profile.icon}
          bio={profile.profile}
          gameTypes={profile.gameTypes}
        />
      )}

      <Link to={paths.profileEdit}>
        <Card>
          <CardContent className="flex items-center justify-between">
            <span className="text-sm">プロフィール編集</span>
            <ChevronRight className="text-muted-foreground size-4" />
          </CardContent>
        </Card>
      </Link>

      <PushNotificationSetting />

      <Link to={paths.feedbackNew}>
        <Card>
          <CardContent className="flex items-center justify-between">
            <span className="text-sm">フィードバックを送る</span>
            <ChevronRight className="text-muted-foreground size-4" />
          </CardContent>
        </Card>
      </Link>

      {isOperator && (
        <Link to={paths.feedbackAdmin}>
          <Card>
            <CardContent className="flex items-center justify-between">
              <span className="text-sm">フィードバック管理</span>
              <ChevronRight className="text-muted-foreground size-4" />
            </CardContent>
          </Card>
        </Link>
      )}

      <Button variant="outline" onClick={handleSignOut}>
        ログアウト
      </Button>
    </div>
  );
}

/** プッシュ通知の有効化/無効化トグル（要件定義書v1.4 27章、画面設計書v1.3 S-25） */
function PushNotificationSetting() {
  const [enabled, setEnabled] = useState(false);
  const [isChecking, setIsChecking] = useState(true);
  const [isUpdating, setIsUpdating] = useState(false);

  useEffect(() => {
    if (!isPushSupported()) {
      setIsChecking(false);
      return;
    }
    getExistingPushSubscription()
      .then((subscription) => setEnabled(subscription !== null))
      .finally(() => setIsChecking(false));
  }, []);

  if (!isPushSupported() || isChecking) {
    return null;
  }

  if (isIosInstallRequired()) {
    return (
      <Card>
        <CardContent className="flex flex-col gap-1">
          <p className="text-sm font-medium">プッシュ通知</p>
          <p className="text-muted-foreground text-xs">
            iPhoneでプッシュ通知を受け取るには、まずこのページをホーム画面に追加してください（共有ボタン→「ホーム画面に追加」）。
          </p>
        </CardContent>
      </Card>
    );
  }

  async function handleToggle(checked: boolean) {
    setIsUpdating(true);
    try {
      if (checked) {
        await subscribeToPush();
        toast.success("プッシュ通知を有効にしました");
      } else {
        await unsubscribeFromPush();
        toast.success("プッシュ通知を無効にしました");
      }
      setEnabled(checked);
    } catch {
      toast.error("プッシュ通知の設定に失敗しました");
    } finally {
      setIsUpdating(false);
    }
  }

  return (
    <Card>
      <CardContent className="flex items-center justify-between">
        <span className="text-sm">プッシュ通知</span>
        <Switch checked={enabled} disabled={isUpdating} onCheckedChange={handleToggle} />
      </CardContent>
    </Card>
  );
}
