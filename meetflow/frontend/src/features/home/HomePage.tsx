import { useQuery } from "@tanstack/react-query";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { CommunityCard } from "@/features/community/components/CommunityCard";
import { communityKeys, listCommunities } from "@/features/community/api";

/**
 * S-02 ホーム画面（Phase1は最小構成）。
 * 通知バッジは GET /notifications がPhase2スコープのため非表示。
 */
export function HomePage() {
  const { data: communities, isLoading } = useQuery({
    queryKey: communityKeys.all,
    queryFn: listCommunities,
  });

  return (
    <div className="flex flex-col gap-4 p-4">
      <h1 className="text-lg font-semibold">ホーム</h1>

      {isLoading && <Skeleton className="h-20 w-full" />}

      {!isLoading && communities?.length === 0 && (
        <EmptyState
          message="所属しているコミュニティがありません"
          description="コミュニティタブから作成・参加してください"
        />
      )}

      {!isLoading && communities && communities.length > 0 && (
        <div className="flex flex-col gap-3">
          <h2 className="text-muted-foreground text-sm font-medium">所属コミュニティ</h2>
          {communities.map((community) => (
            <CommunityCard key={community.communityId} community={community} />
          ))}
        </div>
      )}
    </div>
  );
}
