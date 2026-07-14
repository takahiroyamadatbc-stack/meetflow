import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { communityKeys, joinViaInvite } from "@/features/community/api";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { paths } from "@/routes/paths";

/** 招待URL受諾画面（画面設計書に番号は無いが、招待フローに必須のため実装） */
export function InviteAcceptPage() {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();
  const [message, setMessage] = useState("");

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

  return (
    <div className="flex flex-1 flex-col justify-center px-6 py-10">
      <Card>
        <CardHeader>
          <CardTitle>コミュニティに参加する</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <Textarea
            placeholder="参加メッセージ（任意）"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            rows={3}
          />
          <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            参加する
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
