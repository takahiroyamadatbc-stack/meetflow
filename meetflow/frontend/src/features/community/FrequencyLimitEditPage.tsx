import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { updateMyFrequencyLimit } from "@/features/community/api";
import type { FrequencyLimitPeriod } from "@/features/user/types";
import { paths } from "@/routes/paths";

/** このコミュニティでの参加頻度上限設定変更（S-05dの並び、Issue #19） */
export function FrequencyLimitEditPage() {
  const { communityId } = useParams<{ communityId: string }>();
  const navigate = useNavigate();
  const handleApiError = useApiErrorToast();
  const [count, setCount] = useState("");
  const [period, setPeriod] = useState<FrequencyLimitPeriod>("WEEK");

  const mutation = useMutation({
    mutationFn: (input: { count: number; period: FrequencyLimitPeriod } | null) =>
      updateMyFrequencyLimit(communityId!, input?.count ?? null, input?.period ?? null),
    onSuccess: () => {
      toast.success("参加頻度上限を変更しました");
      navigate(paths.communityDetail(communityId!));
    },
    onError: handleApiError,
  });

  function handleSave() {
    const parsed = Number(count);
    if (!Number.isInteger(parsed) || parsed <= 0) {
      toast.error("上限回数は正の整数で入力してください");
      return;
    }
    mutation.mutate({ count: parsed, period });
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <p className="text-muted-foreground text-sm">
        このコミュニティでの参加頻度上限（回数＋期間）を、プロフィールの全体設定から上書きします。未設定の場合はプロフィールの全体設定に従います。
      </p>
      <div className="flex flex-row items-center gap-2">
        <Input
          type="number"
          min={1}
          placeholder="回数"
          value={count}
          onChange={(e) => setCount(e.target.value)}
        />
        <span className="text-sm">回 /</span>
        <Select value={period} onValueChange={(v) => setPeriod(v as FrequencyLimitPeriod)}>
          <SelectTrigger className="w-24">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="WEEK">週</SelectItem>
            <SelectItem value="MONTH">月</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <Button onClick={handleSave} disabled={mutation.isPending}>
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
