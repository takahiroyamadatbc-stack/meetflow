import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { communityKeys, getCommunity, updateThemeColor } from "@/features/community/api";
import { ThemeColorPicker } from "@/features/community/components/ThemeColorPicker";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { paths } from "@/routes/paths";

/** S-05c コミュニティテーマカラー変更（S-05から遷移、OWNER/ADMIN限定） */
export function ThemeColorEditPage() {
  const { communityId } = useParams<{ communityId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();

  const { data: community, isLoading } = useQuery({
    queryKey: communityKeys.detail(communityId!),
    queryFn: () => getCommunity(communityId!),
    enabled: !!communityId,
  });
  // undefined = ユーザーがまだ何も操作していない（取得済みのthemeColorをそのまま表示）。
  // null = ユーザーが明示的に選択解除した。取得値へのフォールバックと区別する必要がある。
  const [selected, setSelected] = useState<string | null | undefined>(undefined);
  const themeColor = selected !== undefined ? selected : (community?.themeColor ?? null);

  const mutation = useMutation({
    mutationFn: () => updateThemeColor(communityId!, themeColor ?? ""),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: communityKeys.detail(communityId!) });
      toast.success("テーマカラーを変更しました");
      navigate(paths.communityDetail(communityId!));
    },
    onError: handleApiError,
  });

  if (isLoading) {
    return (
      <div className="p-4">
        <Skeleton className="h-10 w-full" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 p-4">
      <ThemeColorPicker value={themeColor} onChange={setSelected} />
      <div
        className="flex h-16 items-center justify-center rounded-lg text-sm font-medium text-white"
        style={{ backgroundColor: themeColor ?? "var(--muted-foreground)" }}
      >
        {themeColor ?? "未選択（既定色）"}
      </div>
      <Button disabled={mutation.isPending} onClick={() => mutation.mutate()}>
        保存する
      </Button>
    </div>
  );
}
