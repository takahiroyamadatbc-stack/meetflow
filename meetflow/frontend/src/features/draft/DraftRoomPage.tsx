import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { useAuthUser } from "@/features/auth/useAuthUser";
import { draftKeys, submitPick } from "@/features/draft/api";
import { PlayerPicker } from "@/features/draft/components/PlayerPicker";
import { RosterBoard } from "@/features/draft/components/RosterBoard";
import { WaveProgress } from "@/features/draft/components/WaveProgress";
import {
  displayNameMap,
  findParticipant,
  hasSubmitted,
  needsToPick,
  pickBlockReason,
} from "@/features/draft/rules";
import { useDraftDetail, useDraftPlayers } from "@/features/draft/useDraft";
import { DRAFT_STATUS_LABELS, type DraftPlayer } from "@/features/draft/types";
import { paths } from "@/routes/paths";

/**
 * S-34 ドラフト参加者画面（スマホ用）。
 *
 * DESIGN.md §4.6の通り、進行操作（開示・抽選・次へ）はここには置かず
 * 主催者画面（S-35）に分けている。この画面でできるのは自分の指名だけ。
 */
export function DraftRoomPage() {
  const { draftId } = useParams<{ draftId: string }>();
  const { userId } = useAuthUser();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();
  const [selectedPlayerId, setSelectedPlayerId] = useState<string | null>(null);

  const { data: draft, isLoading } = useDraftDetail(draftId);
  const { data: players } = useDraftPlayers(draftId, draft?.version);

  const pickMutation = useMutation({
    mutationFn: (playerId: string) => submitPick(draftId!, playerId),
    onSuccess: (pick) => {
      queryClient.invalidateQueries({ queryKey: draftKeys.detail(draftId!) });
      setSelectedPlayerId(null);
      toast.success(`${pick.playerName}を指名しました`);
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
  const me = findParticipant(draft, userId);
  const isHost = draft.hostUserId === userId;
  const myTurn = needsToPick(draft, userId) && !hasSubmitted(draft, userId);

  const blockReasonOf = (player: DraftPlayer) =>
    pickBlockReason(player, {
      round: draft.round,
      rounds: draft.rounds,
      hasFemale: (me?.femaleCount ?? 0) > 0,
      femaleSurplusRemaining: draft.femaleSurplusRemaining,
    });

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
            {draft.season}シーズン ／ 女流枠の残り {draft.femaleSurplusRemaining}
          </p>
          <div className="mt-1 flex gap-2">
            <Link to={paths.draftStandings(draft.draftId)}>
              <Button variant="outline" size="sm">
                成績を見る
              </Button>
            </Link>
            {isHost && (
              <Link to={paths.draftBoard(draft.draftId)}>
                <Button variant="outline" size="sm">
                  進行画面を開く
                </Button>
              </Link>
            )}
          </div>
        </CardContent>
      </Card>

      {!me && (
        <Card>
          <CardContent>
            <p className="text-muted-foreground text-sm">
              あなたはこのドラフトの参加者ではありません（観戦中）
            </p>
          </CardContent>
        </Card>
      )}

      {draft.currentWave && (
        <WaveProgress wave={draft.currentWave} rounds={draft.rounds} nameOf={nameOf} />
      )}

      {myTurn && players && (
        <div className="flex flex-col gap-3">
          <p className="text-sm font-medium">指名する選手を選んでください</p>
          <PlayerPicker
            players={players}
            blockReasonOf={blockReasonOf}
            selectedPlayerId={selectedPlayerId}
            onSelect={setSelectedPlayerId}
            nameOf={nameOf}
            disabled={pickMutation.isPending}
          />
          <Button
            className="sticky bottom-4"
            disabled={!selectedPlayerId || pickMutation.isPending}
            onClick={() => selectedPlayerId && pickMutation.mutate(selectedPlayerId)}
          >
            この選手を指名する
          </Button>
        </div>
      )}

      {me && !myTurn && draft.status === "NOMINATING" && (
        <Card>
          <CardContent>
            <p className="text-sm">
              {hasSubmitted(draft, userId)
                ? "指名を提出しました。全員の提出を待っています。"
                : "この巡はあなたの指名は不要です。"}
            </p>
          </CardContent>
        </Card>
      )}

      <div className="flex flex-col gap-2">
        <p className="text-sm font-medium">チーム編成</p>
        <RosterBoard
          participants={draft.participants}
          rosters={draft.rosters}
          rounds={draft.rounds}
          highlightUserId={userId}
        />
      </div>
    </div>
  );
}
