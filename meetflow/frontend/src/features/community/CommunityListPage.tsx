import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ArrowDownUp, ChevronDown, ChevronUp, Plus } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { CommunityCard } from "@/features/community/components/CommunityCard";
import { RoleBadge } from "@/features/community/components/RoleBadge";
import { communityKeys, listCommunities, reorderCommunities } from "@/features/community/api";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import type { CommunitySummary } from "@/features/community/types";
import { paths } from "@/routes/paths";

/** S-03 コミュニティ一覧画面 */
export function CommunityListPage() {
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();
  const [reordering, setReordering] = useState(false);
  const [order, setOrder] = useState<CommunitySummary[]>([]);

  const { data: communities, isLoading } = useQuery({
    queryKey: communityKeys.all,
    queryFn: listCommunities,
  });

  useEffect(() => {
    if (communities) setOrder(communities);
  }, [communities]);

  const reorderMutation = useMutation({
    mutationFn: (communityIds: string[]) => reorderCommunities(communityIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: communityKeys.all });
      toast.success("表示順を変更しました");
      setReordering(false);
    },
    onError: handleApiError,
  });

  function moveItem(index: number, direction: -1 | 1) {
    setOrder((current) => {
      const target = index + direction;
      if (target < 0 || target >= current.length) return current;
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  function handleDoneReordering() {
    reorderMutation.mutate(order.map((c) => c.communityId));
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">コミュニティ</h1>
        <div className="flex gap-2">
          {communities && communities.length > 1 && (
            <Button
              variant={reordering ? "default" : "outline"}
              size="icon"
              aria-label={reordering ? "並び替えを完了" : "表示順を並び替え"}
              disabled={reorderMutation.isPending}
              onClick={() => (reordering ? handleDoneReordering() : setReordering(true))}
            >
              <ArrowDownUp className="size-4" />
            </Button>
          )}
          <Link to={paths.communityNew}>
            <Button size="icon" aria-label="コミュニティを作成">
              <Plus className="size-4" />
            </Button>
          </Link>
        </div>
      </div>

      {isLoading && (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      )}

      {!isLoading && communities?.length === 0 && (
        <EmptyState
          message="所属しているコミュニティがありません"
          description="新しくコミュニティを作成するか、招待URLから参加してください"
        />
      )}

      {!isLoading && communities && communities.length > 0 && (
        <div className="flex flex-col gap-3">
          {reordering
            ? order.map((community, index) => (
                <Card
                  key={community.communityId}
                  className="border-l-4"
                  style={
                    community.themeColor ? { borderLeftColor: community.themeColor } : undefined
                  }
                >
                  <CardContent className="flex items-center justify-between gap-2">
                    <div className="flex flex-col gap-1">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-semibold">{community.name}</p>
                        <RoleBadge role={community.role} />
                      </div>
                    </div>
                    <div className="flex gap-1">
                      <Button
                        variant="outline"
                        size="icon"
                        aria-label="上へ移動"
                        disabled={index === 0}
                        onClick={() => moveItem(index, -1)}
                      >
                        <ChevronUp className="size-4" />
                      </Button>
                      <Button
                        variant="outline"
                        size="icon"
                        aria-label="下へ移動"
                        disabled={index === order.length - 1}
                        onClick={() => moveItem(index, 1)}
                      >
                        <ChevronDown className="size-4" />
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))
            : communities.map((community) => (
                <CommunityCard key={community.communityId} community={community} />
              ))}
        </div>
      )}
    </div>
  );
}
