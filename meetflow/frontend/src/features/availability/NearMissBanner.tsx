import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { format, parseISO } from "date-fns";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { listEventTemplates, matchingKeys } from "@/features/matching/api";
import {
  availabilityKeys,
  createAvailabilityBatch,
  listNearMissWindows,
} from "@/features/availability/api";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";

type WindowWithTemplate = {
  templateId: string;
  startTime: string;
  endTime: string;
  neededCount: number;
};

/**
 * Issue #96: 「あと〇人で成立」表示。バックエンド側で、このコミュニティに
 * 空き予定を1件も提出していない呼び出し元には常に空配列が返るため（後出し
 * 防止のゲート）、このコンポーネントは「表示すべきかどうか」を自前で判定
 * する必要はない -- 何も返らなければ何も描画しないだけでよい。
 */
export function NearMissBanner({ communityId }: { communityId: string }) {
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();

  const { data: templates } = useQuery({
    queryKey: matchingKeys.templates(communityId),
    queryFn: () => listEventTemplates(communityId),
  });

  const nearMissQueries = useQueries({
    queries: (templates ?? []).map((template) => ({
      queryKey: [...matchingKeys.templates(communityId), template.templateId, "near-miss"],
      queryFn: () => listNearMissWindows(communityId, template.templateId),
    })),
  });

  const windows: WindowWithTemplate[] = (templates ?? []).flatMap((template, i) =>
    (nearMissQueries[i]?.data ?? []).map((w) => ({ ...w, templateId: template.templateId })),
  );

  const addMutation = useMutation({
    mutationFn: (w: WindowWithTemplate) =>
      createAvailabilityBatch(communityId, [{ startTime: w.startTime, endTime: w.endTime }]),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: availabilityKeys.list(communityId) });
      queryClient.invalidateQueries({ queryKey: matchingKeys.templates(communityId) });
      toast.success("空き予定を追加しました");
    },
    onError: handleApiError,
  });

  if (windows.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-col gap-2">
      {windows.map((w) => (
        <Card key={`${w.templateId}-${w.startTime}`}>
          <CardContent className="flex items-center justify-between gap-2">
            <div className="flex flex-col gap-1">
              <Badge variant="secondary">あと{w.neededCount}人で成立</Badge>
              <p className="text-muted-foreground text-xs">
                {format(parseISO(w.startTime), "M月d日 HH:mm")} -{" "}
                {format(parseISO(w.endTime), "HH:mm")}
              </p>
            </div>
            {/* 成立を約束するものではなく、成立への後押し(自分の空きの追加)に留める */}
            <Button size="sm" disabled={addMutation.isPending} onClick={() => addMutation.mutate(w)}>
              この時間に空きを追加
            </Button>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
