import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import { communityKeys, getCommunity } from "@/features/community/api";
import {
  deleteEventTemplate,
  listEventTemplates,
  matchingKeys,
} from "@/features/matching/api";
import { GAME_TYPE_LABELS } from "@/features/user/types";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { paths } from "@/routes/paths";

/** S-11 開催条件一覧画面 */
export function EventTemplateListPage() {
  const { communityId } = useParams<{ communityId: string }>();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  const { data: community } = useQuery({
    queryKey: communityKeys.detail(communityId!),
    queryFn: () => getCommunity(communityId!),
    enabled: !!communityId,
  });

  const { data: templates, isLoading } = useQuery({
    queryKey: matchingKeys.templates(communityId!),
    queryFn: () => listEventTemplates(communityId!),
    enabled: !!communityId,
  });

  const deleteMutation = useMutation({
    mutationFn: (templateId: string) => deleteEventTemplate(communityId!, templateId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: matchingKeys.templates(communityId!) });
      toast.success("開催条件を削除しました");
    },
    onError: handleApiError,
    onSettled: () => setDeleteTarget(null),
  });

  const isAdmin = community?.role === "OWNER" || community?.role === "ADMIN";

  if (isLoading) {
    return (
      <div className="flex flex-col gap-3 p-4">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    );
  }

  const sorted = [...(templates ?? [])].sort((a, b) => b.priority - a.priority);

  return (
    <div className="flex flex-col gap-3 p-4">
      {isAdmin && (
        <Link to={paths.eventTemplateNew(communityId!)}>
          <Button className="w-full">＋開催条件を追加</Button>
        </Link>
      )}

      {sorted.length === 0 && (
        <EmptyState
          message="開催条件がまだありません"
          description="開催条件を登録するとマッチング候補を生成できます"
        />
      )}

      {sorted.map((template) => (
        <Card key={template.templateId}>
          <CardContent className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">{GAME_TYPE_LABELS[template.gameType]}</span>
              <Badge variant="outline">優先度 {template.priority}</Badge>
            </div>
            <p className="text-muted-foreground text-sm">
              {template.minPlayers}〜{template.maxPlayers}人
            </p>
            {template.conditions.beginnerOk && <Badge variant="secondary">初心者歓迎</Badge>}
            {isAdmin && (
              <div className="mt-2 flex gap-2">
                <Link to={paths.eventTemplateEdit(communityId!, template.templateId)}>
                  <Button variant="outline" size="sm">
                    編集する
                  </Button>
                </Link>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setDeleteTarget(template.templateId)}
                >
                  削除する
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      ))}

      <AlertDialog open={deleteTarget !== null} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>この開催条件を削除しますか？</AlertDialogTitle>
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
