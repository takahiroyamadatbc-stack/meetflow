import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { toast } from "sonner";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { RoleBadge } from "@/features/community/components/RoleBadge";
import { communityKeys, deleteCommunity, getCommunity, leaveCommunity } from "@/features/community/api";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { paths } from "@/routes/paths";

/** S-05 コミュニティ詳細画面 */
export function CommunityDetailPage() {
  const { communityId } = useParams<{ communityId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [leaveDialogOpen, setLeaveDialogOpen] = useState(false);

  const { data: community, isLoading } = useQuery({
    queryKey: communityKeys.detail(communityId!),
    queryFn: () => getCommunity(communityId!),
    enabled: !!communityId,
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteCommunity(communityId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: communityKeys.all });
      toast.success("コミュニティを削除しました");
      navigate(paths.communityList, { replace: true });
    },
    onError: handleApiError,
    onSettled: () => setDeleteDialogOpen(false),
  });

  const leaveMutation = useMutation({
    mutationFn: () => leaveCommunity(communityId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: communityKeys.all });
      toast.success("コミュニティを退会しました");
      navigate(paths.communityList, { replace: true });
    },
    onError: handleApiError,
    onSettled: () => setLeaveDialogOpen(false),
  });

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4 p-4">
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (!community) {
    return <EmptyState message="コミュニティが見つかりません" />;
  }

  const isAdmin = community.role === "OWNER" || community.role === "ADMIN";

  return (
    <div className="flex flex-col gap-4 p-4">
      <Card>
        <CardContent className="flex flex-col gap-1">
          {community.themeColor && (
            <div
              className="mb-1 h-1.5 w-10 rounded-full"
              style={{ backgroundColor: community.themeColor }}
            />
          )}
          <div className="flex items-center justify-between">
            <p className="text-base font-semibold">{community.name}</p>
            <RoleBadge role={community.role} />
          </div>
          {community.genre && <p className="text-muted-foreground text-xs">{community.genre}</p>}
          {community.description && <p className="text-sm">{community.description}</p>}
          {community.memberApprovalRequired && (
            <Badge variant="outline" className="mt-1 self-start">
              参加に承認が必要
            </Badge>
          )}
        </CardContent>
      </Card>

      <NavCard to={paths.communityInvite(community.communityId)} label="メンバーを招待する" />
      <NavCard to={paths.eventList(community.communityId)} label="イベント一覧" />

      <Accordion className="flex flex-col gap-2">
        {isAdmin && (
          <AccordionItem value="admin">
            <AccordionTrigger>管理者メニュー</AccordionTrigger>
            <AccordionContent>
              <div className="flex flex-col gap-3">
                <NavCard
                  to={paths.communityJoinRequests(community.communityId)}
                  label="参加リクエスト一覧"
                  badgeCount={community.pendingRequestCount}
                />
                <NavCard
                  to={paths.availabilityRequestList(community.communityId)}
                  label="空き予定提出リクエスト"
                />
                <NavCard
                  to={paths.communityProfileEdit(community.communityId)}
                  label="コミュニティプロフィールを編集"
                />
              </div>
            </AccordionContent>
          </AccordionItem>
        )}

        <AccordionItem value="member">
          <AccordionTrigger>メンバー</AccordionTrigger>
          <AccordionContent>
            <div className="flex flex-col gap-3">
              <NavCard to={paths.communityMembers(community.communityId)} label="メンバー一覧" />
            </div>
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="availability">
          <AccordionTrigger>空き予定</AccordionTrigger>
          <AccordionContent>
            <div className="flex flex-col gap-3">
              <NavCard
                to={paths.availabilityNew(community.communityId)}
                label="空き予定を登録する"
              />
              <NavCard
                to={paths.availabilityCalendar(community.communityId)}
                label="登録済みの空き予定を確認・編集する"
              />
            </div>
          </AccordionContent>
        </AccordionItem>

        {isAdmin && (
          <AccordionItem value="matching">
            <AccordionTrigger>マッチング</AccordionTrigger>
            <AccordionContent>
              <div className="flex flex-col gap-3">
                <NavCard to={paths.eventTemplateList(community.communityId)} label="開催条件" />
                <NavCard
                  to={paths.matchingCandidateList(community.communityId)}
                  label="マッチング候補"
                />
              </div>
            </AccordionContent>
          </AccordionItem>
        )}

        <AccordionItem value="settings">
          <AccordionTrigger>設定</AccordionTrigger>
          <AccordionContent>
            <div className="flex flex-col gap-3">
              <NavCard
                to={paths.communityDisplayNameEdit(community.communityId)}
                label="このコミュニティでの表示名を変更"
              />
              <NavCard
                to={paths.communityAutoApproveEdit(community.communityId)}
                label="このコミュニティでの自動承認設定を変更"
              />
              <NavCard
                to={paths.communityFrequencyLimitEdit(community.communityId)}
                label="このコミュニティでの参加頻度上限を変更"
              />
            </div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>

      {community.role !== "OWNER" && (
        <>
          <Separator className="my-2" />
          <Button
            variant="destructive"
            className="self-start"
            onClick={() => setLeaveDialogOpen(true)}
          >
            このコミュニティを退会する
          </Button>
        </>
      )}

      {community.role === "OWNER" && (
        <>
          <Separator className="my-2" />
          <Button
            variant="destructive"
            className="self-start"
            onClick={() => setDeleteDialogOpen(true)}
          >
            コミュニティを削除する
          </Button>
        </>
      )}

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>このコミュニティを削除しますか？</AlertDialogTitle>
            <AlertDialogDescription>
              自分以外のメンバーが在籍している場合は削除できません。この操作は取り消せません。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="flex justify-end gap-2 px-4 pb-4">
            <AlertDialogCancel>キャンセル</AlertDialogCancel>
            <AlertDialogAction
              disabled={deleteMutation.isPending}
              onClick={() => deleteMutation.mutate()}
            >
              削除する
            </AlertDialogAction>
          </div>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={leaveDialogOpen} onOpenChange={setLeaveDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>このコミュニティを退会しますか？</AlertDialogTitle>
            <AlertDialogDescription>
              未来の確定イベント参加が残っている場合は退会できません。この操作は取り消せません。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="flex justify-end gap-2 px-4 pb-4">
            <AlertDialogCancel>キャンセル</AlertDialogCancel>
            <AlertDialogAction
              disabled={leaveMutation.isPending}
              onClick={() => leaveMutation.mutate()}
            >
              退会する
            </AlertDialogAction>
          </div>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function NavCard({
  to,
  label,
  badgeCount,
}: {
  to: string;
  label: string;
  badgeCount?: number;
}) {
  return (
    <Link to={to}>
      <Card>
        <CardContent className="flex items-center justify-between">
          <span className="flex items-center gap-2 text-sm">
            {label}
            {!!badgeCount && <Badge variant="destructive">{badgeCount}</Badge>}
          </span>
          <ChevronRight className="text-muted-foreground size-4" />
        </CardContent>
      </Card>
    </Link>
  );
}
