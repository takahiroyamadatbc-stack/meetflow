import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { format, parseISO } from "date-fns";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { approveCancelRequest, eventKeys, listCancelRequests } from "@/features/event/api";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import type { CancelRequest } from "@/features/event/types";

/** S-19 キャンセル申請一覧・承認画面（バックエンドに却下APIが無いため承認のみ） */
export function CancelRequestListPage() {
  const { eventId } = useParams<{ eventId: string }>();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();
  const queryKey = eventKeys.cancelRequests(eventId!);

  const { data: requests, isLoading } = useQuery({
    queryKey,
    queryFn: () => listCancelRequests(eventId!),
    enabled: !!eventId,
  });

  const approveMutation = useMutation({
    mutationFn: (userId: string) => approveCancelRequest(eventId!, userId),
    onMutate: (userId: string) => {
      const previous = queryClient.getQueryData<CancelRequest[]>(queryKey);
      queryClient.setQueryData<CancelRequest[]>(
        queryKey,
        (old) => old?.filter((r) => r.userId !== userId) ?? [],
      );
      return previous;
    },
    onSuccess: () => toast.success("キャンセル申請を承認しました"),
    onError: (err, _userId, previous) => {
      queryClient.setQueryData(queryKey, previous);
      handleApiError(err);
    },
  });

  if (isLoading) {
    return (
      <div className="flex flex-col gap-3 p-4">
        <Skeleton className="h-20 w-full" />
      </div>
    );
  }

  const pending = (requests ?? []).filter((r) => r.status === "PENDING");

  if (pending.length === 0) {
    return <EmptyState message="未処理のキャンセル申請はありません" />;
  }

  return (
    <div className="flex flex-col gap-3 p-4">
      {pending.map((request) => (
        <Card key={request.userId}>
          <CardContent className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">{request.reason}</p>
              <p className="text-muted-foreground text-xs">
                {format(parseISO(request.requestedAt), "M月d日 HH:mm")}に申請
              </p>
            </div>
            <Button
              size="sm"
              disabled={approveMutation.isPending}
              onClick={() => approveMutation.mutate(request.userId)}
            >
              承認する
            </Button>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
