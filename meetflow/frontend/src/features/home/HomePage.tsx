import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { CommunityCard } from "@/features/community/components/CommunityCard";
import { communityKeys, listCommunities } from "@/features/community/api";
import { useUnreadNotificationCount } from "@/features/notification/api";
import { AnnouncementCard } from "@/features/announcement/AnnouncementCard";
import { paths } from "@/routes/paths";

/** S-02 ホーム画面 */
export function HomePage() {
  const { data: communities, isLoading } = useQuery({
    queryKey: communityKeys.all,
    queryFn: listCommunities,
  });
  const unreadCount = useUnreadNotificationCount();

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">ホーム</h1>
        {unreadCount > 0 && (
          <Link to={paths.notifications}>
            <Badge variant="destructive">未読の通知 {unreadCount}件</Badge>
          </Link>
        )}
      </div>

      <AnnouncementCard />

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
