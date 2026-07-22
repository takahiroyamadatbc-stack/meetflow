import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { format, parseISO } from "date-fns";
import { Calendar } from "@/components/ui/calendar";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  availabilityKeys,
  createAvailabilityBatch,
  listAvailability,
} from "@/features/availability/api";
import {
  TimeSlotSheet,
  type TimeSlotValue,
} from "@/features/availability/components/TimeSlotSheet";
import { NearMissBanner } from "@/features/availability/NearMissBanner";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import type { AvailabilityInput } from "@/features/availability/types";
import type { GameType } from "@/features/user/types";
import { updateMyProfile, userKeys } from "@/features/user/api";

/**
 * S-09 空き予定登録画面（カレンダーで複数日選択→時間帯パネルでバッチ登録）。
 * 登録済みの日はカレンダー上にドットマーカーを表示し、選択自体もできない
 * ようにする（Issue #21）ことで二重登録を防ぐ。時間帯パネルの初期値は
 * 前回登録した空き予定の時刻から算出する。カレンダーの選択モード自体
 * （複数日選択→バッチ登録）は変更しない。
 */
export function AvailabilityCalendarPage() {
  const { communityId } = useParams<{ communityId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();

  const [selectedDates, setSelectedDates] = useState<Date[]>([]);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [autoApprove, setAutoApprove] = useState(false);

  const { data: availabilities } = useQuery({
    queryKey: availabilityKeys.list(communityId!),
    queryFn: () => listAvailability(communityId!),
    enabled: !!communityId,
  });

  const datesWithAvailability = useMemo(
    () => (availabilities ?? []).map((a) => parseISO(a.startTime)),
    [availabilities],
  );

  const latestTimeSlot = useMemo<TimeSlotValue | undefined>(() => {
    if (!availabilities || availabilities.length === 0) return undefined;
    const latest = availabilities.reduce((a, b) => (a.startTime > b.startTime ? a : b));
    return {
      startHour: format(parseISO(latest.startTime), "HH:mm"),
      endHour: format(parseISO(latest.endTime), "HH:mm"),
      gameTypes: [] as GameType[],
      comment: "",
    };
  }, [availabilities]);

  const mutation = useMutation({
    mutationFn: async (entries: AvailabilityInput[]) => {
      await createAvailabilityBatch(communityId!, entries);
      if (autoApprove) {
        await updateMyProfile({ autoApprove: true });
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: availabilityKeys.list(communityId!) });
      if (autoApprove) {
        queryClient.invalidateQueries({ queryKey: userKeys.me });
      }
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
    setSheetOpen(false);
    mutation.mutate(entries);
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      {/* Issue #96: 既に空き予定を提出済みのメンバーにのみ「あと〇人で
          成立」を見せ、ワンタップで空きを追加する導線を出す */}
      {communityId && <NearMissBanner communityId={communityId} />}
      <Calendar
        mode="multiple"
        selected={selectedDates}
        onSelect={(dates) => setSelectedDates(dates ?? [])}
        disabled={[{ before: new Date() }, ...datesWithAvailability]}
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

      <div className="flex items-center gap-2">
        <Checkbox
          id="auto-approve"
          checked={autoApprove}
          onCheckedChange={(checked) => setAutoApprove(checked === true)}
        />
        <Label htmlFor="auto-approve" className="text-sm font-normal">
          次回以降は参加を自動承認する
        </Label>
      </div>

      <TimeSlotSheet
        open={sheetOpen}
        onOpenChange={setSheetOpen}
        selectedDateCount={selectedDates.length}
        submitting={mutation.isPending}
        onSubmit={handleSubmit}
        initialValue={latestTimeSlot}
      />
    </div>
  );
}
