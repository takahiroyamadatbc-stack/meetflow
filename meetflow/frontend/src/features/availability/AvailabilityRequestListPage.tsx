import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { format, parseISO } from "date-fns";
import { ChevronDown, ChevronUp, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { communityKeys, getCommunity } from "@/features/community/api";
import {
  availabilityKeys,
  listAvailabilityRequests,
  listPendingMembers,
} from "@/features/availability/api";
import { paths } from "@/routes/paths";

/** S-27 空き予定提出リクエスト一覧・未提出者確認画面 */
export function AvailabilityRequestListPage() {
  const { communityId } = useParams<{ communityId: string }>();

  const { data: currentCommunity } = useQuery({
    queryKey: communityKeys.detail(communityId!),
    queryFn: () => getCommunity(communityId!),
    enabled: !!communityId,
  });
  const isAdmin = currentCommunity?.role === "OWNER" || currentCommunity?.role === "ADMIN";

  const { data: requests, isLoading } = useQuery({
    queryKey: availabilityKeys.requests(communityId!),
    queryFn: () => listAvailabilityRequests(communityId!),
    enabled: !!communityId,
  });

  if (isLoading) {
    return (
      <div className="flex flex-col gap-3 p-4">
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 p-4">
      {isAdmin && (
        <Link to={paths.availabilityRequestNew(communityId!)} className="self-end">
          <Button size="sm">
            <Plus className="size-4" />
            提出リクエストを作成
          </Button>
        </Link>
      )}

      {(!requests || requests.length === 0) && (
        <EmptyState message="空き予定提出リクエストはありません" />
      )}

      {requests?.map((request) => (
        <RequestCard
          key={request.requestId}
          communityId={communityId!}
          requestId={request.requestId}
          targetPeriodStart={request.targetPeriodStart}
          targetPeriodEnd={request.targetPeriodEnd}
          deadline={request.deadline}
          message={request.message}
          canExpand={isAdmin}
        />
      ))}
    </div>
  );
}

function RequestCard({
  communityId,
  requestId,
  targetPeriodStart,
  targetPeriodEnd,
  deadline,
  message,
  canExpand,
}: {
  communityId: string;
  requestId: string;
  targetPeriodStart: string;
  targetPeriodEnd: string;
  deadline: string;
  message: string;
  canExpand: boolean;
}) {
  const [expanded, setExpanded] = useState(false);

  const { data: pendingMembers, isLoading } = useQuery({
    queryKey: availabilityKeys.pendingMembers(communityId, requestId),
    queryFn: () => listPendingMembers(communityId, requestId),
    enabled: expanded && canExpand,
  });

  return (
    <Card>
      <CardContent className="flex flex-col gap-2">
        <p className="text-sm font-medium">
          {format(parseISO(targetPeriodStart), "M月d日")} 〜{" "}
          {format(parseISO(targetPeriodEnd), "M月d日")}
        </p>
        <p className="text-muted-foreground text-xs">
          提出期限: {format(parseISO(deadline), "M月d日 HH:mm")}
        </p>
        {message && <p className="text-sm">{message}</p>}

        {canExpand && (
          <Button variant="ghost" size="sm" className="self-start" onClick={() => setExpanded((v) => !v)}>
            未提出者を確認
            {expanded ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
          </Button>
        )}

        {expanded && canExpand && (
          <div className="bg-muted rounded-md p-3">
            {isLoading && <Skeleton className="h-6 w-full" />}
            {!isLoading && pendingMembers?.length === 0 && (
              <p className="text-muted-foreground text-sm">全員提出済みです</p>
            )}
            {!isLoading && pendingMembers && pendingMembers.length > 0 && (
              <ul className="flex flex-col gap-1">
                {pendingMembers.map((member) => (
                  <li key={member.userId} className="text-sm">
                    {member.nickname}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
