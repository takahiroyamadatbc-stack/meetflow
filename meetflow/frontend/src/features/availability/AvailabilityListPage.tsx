import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { format, parseISO } from "date-fns";
import { toast } from "sonner";
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
import { communityKeys, listCommunities } from "@/features/community/api";
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
import { useState } from "react";

/**
 * S-10 空き予定一覧画面。
 * バックエンドはコミュニティ単位でしか空き予定を扱えないため（食い違い#と別に、
 * Phase1実装計画の申し送り事項参照）、所属コミュニティを横断してフロント側で
 * 集約する。
 */
export function AvailabilityListPage() {
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [editTarget, setEditTarget] = useState<Availability | null>(null);

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

  const deleteMutation = useMutation({
    mutationFn: deleteAvailability,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["availability"] });
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
      queryClient.invalidateQueries({ queryKey: ["availability"] });
      toast.success("空き予定を変更しました");
      setEditTarget(null);
    },
    onError: handleApiError,
  });

  const isLoading = isLoadingCommunities || availabilityQueries.some((q) => q.isLoading);

  if (isLoading) {
    return (
      <div className="flex flex-col gap-3 p-4">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }

  const rows = (communities ?? []).flatMap((community, index) =>
    (availabilityQueries[index]?.data ?? []).map((availability) => ({
      community,
      availability,
    })),
  );
  rows.sort((a, b) => a.availability.startTime.localeCompare(b.availability.startTime));

  if (rows.length === 0) {
    return (
      <EmptyState
        message="登録済みの空き予定がありません"
        description="コミュニティ詳細から空き予定を登録してください"
      />
    );
  }

  return (
    <div className="flex flex-col gap-3 p-4">
      {rows.map(({ community, availability }) => (
        <Card key={availability.availabilityId}>
          <CardContent className="flex flex-col gap-1">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium">
                {format(parseISO(availability.startTime), "M月d日 HH:mm")} -{" "}
                {format(parseISO(availability.endTime), "HH:mm")}
              </p>
              <Link to={paths.communityDetail(community.communityId)}>
                <Badge variant="outline">{community.name}</Badge>
              </Link>
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

      <AlertDialog open={deleteTarget !== null} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>この空き予定を削除しますか？</AlertDialogTitle>
          </AlertDialogHeader>
          <div className="flex justify-end gap-2 px-4 pb-4">
            <AlertDialogCancel>キャンセル</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget)}
            >
              削除する
            </AlertDialogAction>
          </div>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
