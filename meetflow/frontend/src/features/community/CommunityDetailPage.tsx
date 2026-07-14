import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { RoleBadge } from "@/features/community/components/RoleBadge";
import { communityKeys, listCommunities } from "@/features/community/api";
import { paths } from "@/routes/paths";

/**
 * S-05 コミュニティ詳細画面。
 * GET /communities/{communityId} が存在しないため（Phase1実装計画の食い違い#1）、
 * 一覧のTanStack Queryキャッシュから対象コミュニティを検索して表示する。
 */
export function CommunityDetailPage() {
  const { communityId } = useParams<{ communityId: string }>();
  const { data: communities, isLoading } = useQuery({
    queryKey: communityKeys.all,
    queryFn: listCommunities,
  });

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4 p-4">
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  const community = communities?.find((c) => c.communityId === communityId);
  if (!community) {
    return <EmptyState message="コミュニティが見つかりません" />;
  }

  const isAdmin = community.role === "OWNER" || community.role === "ADMIN";

  return (
    <div className="flex flex-col gap-4 p-4">
      <Card>
        <CardContent className="flex flex-col gap-1">
          <div className="flex items-center justify-between">
            <p className="text-base font-semibold">{community.name}</p>
            <RoleBadge role={community.role} />
          </div>
          {community.genre && <p className="text-muted-foreground text-xs">{community.genre}</p>}
          {community.description && <p className="text-sm">{community.description}</p>}
        </CardContent>
      </Card>

      <div className="flex flex-col gap-3">
        <NavCard to={paths.communityMembers(community.communityId)} label="メンバー一覧" />
        <NavCard
          to={paths.availabilityNew(community.communityId)}
          label="空き予定を登録する"
        />
        <NavCard
          to={paths.availabilityRequestList(community.communityId)}
          label="空き予定提出リクエスト"
        />
        {isAdmin && (
          <>
            <NavCard to={paths.communityInvite(community.communityId)} label="メンバーを招待する" />
            <NavCard
              to={paths.communityJoinRequests(community.communityId)}
              label="参加リクエスト一覧"
            />
          </>
        )}
      </div>
    </div>
  );
}

function NavCard({ to, label }: { to: string; label: string }) {
  return (
    <Link to={to}>
      <Card>
        <CardContent className="flex items-center justify-between">
          <span className="text-sm">{label}</span>
          <ChevronRight className="text-muted-foreground size-4" />
        </CardContent>
      </Card>
    </Link>
  );
}
