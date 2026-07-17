import { useMemo, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { format, isSameDay, parseISO } from "date-fns";
import type { DayButton } from "react-day-picker";
import { Calendar } from "@/components/ui/calendar";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { communityKeys, listCommunities } from "@/features/community/api";
import { availabilityKeys, listAvailability } from "@/features/availability/api";
import { eventKeys, listMyEvents } from "@/features/event/api";
import type { Availability } from "@/features/availability/types";
import type { CommunitySummary } from "@/features/community/types";
import { GAME_TYPE_LABELS } from "@/features/user/types";
import { DEFAULT_THEME_COLOR } from "@/features/community/theme-colors";
import { paths } from "@/routes/paths";
import { cn } from "@/lib/utils";

type DayMarker = { color: string; kind: "availability" | "confirmed" };

/**
 * S-10 予定タブ（Issue #12）。
 * バックエンドはコミュニティ単位でしか空き予定を扱えないため、所属コミュニティを
 * 横断してフロント側で集約する（AvailabilityListPageの従来方針を踏襲）。
 * カレンダー表示にし、登録済みの空き予定は日付ごとにコミュニティのテーマカラーを
 * 縦に並べ、確定した予定はそのコミュニティのテーマカラーのみで区別する。
 */
export function AvailabilityListPage() {
  const [selectedDate, setSelectedDate] = useState<Date | undefined>(undefined);

  const { data: communities, isLoading: isLoadingCommunities } = useQuery({
    queryKey: communityKeys.all,
    queryFn: listCommunities,
  });

  const availabilityQueries = useQueries({
    queries: (communities ?? []).map((community) => ({
      queryKey: availabilityKeys.list(community.communityId),
      queryFn: () => listAvailability(community.communityId),
      enabled: !!communities,
    })),
  });

  const { data: myEvents, isLoading: isLoadingEvents } = useQuery({
    queryKey: eventKeys.myEvents,
    queryFn: listMyEvents,
  });

  const isLoading =
    isLoadingCommunities || isLoadingEvents || availabilityQueries.some((q) => q.isLoading);

  const communityById = useMemo(
    () => new Map((communities ?? []).map((c) => [c.communityId, c] as const)),
    [communities],
  );

  const availabilityRows = useMemo(
    () =>
      (communities ?? []).flatMap((community, index) =>
        (availabilityQueries[index]?.data ?? []).map((availability) => ({
          community,
          availability,
        })),
      ),
    [communities, availabilityQueries],
  );

  const markersByDate = useMemo(() => {
    const map = new Map<string, DayMarker[]>();
    for (const { community, availability } of availabilityRows) {
      const key = format(parseISO(availability.startTime), "yyyy-MM-dd");
      const color = community.themeColor ?? DEFAULT_THEME_COLOR;
      const markers = map.get(key) ?? [];
      if (!markers.some((m) => m.kind === "availability" && m.color === color)) {
        markers.push({ color, kind: "availability" });
      }
      map.set(key, markers);
    }
    for (const myEvent of myEvents ?? []) {
      const key = format(parseISO(myEvent.startTime), "yyyy-MM-dd");
      const color = communityById.get(myEvent.communityId)?.themeColor ?? DEFAULT_THEME_COLOR;
      const markers = map.get(key) ?? [];
      markers.unshift({ color, kind: "confirmed" });
      map.set(key, markers);
    }
    return map;
  }, [availabilityRows, myEvents, communityById]);

  const selectedAvailability = useMemo(
    () =>
      selectedDate
        ? availabilityRows.filter((row) =>
            isSameDay(parseISO(row.availability.startTime), selectedDate),
          )
        : [],
    [availabilityRows, selectedDate],
  );

  const selectedEvents = useMemo(
    () =>
      selectedDate
        ? (myEvents ?? []).filter((e) => isSameDay(parseISO(e.startTime), selectedDate))
        : [],
    [myEvents, selectedDate],
  );

  if (isLoading) {
    return (
      <div className="flex flex-col gap-3 p-4">
        <Skeleton className="h-72 w-full" />
      </div>
    );
  }

  const hasAnyData = availabilityRows.length > 0 || (myEvents ?? []).length > 0;
  const hasSelection = selectedDate !== undefined;
  const selectedIsEmpty = selectedEvents.length === 0 && selectedAvailability.length === 0;

  return (
    <div className="flex flex-col gap-4 p-4">
      <Calendar
        mode="single"
        selected={selectedDate}
        onSelect={setSelectedDate}
        className="mx-auto"
        components={{
          DayButton: (props) => <ScheduleDayButton markersByDate={markersByDate} {...props} />,
        }}
      />

      {!hasAnyData && (
        <EmptyState
          message="登録済みの空き予定がありません"
          description="コミュニティ詳細から空き予定を登録してください"
        />
      )}

      {hasAnyData && hasSelection && selectedIsEmpty && (
        <EmptyState message="この日の予定はありません" />
      )}

      {selectedEvents.map((myEvent) => {
        const community = communityById.get(myEvent.communityId);
        const themeColor = community?.themeColor ?? DEFAULT_THEME_COLOR;
        return (
          <Card key={myEvent.eventId} className="border-l-4" style={{ borderLeftColor: themeColor }}>
            <CardContent className="flex flex-col gap-1">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium">
                  {format(parseISO(myEvent.startTime), "HH:mm")} -{" "}
                  {format(parseISO(myEvent.endTime), "HH:mm")}
                </p>
                <Badge>確定</Badge>
              </div>
              <Link
                to={paths.eventDetail(myEvent.eventId)}
                className="text-primary text-xs underline underline-offset-4"
              >
                {community?.name ?? "コミュニティ"}
              </Link>
            </CardContent>
          </Card>
        );
      })}

      {selectedAvailability.map(({ community, availability }) => (
        <AvailabilityRowCard
          key={availability.availabilityId}
          community={community}
          availability={availability}
        />
      ))}
    </div>
  );
}

function AvailabilityRowCard({
  community,
  availability,
}: {
  community: CommunitySummary;
  availability: Availability;
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-1">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium">
            {format(parseISO(availability.startTime), "HH:mm")} -{" "}
            {format(parseISO(availability.endTime), "HH:mm")}
          </p>
          <div className="flex items-center gap-1">
            <Badge variant="secondary">空き予定</Badge>
            <Link to={paths.availabilityCalendar(community.communityId)}>
              <Badge variant="outline">{community.name}</Badge>
            </Link>
          </div>
        </div>
        {availability.gameTypes.length > 0 && (
          <div className="flex gap-1">
            {availability.gameTypes.map((g) => (
              <Badge key={g} variant="secondary">
                {GAME_TYPE_LABELS[g]}
              </Badge>
            ))}
          </div>
        )}
        {availability.comment && (
          <p className="text-muted-foreground text-sm">{availability.comment}</p>
        )}
      </CardContent>
    </Card>
  );
}

function ScheduleDayButton({
  className,
  day,
  modifiers,
  markersByDate,
  ...props
}: React.ComponentProps<typeof DayButton> & { markersByDate: Map<string, DayMarker[]> }) {
  const dateKey = format(day.date, "yyyy-MM-dd");
  const markers = markersByDate.get(dateKey) ?? [];
  const hasConfirmed = markers.some((m) => m.kind === "confirmed");

  return (
    <Button
      variant="ghost"
      size="icon"
      data-selected-single={modifiers.selected}
      className={cn(
        "relative flex aspect-square size-auto w-full min-w-(--cell-size) flex-col items-center justify-center gap-0.5 border-0 font-normal leading-none data-[selected-single=true]:bg-primary data-[selected-single=true]:text-primary-foreground",
        className,
      )}
      {...props}
    >
      <span className={cn(hasConfirmed && "text-primary font-bold data-[selected-single=true]:text-primary-foreground")} data-selected-single={modifiers.selected}>
        {day.date.getDate()}
      </span>
      {markers.length > 0 && (
        <span className="flex flex-col items-center gap-0.5">
          {markers.slice(0, 3).map((marker, i) => (
            <span
              key={i}
              className={marker.kind === "confirmed" ? "size-1.5 rounded-xs" : "size-1 rounded-full"}
              style={{ backgroundColor: marker.color }}
            />
          ))}
        </span>
      )}
    </Button>
  );
}
