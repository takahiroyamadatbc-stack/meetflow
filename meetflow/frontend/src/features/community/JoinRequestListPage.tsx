import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { toast } from "sonner";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { JoinRequestCard } from "@/features/community/components/JoinRequestCard";
import {
  approveJoinRequest,
  communityKeys,
  listJoinRequests,
  rejectJoinRequest,
} from "@/features/community/api";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import type { JoinRequest } from "@/features/community/types";

/** S-07 参加リクエスト一覧・承認画面。楽観的更新で即座に一覧から取り除く */
export function JoinRequestListPage() {
  const { communityId } = useParams<{ communityId: string }>();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();
  const queryKey = communityKeys.joinRequests(communityId!);

  const { data: requests, isLoading } = useQuery({
    queryKey,
    queryFn: () => listJoinRequests(communityId!),
    enabled: !!communityId,
  });

  function optimisticallyRemove(requestId: string) {
    const previous = queryClient.getQueryData<JoinRequest[]>(queryKey);
    queryClient.setQueryData<JoinRequest[]>(
      queryKey,
      (old) => old?.filter((r) => r.requestId !== requestId) ?? [],
    );
    return previous;
  }

  const approveMutation = useMutation({
    mutationFn: (requestId: string) => approveJoinRequest(communityId!, requestId),
    onMutate: optimisticallyRemove,
    onSuccess: () => toast.success("参加を承認しました"),
    onError: (err, _requestId, previous) => {
      queryClient.setQueryData(queryKey, previous);
      handleApiError(err);
    },
  });

  const rejectMutation = useMutation({
    mutationFn: (requestId: string) => rejectJoinRequest(communityId!, requestId),
    onMutate: optimisticallyRemove,
    onSuccess: () => toast.success("参加リクエストを却下しました"),
    onError: (err, _requestId, previous) => {
      queryClient.setQueryData(queryKey, previous);
      handleApiError(err);
    },
  });

  if (isLoading) {
    return (
      <div className="flex flex-col gap-3 p-4">
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (!requests || requests.length === 0) {
    return <EmptyState message="未処理の参加リクエストはありません" />;
  }

  return (
    <div className="flex flex-col gap-3 p-4">
      {requests.map((request) => (
        <JoinRequestCard
          key={request.requestId}
          request={request}
          disabled={approveMutation.isPending || rejectMutation.isPending}
          onApprove={() => approveMutation.mutate(request.requestId)}
          onReject={() => rejectMutation.mutate(request.requestId)}
        />
      ))}
    </div>
  );
}
