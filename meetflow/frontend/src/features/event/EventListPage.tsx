import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { format, parseISO } from "date-fns";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { eventKeys, listCommunityEvents } from "@/features/event/api";
import { EVENT_STATUS_LABELS } from "@/features/event/types";
import { paths } from "@/routes/paths";

const UPCOMING_STATUSES = "OPEN,MATCHING,PENDING_APPROVAL,CONFIRMED,IN_PROGRESS";
const PAST_STATUSES = "COMPLETED,CANCELLED";

/** S-17 イベント一覧画面 */
export function EventListPage() {
  const { communityId } = useParams<{ communityId: string }>();
  const [tab, setTab] = useState<"upcoming" | "past">("upcoming");
  const status = tab === "upcoming" ? UPCOMING_STATUSES : PAST_STATUSES;

  const { data: events, isLoading } = useQuery({
    queryKey: eventKeys.communityEvents(communityId!, status),
    queryFn: () => listCommunityEvents(communityId!, status),
    enabled: !!communityId,
  });

  return (
    <div className="flex flex-col gap-3 p-4">
      <div className="flex gap-2">
        <Button
          type="button"
          variant={tab === "upcoming" ? "default" : "outline"}
          size="sm"
          onClick={() => setTab("upcoming")}
        >
          開催予定
        </Button>
        <Button
          type="button"
          variant={tab === "past" ? "default" : "outline"}
          size="sm"
          onClick={() => setTab("past")}
        >
          過去
        </Button>
      </div>

      {isLoading ? (
        <Skeleton className="h-20 w-full" />
      ) : (events ?? []).length === 0 ? (
        <EmptyState message="イベントがありません" />
      ) : (
        (events ?? []).map((event) => (
          <Link key={event.eventId} to={paths.eventDetail(event.eventId)}>
            <Card>
              <CardContent className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium">
                    {format(parseISO(event.startTime), "M月d日 HH:mm")}
                  </p>
                  {event.locationName && (
                    <p className="text-muted-foreground text-xs">{event.locationName}</p>
                  )}
                </div>
                <Badge variant="outline">{EVENT_STATUS_LABELS[event.status]}</Badge>
              </CardContent>
            </Card>
          </Link>
        ))
      )}
    </div>
  );
}
