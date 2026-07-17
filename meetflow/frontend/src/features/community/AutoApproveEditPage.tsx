import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { updateMyAutoApprove } from "@/features/community/api";
import { paths } from "@/routes/paths";

/** このコミュニティでの自動承認設定変更（S-05dから遷移、Issue #10） */
export function AutoApproveEditPage() {
  const { communityId } = useParams<{ communityId: string }>();
  const navigate = useNavigate();
  const handleApiError = useApiErrorToast();
  const [autoApprove, setAutoApprove] = useState(false);

  const mutation = useMutation({
    mutationFn: (value: boolean | null) => updateMyAutoApprove(communityId!, value),
    onSuccess: () => {
      toast.success("自動承認設定を変更しました");
      navigate(paths.communityDetail(communityId!));
    },
    onError: handleApiError,
  });

  return (
    <div className="flex flex-col gap-4 p-4">
      <p className="text-muted-foreground text-sm">
        このコミュニティで仮確定されたイベントについて、参加承認を自動で行うかどうかを設定します。未設定の場合はプロフィールの全体設定に従います。
      </p>
      <div className="flex flex-row items-center justify-between rounded-md border p-4">
        <span className="text-sm font-medium">このコミュニティでは自動承認する</span>
        <Switch checked={autoApprove} onCheckedChange={setAutoApprove} />
      </div>
      <Button onClick={() => mutation.mutate(autoApprove)} disabled={mutation.isPending}>
        保存する
      </Button>
      <Button
        variant="outline"
        onClick={() => mutation.mutate(null)}
        disabled={mutation.isPending}
      >
        プロフィールの設定に戻す（上書きを解除）
      </Button>
    </div>
  );
}
