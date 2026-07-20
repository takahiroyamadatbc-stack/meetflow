import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { communityKeys, getInvitePreview, joinViaInvite } from "@/features/community/api";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { consumePendingInvitePath } from "@/features/auth/pendingInvite";
import { paths } from "@/routes/paths";

/**
 * 招待URL受諾画面（画面設計書に番号は無いが、招待フローに必須のため実装）。
 * マウント時にGET /invites/{token}で承認要否を事前取得し、承認不要
 * （即時参加）の場合はメッセージ欄を表示しない（Issue #23。承認制の
 * コミュニティでは、joinViaInviteがmessageを保存し管理者の審査材料に
 * 使うが、即時参加ではmessageは一切参照・保存されず捨てられるため）。
 */
export function InviteAcceptPage() {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();
  const [message, setMessage] = useState("");

  // このページへの到着をもって招待の引き継ぎ導線は役目を終えたとみなし、
  // sessionStorageの一時保存を消費（削除）する。LoginPage/ConfirmSignUpPage/
  // RedirectIfAuthenticatedはpeek（読むだけ）に統一したため、削除はここでのみ
  // 行う（レンダー中の副作用を避けるためuseEffect内で実行。Issue #69）。
  useEffect(() => {
    consumePendingInvitePath();
  }, []);

  const {
    data: preview,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["invitePreview", token],
    queryFn: () => getInvitePreview(token!),
    enabled: !!token,
    retry: false,
  });

  const mutation = useMutation({
    mutationFn: () => joinViaInvite(token!, message || undefined),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: communityKeys.all });
      if (result.status === "ACTIVE") {
        toast.success("コミュニティに参加しました");
        navigate(paths.communityDetail(result.communityId), { replace: true });
      } else {
        toast.success("参加リクエストを送信しました。管理者の承認をお待ちください");
        navigate(paths.home, { replace: true });
      }
    },
    onError: handleApiError,
  });

  if (isLoading) {
    return (
      <div className="flex flex-1 flex-col justify-center px-6 py-10">
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (isError || !preview) {
    return <EmptyState message="招待URLが無効です" />;
  }

  return (
    <div className="flex flex-1 flex-col justify-center px-6 py-10">
      <Card>
        <CardHeader>
          <CardTitle>{preview.communityName} に参加する</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {preview.approvalRequired && (
            <Textarea
              placeholder="参加メッセージ（任意）"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={3}
            />
          )}
          <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            参加する
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
