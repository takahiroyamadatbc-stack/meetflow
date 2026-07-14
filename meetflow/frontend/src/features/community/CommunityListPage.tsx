import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { CommunityCard } from "@/features/community/components/CommunityCard";
import { communityKeys, listCommunities } from "@/features/community/api";
import { paths } from "@/routes/paths";

/** S-03 コミュニティ一覧画面 */
export function CommunityListPage() {
  const { data: communities, isLoading } = useQuery({
    queryKey: communityKeys.all,
    queryFn: listCommunities,
  });

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">コミュニティ</h1>
        <Link to={paths.communityNew}>
          <Button size="icon" aria-label="コミュニティを作成">
            <Plus className="size-4" />
          </Button>
        </Link>
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
          {communities.map((community) => (
            <CommunityCard key={community.communityId} community={community} />
          ))}
        </div>
      )}
    </div>
  );
}
