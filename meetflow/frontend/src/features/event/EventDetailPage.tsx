import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { format, parseISO } from "date-fns";
import { toast } from "sonner";
import { X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { EmptyState } from "@/components/feedback/EmptyState";
import { communityKeys, getCommunity, listMembers } from "@/features/community/api";
import {
  addParticipant,
  approveParticipation,
  cancelEvent,
  completeEvent,
  confirmEvent,
  eventKeys,
  getEvent,
  listCancelRequests,
  listParticipants,
  rejectParticipation,
  removeParticipant,
  reopenEvent,
  updateEventMemo,
} from "@/features/event/api";
import { EVENT_STATUS_LABELS, PARTICIPANT_STATUS_LABELS } from "@/features/event/types";
import { getCandidateDetail, matchingKeys } from "@/features/matching/api";
import { listEventSessions, resultKeys } from "@/features/result/api";
import { GAME_TYPE_LABELS } from "@/features/user/types";
import { QuickFeedbackPrompt } from "@/features/feedback/QuickFeedbackPrompt";
import { useAuthUser } from "@/features/auth/useAuthUser";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { paths } from "@/routes/paths";

/** S-16 イベント詳細画面 */
export function EventDetailPage() {
  const { eventId } = useParams<{ eventId: string }>();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();
  const { userId } = useAuthUser();
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);
  const [showRejectConfirm, setShowRejectConfirm] = useState(false);
  const [showCompleteConfirm, setShowCompleteConfirm] = useState(false);
  const [showReopenConfirm, setShowReopenConfirm] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [newMemberId, setNewMemberId] = useState("");
  const [removeTargetUserId, setRemoveTargetUserId] = useState<string | null>(null);
  const [isEditingMemo, setIsEditingMemo] = useState(false);
  const [memoDraft, setMemoDraft] = useState("");

  const { data: event, isLoading } = useQuery({
    queryKey: eventKeys.detail(eventId!),
    queryFn: () => getEvent(eventId!),
    enabled: !!eventId,
  });

  const { data: community } = useQuery({
    queryKey: communityKeys.detail(event?.communityId ?? ""),
    queryFn: () => getCommunity(event!.communityId),
    enabled: !!event?.communityId,
  });

  const { data: participants } = useQuery({
    queryKey: eventKeys.participants(eventId!),
    queryFn: () => listParticipants(eventId!),
    enabled: !!eventId,
  });

  const { data: cancelRequests } = useQuery({
    queryKey: eventKeys.cancelRequests(eventId!),
    queryFn: () => listCancelRequests(eventId!),
    enabled: !!eventId && (community?.role === "OWNER" || community?.role === "ADMIN"),
  });

  const isAdmin = community?.role === "OWNER" || community?.role === "ADMIN";
  // Issue #79: 仮確定前(PENDING_APPROVAL)は参加者(Participant)がまだ
  // 存在しないため、候補(MatchCandidate)のメンバー一覧を取得して
  // チェックボックスで選択可能にする。
  const { data: candidate } = useQuery({
    queryKey: matchingKeys.candidateDetail(event?.candidateId ?? ""),
    queryFn: () => getCandidateDetail(event!.candidateId!),
    enabled: !!event?.candidateId && event?.status === "PENDING_APPROVAL" && isAdmin,
  });

  const [selectedMemberIds, setSelectedMemberIds] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (candidate) {
      setSelectedMemberIds(new Set(candidate.members.map((m) => m.userId)));
    }
  }, [candidate]);

  // Issue #78(F-603のMVP前倒し): 確定後のメンバー追加候補一覧。
  const { data: communityMembers } = useQuery({
    queryKey: communityKeys.members(event?.communityId ?? ""),
    queryFn: () => listMembers(event!.communityId),
    enabled: !!event?.communityId && event?.status === "CONFIRMED" && isAdmin,
  });

  // COMPLETED/IN_PROGRESSへの状態遷移が未実装なため、実運用で唯一到達
  // 可能なCONFIRMED状態を成績入力の解禁条件にしている（Issue #20）。
  const canManageResults =
    event?.status === "CONFIRMED" ||
    event?.status === "IN_PROGRESS" ||
    event?.status === "COMPLETED";
  const { data: sessions } = useQuery({
    queryKey: resultKeys.eventSessions(eventId!),
    queryFn: () => listEventSessions(eventId!),
    enabled: !!eventId && canManageResults,
  });

  const confirmMutation = useMutation({
    mutationFn: () =>
      confirmEvent(eventId!, candidate ? Array.from(selectedMemberIds) : undefined),
    onSuccess: (updated) => {
      queryClient.setQueryData(eventKeys.detail(eventId!), updated);
      queryClient.invalidateQueries({ queryKey: eventKeys.participants(eventId!) });
      toast.success(
        updated.status === "CONFIRMED"
          ? "イベントを仮確定しました。全員が自動承認済みのため、そのまま確定しました"
          : "イベントを仮確定しました。参加予定者全員の承認を待っています",
      );
    },
    onError: handleApiError,
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelEvent(eventId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: eventKeys.detail(eventId!) });
      toast.success("イベントを中止しました");
    },
    onError: handleApiError,
    onSettled: () => setShowCancelConfirm(false),
  });

  const completeMutation = useMutation({
    mutationFn: () => completeEvent(eventId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: eventKeys.detail(eventId!) });
      toast.success("本日の対局を終了しました。成績がコミュニティの通算成績に反映されます");
    },
    onError: handleApiError,
    onSettled: () => setShowCompleteConfirm(false),
  });

  const reopenMutation = useMutation({
    mutationFn: () => reopenEvent(eventId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: eventKeys.detail(eventId!) });
      toast.success("イベントを開催予定に戻しました");
    },
    onError: handleApiError,
    onSettled: () => setShowReopenConfirm(false),
  });

  const approveParticipationMutation = useMutation({
    mutationFn: () => approveParticipation(eventId!),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: eventKeys.detail(eventId!) });
      queryClient.invalidateQueries({ queryKey: eventKeys.participants(eventId!) });
      toast.success(
        result.eventStatus === "CONFIRMED"
          ? "参加を承認しました。全員の承認が完了し、イベントが確定しました"
          : "参加を承認しました",
      );
    },
    onError: handleApiError,
  });

  const rejectParticipationMutation = useMutation({
    mutationFn: () => rejectParticipation(eventId!, rejectReason || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: eventKeys.detail(eventId!) });
      queryClient.invalidateQueries({ queryKey: eventKeys.participants(eventId!) });
      toast.success("参加を辞退しました。管理者に通知されます");
    },
    onError: handleApiError,
    onSettled: () => {
      setShowRejectConfirm(false);
      setRejectReason("");
    },
  });

  const addParticipantMutation = useMutation({
    mutationFn: () => addParticipant(eventId!, newMemberId),
    onSuccess: (added) => {
      queryClient.invalidateQueries({ queryKey: eventKeys.participants(eventId!) });
      toast.success(`${added.nickname}さんを参加者に追加しました`);
      setNewMemberId("");
    },
    onError: handleApiError,
  });

  const removeParticipantMutation = useMutation({
    mutationFn: (targetUserId: string) => removeParticipant(eventId!, targetUserId),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: eventKeys.participants(eventId!) });
      if (result.belowMinPlayers) {
        toast.warning(
          `参加者を削除しました。参加人数が開催条件の最低人数を下回っています(残り${result.remainingParticipantCount}人)`,
        );
      } else {
        toast.success("参加者を削除しました");
      }
    },
    onError: handleApiError,
    onSettled: () => setRemoveTargetUserId(null),
  });

  const updateMemoMutation = useMutation({
    mutationFn: (memo: string) => updateEventMemo(eventId!, memo),
    onSuccess: (updated) => {
      queryClient.setQueryData(eventKeys.detail(eventId!), updated);
      setIsEditingMemo(false);
      toast.success("メモを更新しました");
    },
    onError: handleApiError,
  });

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4 p-4">
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (!event) {
    return <EmptyState message="イベントが見つかりません" />;
  }

  const myParticipant = participants?.find((p) => p.userId === userId);
  const pendingCancelCount = (cancelRequests ?? []).filter((r) => r.status === "PENDING").length;
  const confirmedParticipantCount = (participants ?? []).filter(
    (p) => p.status === "CONFIRMED",
  ).length;

  return (
    <div className="flex flex-col gap-4 p-4">
      <Card>
        <CardContent className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <p className="text-base font-semibold">
              {format(parseISO(event.startTime), "M月d日 HH:mm")} 〜
              {format(parseISO(event.endTime), "HH:mm")}
            </p>
            <Badge variant="outline">{EVENT_STATUS_LABELS[event.status]}</Badge>
          </div>
          {event.location && <p className="text-sm">会場：{event.location.name}</p>}
          {event.locationNote && (
            <p className="text-muted-foreground text-sm">{event.locationNote}</p>
          )}
        </CardContent>
      </Card>

      {(event.memo || isAdmin) && (
        <Card>
          <CardContent className="flex flex-col gap-2">
            <p className="text-sm font-medium">ひとことメモ</p>
            {isEditingMemo ? (
              <div className="flex flex-col gap-2">
                <Textarea
                  placeholder="例：持ち物、集合時間の補足、注意事項など"
                  value={memoDraft}
                  onChange={(e) => setMemoDraft(e.target.value)}
                  maxLength={300}
                />
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    disabled={updateMemoMutation.isPending}
                    onClick={() => updateMemoMutation.mutate(memoDraft)}
                  >
                    保存する
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setIsEditingMemo(false)}>
                    キャンセル
                  </Button>
                </div>
              </div>
            ) : (
              <>
                {event.memo ? (
                  <p className="text-muted-foreground text-sm whitespace-pre-wrap">
                    {event.memo}
                  </p>
                ) : (
                  isAdmin && (
                    <p className="text-muted-foreground text-sm">まだメモはありません</p>
                  )
                )}
                {isAdmin && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="self-start"
                    onClick={() => {
                      setMemoDraft(event.memo);
                      setIsEditingMemo(true);
                    }}
                  >
                    編集する
                  </Button>
                )}
              </>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="flex flex-col gap-2">
          <p className="text-sm font-medium">参加者</p>
          {(participants ?? []).map((participant) => (
            <div key={participant.userId} className="flex items-center justify-between text-sm">
              {canManageResults ? (
                <Link
                  to={paths.resultSummary(event.communityId, participant.userId)}
                  className="underline"
                >
                  {participant.nickname}
                </Link>
              ) : (
                <span>{participant.nickname}</span>
              )}
              <div className="flex items-center gap-1">
                {participant.status !== "CONFIRMED" && (
                  <Badge variant="outline">{PARTICIPANT_STATUS_LABELS[participant.status]}</Badge>
                )}
                {event.status === "CONFIRMED" && isAdmin && participant.status === "CONFIRMED" && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-6"
                    aria-label={`${participant.nickname}さんを削除`}
                    onClick={() => setRemoveTargetUserId(participant.userId)}
                  >
                    <X className="size-4" />
                  </Button>
                )}
              </div>
            </div>
          ))}

          {event.status === "CONFIRMED" && isAdmin && (
            <div className="flex gap-2 border-t pt-2">
              <Select value={newMemberId} onValueChange={(v) => setNewMemberId(v ?? "")}>
                <SelectTrigger className="flex-1">
                  <SelectValue placeholder="追加するメンバーを選択" />
                </SelectTrigger>
                <SelectContent>
                  {(communityMembers ?? [])
                    .filter(
                      (m) =>
                        m.status === "ACTIVE" &&
                        !(participants ?? []).some(
                          (p) =>
                            p.userId === m.userId &&
                            (p.status === "CONFIRMED" || p.status === "AWAITING_APPROVAL"),
                        ),
                    )
                    .map((m) => (
                      <SelectItem key={m.userId} value={m.userId}>
                        {m.nickname}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
              <Button
                variant="outline"
                disabled={!newMemberId || addParticipantMutation.isPending}
                onClick={() => addParticipantMutation.mutate()}
              >
                追加
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {event.status === "PENDING_APPROVAL" && isAdmin && (
        <Card>
          <CardContent className="flex flex-col gap-3">
            {candidate && candidate.members.length > 0 && (
              <>
                <p className="text-sm font-medium">参加させるメンバーを選択してください</p>
                <div className="flex flex-col gap-2">
                  {candidate.members.map((member) => (
                    <label
                      key={member.userId}
                      className="flex items-center gap-2 text-sm"
                      htmlFor={`candidate-member-${member.userId}`}
                    >
                      <Checkbox
                        id={`candidate-member-${member.userId}`}
                        checked={selectedMemberIds.has(member.userId)}
                        onCheckedChange={(checked) =>
                          setSelectedMemberIds((prev) => {
                            const next = new Set(prev);
                            if (checked) {
                              next.add(member.userId);
                            } else {
                              next.delete(member.userId);
                            }
                            return next;
                          })
                        }
                      />
                      {member.nickname}
                    </label>
                  ))}
                </div>
              </>
            )}
            <Button
              onClick={() => confirmMutation.mutate()}
              disabled={
                confirmMutation.isPending || (!!candidate && selectedMemberIds.size === 0)
              }
            >
              このイベントを仮確定する
            </Button>
          </CardContent>
        </Card>
      )}

      {event.status === "AWAITING_MEMBER_APPROVAL" &&
        myParticipant?.status === "AWAITING_APPROVAL" && (
          <div className="flex flex-col gap-2">
            <Button
              onClick={() => approveParticipationMutation.mutate()}
              disabled={approveParticipationMutation.isPending}
            >
              参加を承認する
            </Button>
            <Button
              variant="outline"
              onClick={() => setShowRejectConfirm(true)}
              disabled={rejectParticipationMutation.isPending}
            >
              参加を辞退する
            </Button>
          </div>
        )}

      {event.status === "AWAITING_MEMBER_APPROVAL" && isAdmin && (
        <p className="text-muted-foreground text-sm">
          参加予定者全員の承認をお待ちください（{confirmedParticipantCount}/
          {(participants ?? []).length}人が承認済み）
        </p>
      )}

      {event.status === "CONFIRMED" && myParticipant?.status === "CONFIRMED" && (
        <>
          <QuickFeedbackPrompt
            relatedFeature="EVENT_CONFIRM"
            storageKey={`event-confirm:${event.eventId}`}
          />
          <Link to={paths.eventCancelRequest(event.eventId)}>
            <Button variant="outline" className="w-full">
              参加をキャンセル申請する
            </Button>
          </Link>
        </>
      )}

      {event.status === "CONFIRMED" && isAdmin && (
        <>
          <Link to={paths.eventCancelRequestList(event.eventId)}>
            <Button variant="outline" className="w-full">
              キャンセル申請一覧
              {pendingCancelCount > 0 && (
                <Badge variant="destructive" className="ml-2">
                  {pendingCancelCount}
                </Badge>
              )}
            </Button>
          </Link>
          <Button onClick={() => setShowCompleteConfirm(true)} disabled={completeMutation.isPending}>
            本日の対局を終了する
          </Button>
          <Button variant="destructive" onClick={() => setShowCancelConfirm(true)}>
            イベントを中止する
          </Button>
        </>
      )}

      {event.status === "COMPLETED" && isAdmin && (
        <Button
          variant="outline"
          onClick={() => setShowReopenConfirm(true)}
          disabled={reopenMutation.isPending}
        >
          開催予定に戻す
        </Button>
      )}

      {canManageResults && (
        <Card>
          <CardContent className="flex flex-col gap-2">
            <p className="text-sm font-medium">対局成績</p>
            {(sessions ?? []).length === 0 && (
              <p className="text-muted-foreground text-sm">まだ対局は登録されていません</p>
            )}
            {(sessions ?? []).map((session) => (
              <div
                key={session.sessionNo}
                className="flex items-center justify-between text-sm"
              >
                <span>
                  対局{Number(session.sessionNo)}（{GAME_TYPE_LABELS[session.gameType]}）
                </span>
                {isAdmin && (
                  <Link
                    to={paths.resultSessionEdit(event.eventId, session.sessionNo)}
                    className="underline"
                  >
                    編集
                  </Link>
                )}
              </div>
            ))}
            <Link to={paths.resultSessionNew(event.eventId)}>
              <Button variant="outline" className="w-full">
                成績を入力する
              </Button>
            </Link>
          </CardContent>
        </Card>
      )}

      <AlertDialog open={showCompleteConfirm} onOpenChange={setShowCompleteConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>本日の対局を終了しますか？</AlertDialogTitle>
          </AlertDialogHeader>
          <p className="text-muted-foreground px-4 text-sm">
            終了すると元に戻せません。ここまでに登録された対局成績が、コミュニティの通算成績に反映されます。
          </p>
          <div className="flex justify-end gap-2 px-4 pb-4">
            <AlertDialogCancel>キャンセル</AlertDialogCancel>
            <AlertDialogAction onClick={() => completeMutation.mutate()}>
              終了する
            </AlertDialogAction>
          </div>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={showReopenConfirm} onOpenChange={setShowReopenConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>このイベントを開催予定に戻しますか？</AlertDialogTitle>
          </AlertDialogHeader>
          <p className="text-muted-foreground px-4 text-sm">
            誤って「本日の対局を終了する」を押してしまった場合の取り消し用です。登録済みの成績はそのまま残ります。
          </p>
          <div className="flex justify-end gap-2 px-4 pb-4">
            <AlertDialogCancel>キャンセル</AlertDialogCancel>
            <AlertDialogAction onClick={() => reopenMutation.mutate()}>
              開催予定に戻す
            </AlertDialogAction>
          </div>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={showCancelConfirm} onOpenChange={setShowCancelConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>このイベントを中止しますか？</AlertDialogTitle>
          </AlertDialogHeader>
          <p className="text-muted-foreground px-4 text-sm">
            中止すると元に戻せません。参加者全員に通知されます。
          </p>
          <div className="flex justify-end gap-2 px-4 pb-4">
            <AlertDialogCancel>キャンセル</AlertDialogCancel>
            <AlertDialogAction onClick={() => cancelMutation.mutate()}>
              中止する
            </AlertDialogAction>
          </div>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={showRejectConfirm} onOpenChange={setShowRejectConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>参加を辞退しますか？</AlertDialogTitle>
          </AlertDialogHeader>
          <div className="flex flex-col gap-2 px-4">
            <p className="text-muted-foreground text-sm">
              辞退すると、管理者の承認を待たず即座に確定します。イベント自体は自動では中止されず、継続するかどうかは管理者の判断に委ねられます。
            </p>
            <Textarea
              placeholder="辞退理由（任意）"
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
            />
          </div>
          <div className="flex justify-end gap-2 px-4 pb-4">
            <AlertDialogCancel>キャンセル</AlertDialogCancel>
            <AlertDialogAction onClick={() => rejectParticipationMutation.mutate()}>
              辞退する
            </AlertDialogAction>
          </div>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
        open={removeTargetUserId !== null}
        onOpenChange={(open) => !open && setRemoveTargetUserId(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>この参加者を削除しますか？</AlertDialogTitle>
          </AlertDialogHeader>
          <p className="text-muted-foreground px-4 text-sm">
            本人の同意なく参加を取り消します。元に戻すには再度追加してください。
          </p>
          <div className="flex justify-end gap-2 px-4 pb-4">
            <AlertDialogCancel>キャンセル</AlertDialogCancel>
            <AlertDialogAction
              onClick={() =>
                removeTargetUserId && removeParticipantMutation.mutate(removeTargetUserId)
              }
            >
              削除する
            </AlertDialogAction>
          </div>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
