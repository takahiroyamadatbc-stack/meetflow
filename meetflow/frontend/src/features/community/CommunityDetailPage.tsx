import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { RoleBadge } from "@/features/community/components/RoleBadge";
import { communityKeys, getCommunity } from "@/features/community/api";
import { paths } from "@/routes/paths";

/** S-05 コミュニティ詳細画面 */
export function CommunityDetailPage() {
  const { communityId } = useParams<{ communityId: string }>();
  const { data: community, isLoading } = useQuery({
    queryKey: communityKeys.detail(communityId!),
    queryFn: () => getCommunity(communityId!),
    enabled: !!communityId,
  });

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4 p-4">
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

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
          {community.memberApprovalRequired && (
            <Badge variant="outline" className="mt-1 self-start">
              参加に承認が必要
            </Badge>
          )}
        </CardContent>
      </Card>

      <Accordion className="flex flex-col gap-2">
        <AccordionItem value="member">
          <AccordionTrigger>メンバー</AccordionTrigger>
          <AccordionContent>
            <div className="flex flex-col gap-3">
              <NavCard to={paths.communityMembers(community.communityId)} label="メンバー一覧" />
              <NavCard
                to={paths.communityDisplayNameEdit(community.communityId)}
                label="このコミュニティでの表示名を変更"
              />
              {isAdmin && (
                <>
                  <NavCard
                    to={paths.communityInvite(community.communityId)}
                    label="メンバーを招待する"
                  />
                  <NavCard
                    to={paths.communityJoinRequests(community.communityId)}
                    label="参加リクエスト一覧"
                  />
                </>
              )}
            </div>
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="availability">
          <AccordionTrigger>空き予定</AccordionTrigger>
          <AccordionContent>
            <div className="flex flex-col gap-3">
              <NavCard
                to={paths.availabilityNew(community.communityId)}
                label="空き予定を登録する"
              />
              <NavCard to={paths.availabilityList} label="登録済みの空き予定を確認・編集する" />
              <NavCard
                to={paths.availabilityRequestList(community.communityId)}
                label="空き予定提出リクエスト"
              />
            </div>
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="event">
          <AccordionTrigger>イベント・マッチング</AccordionTrigger>
          <AccordionContent>
            <div className="flex flex-col gap-3">
              <NavCard to={paths.eventList(community.communityId)} label="イベント一覧" />
              {isAdmin && (
                <>
                  <NavCard to={paths.eventTemplateList(community.communityId)} label="開催条件" />
                  <NavCard
                    to={paths.matchingCandidateList(community.communityId)}
                    label="マッチング候補"
                  />
                </>
              )}
            </div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
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
