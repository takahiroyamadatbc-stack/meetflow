import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { format, isSameDay, parseISO } from "date-fns";
import { Calendar } from "@/components/ui/calendar";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  availabilityKeys,
  createAvailabilityBatch,
  listAvailability,
} from "@/features/availability/api";
import {
  TimeSlotSheet,
  type TimeSlotValue,
} from "@/features/availability/components/TimeSlotSheet";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import type { AvailabilityInput } from "@/features/availability/types";

/**
 * S-09 空き予定登録画面（カレンダーで複数日選択→時間帯パネルでバッチ登録）。
 * 登録済みの日はカレンダー上にドットマーカーを表示し（Issue #21）、
 * その日を含めて登録しようとした場合は確認ダイアログを挟んで気づかない
 * 二重登録を防ぐ。カレンダーの選択モード自体（複数日選択→バッチ登録）
 * は変更しない。
 */
export function AvailabilityCalendarPage() {
  const { communityId } = useParams<{ communityId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();

  const [selectedDates, setSelectedDates] = useState<Date[]>([]);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [pendingEntries, setPendingEntries] = useState<AvailabilityInput[] | null>(null);

  const { data: availabilities } = useQuery({
    queryKey: availabilityKeys.list(communityId!),
    queryFn: () => listAvailability(communityId!),
    enabled: !!communityId,
  });

  const datesWithAvailability = useMemo(
    () => (availabilities ?? []).map((a) => parseISO(a.startTime)),
    [availabilities],
  );

  const overlappingDateLabels = useMemo(
    () =>
      selectedDates
        .filter((date) => datesWithAvailability.some((existing) => isSameDay(existing, date)))
        .map((date) => format(date, "M月d日")),
    [selectedDates, datesWithAvailability],
  );

  const mutation = useMutation({
    mutationFn: (entries: AvailabilityInput[]) => createAvailabilityBatch(communityId!, entries),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: availabilityKeys.list(communityId!) });
      toast.success("空き予定を登録しました");
      navigate(-1);
    },
    onError: handleApiError,
    onSettled: () => setPendingEntries(null),
  });

  function handleSubmit(value: TimeSlotValue) {
    const entries: AvailabilityInput[] = selectedDates.map((date) => {
      const dateStr = format(date, "yyyy-MM-dd");
      return {
        startTime: `${dateStr}T${value.startHour}:00`,
        endTime: `${dateStr}T${value.endHour}:00`,
        gameTypes: value.gameTypes,
        comment: value.comment,
      };
    });
    setSheetOpen(false);
    if (overlappingDateLabels.length > 0) {
      setPendingEntries(entries);
      return;
    }
    mutation.mutate(entries);
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <Calendar
        mode="multiple"
        selected={selectedDates}
        onSelect={(dates) => setSelectedDates(dates ?? [])}
        disabled={{ before: new Date() }}
        modifiers={{ hasAvailability: datesWithAvailability }}
        modifiersClassNames={{
          hasAvailability:
            "after:absolute after:bottom-1 after:left-1/2 after:size-1 after:-translate-x-1/2 after:rounded-full after:bg-primary after:content-['']",
        }}
        className="mx-auto"
      />
      <Button disabled={selectedDates.length === 0} onClick={() => setSheetOpen(true)}>
        {selectedDates.length > 0
          ? `${selectedDates.length}日を選択中 - 時間帯を設定する`
          : "日付を選択してください"}
      </Button>

      <TimeSlotSheet
        open={sheetOpen}
        onOpenChange={setSheetOpen}
        selectedDateCount={selectedDates.length}
        submitting={mutation.isPending}
        onSubmit={handleSubmit}
      />

      <AlertDialog
        open={pendingEntries !== null}
        onOpenChange={(open) => !open && setPendingEntries(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>登録済みの日付が含まれています</AlertDialogTitle>
            <AlertDialogDescription>
              {overlappingDateLabels.join("、")}
              には既に空き予定が登録されています。このまま登録すると、同じ日に重複して登録されることになります。続けますか？
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="flex justify-end gap-2 px-4 pb-4">
            <AlertDialogCancel>キャンセル</AlertDialogCancel>
            <AlertDialogAction onClick={() => pendingEntries && mutation.mutate(pendingEntries)}>
              続けて登録する
            </AlertDialogAction>
          </div>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
