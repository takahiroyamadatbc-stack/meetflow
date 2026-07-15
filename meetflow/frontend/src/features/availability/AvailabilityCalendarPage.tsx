import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { format } from "date-fns";
import { Calendar } from "@/components/ui/calendar";
import { Button } from "@/components/ui/button";
import { availabilityKeys, createAvailabilityBatch } from "@/features/availability/api";
import {
  TimeSlotSheet,
  type TimeSlotValue,
} from "@/features/availability/components/TimeSlotSheet";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import type { AvailabilityInput } from "@/features/availability/types";

/** S-09 空き予定登録画面（カレンダーで複数日選択→時間帯パネルでバッチ登録） */
export function AvailabilityCalendarPage() {
  const { communityId } = useParams<{ communityId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();

  const [selectedDates, setSelectedDates] = useState<Date[]>([]);
  const [sheetOpen, setSheetOpen] = useState(false);

  const mutation = useMutation({
    mutationFn: (entries: AvailabilityInput[]) => createAvailabilityBatch(communityId!, entries),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: availabilityKeys.list(communityId!) });
      toast.success("空き予定を登録しました");
      navigate(-1);
    },
    onError: handleApiError,
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
    mutation.mutate(entries);
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <Calendar
        mode="multiple"
        selected={selectedDates}
        onSelect={(dates) => setSelectedDates(dates ?? [])}
        disabled={{ before: new Date() }}
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
    </div>
  );
}
