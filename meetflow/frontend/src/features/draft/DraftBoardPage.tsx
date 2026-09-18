import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/feedback/EmptyState";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { useAuthUser } from "@/features/auth/useAuthUser";
import {
  advanceDraft,
  draftKeys,
  listLotteries,
  revealWave,
  runLottery,
  startDraft,
  submitProxyPick,
} from "@/features/draft/api";
import { LotteryLog } from "@/features/draft/components/LotteryLog";
import { PlayerPicker } from "@/features/draft/components/PlayerPicker";
import { RosterBoard } from "@/features/draft/components/RosterBoard";
import { WaveProgress } from "@/features/draft/components/WaveProgress";
import { displayNameMap, findParticipant, pickBlockReason } from "@/features/draft/rules";
import { useDraftDetail, useDraftPlayers } from "@/features/draft/useDraft";
import { DRAFT_STATUS_LABELS, type DraftPlayer } from "@/features/draft/types";

/**
 * S-35 ドラフト主催者画面（プロジェクター／全体進行用）。
 *
 * DESIGN.md §4.6: 状態遷移は自動では起きない。主催者が
 * 「開示」→（必要なら）「抽選」→「次へ」とボタンを押して進める。
 * 主催者以外が開いた場合は操作ボタンを出さず、全体の進行状況だけを見せる。
 */
