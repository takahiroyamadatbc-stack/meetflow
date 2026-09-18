import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { communityKeys, getCommunity } from "@/features/community/api";
import { draftKeys, listDrafts } from "@/features/draft/api";
import { DRAFT_STATUS_LABELS } from "@/features/draft/types";
import { paths } from "@/routes/paths";

/** S-32 Mリーグドラフト一覧画面（docs/draft/DESIGN.md） */
export function DraftListPage() {
  const { communityId } = useParams<{ communityId: string }>();

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
  const isAdmin = community?.role === "OWNER" || community?.role === "ADMIN";

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
        <Link key={draft.draftId} to={paths.draftRoom(draft.draftId)}>
          <Card>
            <CardContent className="flex flex-col gap-2">
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
            </CardContent>
          </Card>
        </Link>
      ))}
    </div>
  );
}
