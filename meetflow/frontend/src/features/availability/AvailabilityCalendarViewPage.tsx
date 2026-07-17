import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { format, isSameDay, parseISO } from "date-fns";
import { toast } from "sonner";
import { Calendar } from "@/components/ui/calendar";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { EmptyState } from "@/components/feedback/EmptyState";
import {
  availabilityKeys,
  deleteAvailability,
  listAvailability,
  updateAvailability,
} from "@/features/availability/api";
import {
  TimeSlotSheet,
  type TimeSlotValue,
} from "@/features/availability/components/TimeSlotSheet";
import type { Availability } from "@/features/availability/types";
import { GAME_TYPE_LABELS } from "@/features/user/types";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { paths } from "@/routes/paths";

/**
 * コミュニティ詳細から遷移する、登録済み空き予定の確認・編集画面（Issue #11）。
 * カレンダー上に登録済みの日をマーカー表示し、日付を選択するとその日の
 * 空き予定一覧（編集・削除）が下に表示される。
 */
export function AvailabilityCalendarViewPage() {
  const { communityId } = useParams<{ communityId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();
  const [selectedDate, setSelectedDate] = useState<Date | undefined>(undefined);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [editTarget, setEditTarget] = useState<Availability | null>(null);

  const { data: availabilities, isLoading } = useQuery({
    queryKey: availabilityKeys.list(communityId!),
    queryFn: () => listAvailability(communityId!),
    enabled: !!communityId,
  });

  const datesWithAvailability = useMemo(
    () => (availabilities ?? []).map((a) => parseISO(a.startTime)),
    [availabilities],
  );

  const selectedDayItems = useMemo(
    () =>
      selectedDate
        ? (availabilities ?? []).filter((a) => isSameDay(parseISO(a.startTime), selectedDate))
        : [],
    [availabilities, selectedDate],
  );

  const deleteMutation = useMutation({
    mutationFn: deleteAvailability,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: availabilityKeys.list(communityId!) });
      toast.success("空き予定を削除しました");
    },
    onError: handleApiError,
    onSettled: () => setDeleteTarget(null),
  });

  const editMutation = useMutation({
    mutationFn: (value: TimeSlotValue) => {
      const dateStr = format(parseISO(editTarget!.startTime), "yyyy-MM-dd");
      return updateAvailability(editTarget!.availabilityId, {
        startTime: `${dateStr}T${value.startHour}:00`,
        endTime: `${dateStr}T${value.endHour}:00`,
        gameTypes: value.gameTypes,
        comment: value.comment,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: availabilityKeys.list(communityId!) });
      toast.success("空き予定を変更しました");
      setEditTarget(null);
    },
    onError: handleApiError,
  });

  if (isLoading) {
    return (
      <div className="flex flex-col gap-3 p-4">
        <Skeleton className="h-72 w-full" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <Calendar
        mode="single"
        selected={selectedDate}
        onSelect={setSelectedDate}
        modifiers={{ hasAvailability: datesWithAvailability }}
        modifiersClassNames={{
          hasAvailability:
            "after:absolute after:bottom-1 after:left-1/2 after:size-1 after:-translate-x-1/2 after:rounded-full after:bg-primary after:content-['']",
        }}
        className="mx-auto"
      />

      <Button onClick={() => navigate(paths.availabilityNew(communityId!))}>
        空き予定を登録する
      </Button>

      {selectedDate && selectedDayItems.length === 0 && (
        <EmptyState message="この日の登録済み空き予定はありません" />
      )}

      {selectedDate &&
        selectedDayItems.map((availability) => (
          <Card key={availability.availabilityId}>
            <CardContent className="flex flex-col gap-1">
              <p className="text-sm font-medium">
                {format(parseISO(availability.startTime), "HH:mm")} -{" "}
                {format(parseISO(availability.endTime), "HH:mm")}
              </p>
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
              <div className="mt-2 flex gap-2">
                <Button variant="outline" size="sm" onClick={() => setEditTarget(availability)}>
                  編集する
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setDeleteTarget(availability.availabilityId)}
                >
                  削除する
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}

      <TimeSlotSheet
        open={editTarget !== null}
        onOpenChange={(open) => !open && setEditTarget(null)}
        selectedDateCount={1}
        submitting={editMutation.isPending}
        onSubmit={(value) => editMutation.mutate(value)}
        isEditMode={editTarget !== null}
        initialValue={
          editTarget
            ? {
                startHour: format(parseISO(editTarget.startTime), "HH:mm"),
                endHour: format(parseISO(editTarget.endTime), "HH:mm"),
                gameTypes: editTarget.gameTypes,
                comment: editTarget.comment,
              }
            : undefined
        }
      />

      <AlertDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>この空き予定を削除しますか？</AlertDialogTitle>
          </AlertDialogHeader>
          <div className="flex justify-end gap-2 px-4 pb-4">
            <AlertDialogCancel>キャンセル</AlertDialogCancel>
            <AlertDialogAction onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget)}>
              削除する
            </AlertDialogAction>
          </div>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