export function DraftBoardPage() {
  const { draftId } = useParams<{ draftId: string }>();
  const { userId } = useAuthUser();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();
  const [proxyTargetUserId, setProxyTargetUserId] = useState<string | null>(null);

  const { data: draft, isLoading } = useDraftDetail(draftId);
  const { data: players } = useDraftPlayers(draftId, draft?.version);
  const { data: lotteries } = useQuery({
    queryKey: [...draftKeys.lotteries(draftId!), draft?.version] as const,
    queryFn: () => listLotteries(draftId!),
    enabled: !!draftId && draft?.version !== undefined,
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: draftKeys.detail(draftId!) });

  const startMutation = useMutation({
    mutationFn: () => startDraft(draftId!),
    onSuccess: () => {
      invalidate();
      toast.success("ドラフトを開始しました");
    },
    onError: handleApiError,
  });

  const revealMutation = useMutation({
    mutationFn: () => revealWave(draftId!),
    onSuccess: (result) => {
      invalidate();
      toast.success(
        result.lotteryRequired ? "指名が重複しました。抽選してください" : "指名を開示しました",
      );
    },
    onError: handleApiError,
  });

  const lotteryMutation = useMutation({
    mutationFn: () => runLottery(draftId!),
    onSuccess: () => {
      invalidate();
      toast.success("抽選を行いました");
    },
    onError: handleApiError,
  });

  const advanceMutation = useMutation({
    mutationFn: () => advanceDraft(draftId!),
    onSuccess: (result) => {
      invalidate();
      toast.success(
        result.status === "COMPLETED" ? "ドラフトが完了しました" : `${result.round}巡目に進みました`,
      );
    },
    onError: handleApiError,
  });

  const proxyMutation = useMutation({
    mutationFn: ({ targetUserId, playerId }: { targetUserId: string; playerId: string }) =>
      submitProxyPick(draftId!, targetUserId, playerId),
    onSuccess: (pick) => {
      invalidate();
      setProxyTargetUserId(null);
      toast.success(`代理で${pick.playerName}を指名しました`);
    },
    onError: handleApiError,
  });

  if (isLoading) {
    return (
      <div className="flex flex-col gap-3 p-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  if (!draft) {
    return <EmptyState message="ドラフトが見つかりません" />;
  }

  const nameMap = displayNameMap(draft);
  const nameOf = (id: string) => nameMap[id] ?? id;
  const isHost = draft.hostUserId === userId;
  const wave = draft.currentWave;
  const allSubmitted = wave ? wave.pendingUserIds.length === 0 : false;
  const busy =
    startMutation.isPending ||
    revealMutation.isPending ||
    lotteryMutation.isPending ||
    advanceMutation.isPending;

  return (
    <div className="flex flex-col gap-4 p-4">
      <Card>
        <CardContent className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-base font-semibold">{draft.name}</span>
            <Badge variant={draft.status === "COMPLETED" ? "secondary" : "default"}>
              {DRAFT_STATUS_LABELS[draft.status]}
            </Badge>
          </div>
          <p className="text-muted-foreground text-xs">
            {draft.participantCount}人 ／ 女流枠の残り {draft.femaleSurplusRemaining}
          </p>
        </CardContent>
      </Card>

      {wave && <WaveProgress wave={wave} rounds={draft.rounds} nameOf={nameOf} />}

      {isHost && (
        <div className="flex flex-col gap-2">
          {draft.status === "SETUP" && (
            <Button onClick={() => startMutation.mutate()} disabled={busy}>
              ドラフトを開始する
            </Button>
          )}
          {draft.status === "NOMINATING" && (
            <>
              <Button onClick={() => revealMutation.mutate()} disabled={busy || !allSubmitted}>
                指名を開示する
              </Button>
              {!allSubmitted && wave && (
                // DESIGN.md §4.7: 制限時間は設けず、連絡がつかない人だけ代理指名する。
                <div className="flex flex-col gap-2">
                  <p className="text-muted-foreground text-xs">
                    連絡がつかない場合は代理で指名できます
                  </p>
                  {wave.pendingUserIds.map((pendingUserId) => (
                    <Button
                      key={pendingUserId}
                      variant="outline"
                      size="sm"
                      onClick={() => setProxyTargetUserId(pendingUserId)}
                    >
                      {nameOf(pendingUserId)}の代理で指名する
                    </Button>
                  ))}
                </div>
              )}
            </>
          )}
          {draft.status === "REVEAL" && wave?.lotteryRequired && (
            <Button onClick={() => lotteryMutation.mutate()} disabled={busy}>
              抽選を実行する
            </Button>
          )}
          {((draft.status === "REVEAL" && !wave?.lotteryRequired) ||
            draft.status === "LOTTERY") && (
            <Button onClick={() => advanceMutation.mutate()} disabled={busy}>
              次へ進む
            </Button>
          )}
        </div>
      )}

      {!isHost && draft.status !== "COMPLETED" && (
        <p className="text-muted-foreground text-sm">
          進行は主催者（{nameOf(draft.hostUserId)}）が操作します
        </p>
      )}

      <div className="flex flex-col gap-2">
        <p className="text-sm font-medium">チーム編成</p>
        <RosterBoard
          participants={draft.participants}
          rosters={draft.rosters}
          rounds={draft.rounds}
        />
      </div>

      <div className="flex flex-col gap-2">
        <p className="text-sm font-medium">抽選の記録</p>
        <LotteryLog lotteries={lotteries ?? []} nameOf={nameOf} />
      </div>

      <ProxyPickDialog
        targetUserId={proxyTargetUserId}
        onClose={() => setProxyTargetUserId(null)}
        nameOf={nameOf}
        players={players ?? []}
        blockReasonOf={(player) =>
          pickBlockReason(player, {
            round: draft.round,
            rounds: draft.rounds,
            hasFemale: (findParticipant(draft, proxyTargetUserId)?.femaleCount ?? 0) > 0,
            femaleSurplusRemaining: draft.femaleSurplusRemaining,
          })
        }
        onSubmit={(playerId) =>
          proxyTargetUserId &&
          proxyMutation.mutate({ targetUserId: proxyTargetUserId, playerId })
        }
        pending={proxyMutation.isPending}
      />
    </div>
  );
}

function ProxyPickDialog({
  targetUserId,
  onClose,
  nameOf,
  players,
  blockReasonOf,
  onSubmit,
  pending,
}: {
  targetUserId: string | null;
  onClose: () => void;
  nameOf: (userId: string) => string;
  players: DraftPlayer[];
  blockReasonOf: (player: DraftPlayer) => ReturnType<typeof pickBlockReason>;
  onSubmit: (playerId: string) => void;
  pending: boolean;
}) {
  const [selectedPlayerId, setSelectedPlayerId] = useState<string | null>(null);

  return (
    <Dialog
      open={targetUserId !== null}
      onOpenChange={(open) => {
        if (!open) {
          setSelectedPlayerId(null);
          onClose();
        }
      }}
    >
      <DialogContent className="max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {targetUserId ? `${nameOf(targetUserId)}の代理で指名` : "代理指名"}
          </DialogTitle>
        </DialogHeader>
        <PlayerPicker
          players={players}
          blockReasonOf={blockReasonOf}
          selectedPlayerId={selectedPlayerId}
          onSelect={setSelectedPlayerId}
          nameOf={nameOf}
          disabled={pending}
        />
        <Button
          disabled={!selectedPlayerId || pending}
          onClick={() => selectedPlayerId && onSubmit(selectedPlayerId)}
        >
          この選手で代理指名する
        </Button>
      </DialogContent>
    </Dialog>
  );
}
