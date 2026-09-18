import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { communityKeys, getCommunity } from "@/features/community/api";
import { deleteDraft, draftKeys, listDrafts } from "@/features/draft/api";
import { DRAFT_STATUS_LABELS } from "@/features/draft/types";
import type { DraftSummary } from "@/features/draft/types";
import { paths } from "@/routes/paths";

/** S-32 Mリーグドラフト一覧画面（docs/draft/DESIGN.md） */
export function DraftListPage() {
  const { communityId } = useParams<{ communityId: string }>();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();
  // 削除対象のドラフト。ダイアログに名前を出すので、真偽値ではなく実体で持つ。
  const [pendingDelete, setPendingDelete] = useState<DraftSummary | null>(null);

  const { data: community } = useQuery({
    queryKey: communityKeys.detail(communityId!),
    queryFn: () => getCommunity(communityId!),
    enabled: !!communityId,
  });

  const { data: drafts, isLoading } = useQuery({
    queryKey: draftKeys.list(communityId!),
    queryFn: () => listDrafts(communityId!),
    enabled: !!communityId,
  });

  // DESIGN.md §4.13: ドラフトの作成は他の管理操作と揃えてOWNER/ADMINのみ。
  // 削除も同じ。
  const isAdmin = community?.role === "OWNER" || community?.role === "ADMIN";

  const deleteMutation = useMutation({
    mutationFn: (draftId: string) => deleteDraft(draftId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: draftKeys.list(communityId!) });
      toast.success("ドラフトを削除しました");
    },
    onError: handleApiError,
    onSettled: () => setPendingDelete(null),
  });

  if (isLoading) {
    return (
      <div className="flex flex-col gap-3 p-4">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 p-4">
      {isAdmin && (
        <Link to={paths.draftNew(communityId!)}>
          <Button className="w-full">＋ドラフトを作成</Button>
        </Link>
      )}

      {(drafts ?? []).length === 0 && (
        <EmptyState
          message="ドラフトがまだありません"
          description="Mリーグの選手を指名して、シーズンの獲得ポイントで競います"
        />
      )}

      {(drafts ?? []).map((draft) => (
        <Card key={draft.draftId}>
          <CardContent className="flex flex-col gap-2">
            {/* 削除ボタンはLinkの外に出す。中に入れると入れ子のクリック領域に
                なり、消すつもりが開いてしまう。 */}
            <Link to={paths.draftRoom(draft.draftId)} className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{draft.name}</span>
                <Badge variant={draft.status === "COMPLETED" ? "secondary" : "default"}>
                  {DRAFT_STATUS_LABELS[draft.status]}
                </Badge>
              </div>
              <p className="text-muted-foreground text-xs">
                {draft.season}シーズン ／ {draft.participantCount}人
                {draft.status !== "SETUP" && draft.status !== "COMPLETED" && (
                  <> ／ {draft.round}巡目</>
                )}
              </p>
            </Link>
            {isAdmin && (
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive self-end"
                onClick={() => setPendingDelete(draft)}
              >
                削除
              </Button>
            )}
          </CardContent>
        </Card>
      ))}

      <AlertDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              「{pendingDelete?.name}」を削除しますか？
            </AlertDialogTitle>
          </AlertDialogHeader>
          <p className="text-muted-foreground px-4 text-sm">
            指名結果・抽選の記録・順位がすべて消え、元に戻せません。
          </p>
          <div className="flex justify-end gap-2 px-4 pb-4">
            <AlertDialogCancel>キャンセル</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => pendingDelete && deleteMutation.mutate(pendingDelete.draftId)}
              disabled={deleteMutation.isPending}
            >
              削除する
            </AlertDialogAction>
          </div>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
