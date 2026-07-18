import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { format, parseISO } from "date-fns";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { CommunityCard } from "@/features/community/components/CommunityCard";
import { communityKeys, listCommunities } from "@/features/community/api";
import { DEFAULT_THEME_COLOR } from "@/features/community/theme-colors";
import { useUnreadNotificationCount } from "@/features/notification/api";
import { AnnouncementCard } from "@/features/announcement/AnnouncementCard";
import { getMyProfile, userKeys } from "@/features/user/api";
import { ProfileCard } from "@/features/user/components/ProfileCard";
import { eventKeys, listMyEvents } from "@/features/event/api";
import { paths } from "@/routes/paths";

/** S-02 ホーム画面 */
export function HomePage() {
  const { data: communities, isLoading } = useQuery({
    queryKey: communityKeys.all,
    queryFn: listCommunities,
  });
  const { data: profile } = useQuery({
    queryKey: userKeys.me,
    queryFn: getMyProfile,
  });
  const { data: myEvents } = useQuery({
    queryKey: eventKeys.myEvents,
    queryFn: listMyEvents,
  });
  const unreadCount = useUnreadNotificationCount();

  const communityById = useMemo(
    () => new Map((communities ?? []).map((c) => [c.communityId, c] as const)),
    [communities],
  );

  // Issue #54: 未来の確定イベントを全件表示する（一部のみに絞らない）
  const upcomingEvents = useMemo(
    () =>
      (myEvents ?? [])
        .filter((e) => parseISO(e.startTime).getTime() > Date.now())
        .sort((a, b) => parseISO(a.startTime).getTime() - parseISO(b.startTime).getTime()),
    [myEvents],
  );

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

      {profile && (
        <ProfileCard
          nickname={profile.nickname}
          icon={profile.icon}
          bio={profile.profile}
          gameTypes={profile.gameTypes}
        />
      )}

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

      {upcomingEvents.length > 0 && (
        <div className="flex flex-col gap-3">
          <h2 className="text-muted-foreground text-sm font-medium">確定イベント</h2>
          {upcomingEvents.map((myEvent) => {
            const community = communityById.get(myEvent.communityId);
            const themeColor = community?.themeColor ?? DEFAULT_THEME_COLOR;
            return (
              <Link key={myEvent.eventId} to={paths.eventDetail(myEvent.eventId)}>
                <Card className="border-l-4" style={{ borderLeftColor: themeColor }}>
                  <CardContent className="flex flex-col gap-1">
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-medium">
                        {format(parseISO(myEvent.startTime), "M月d日 HH:mm")} -{" "}
                        {format(parseISO(myEvent.endTime), "HH:mm")}
                      </p>
                      <Badge>確定</Badge>
                    </div>
                    <p className="text-muted-foreground text-xs">
                      {community?.name ?? "コミュニティ"}
                    </p>
                  </CardContent>
                </Card>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
