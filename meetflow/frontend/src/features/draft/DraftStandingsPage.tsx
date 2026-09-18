import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { useAuthUser } from "@/features/auth/useAuthUser";
import { draftKeys, getStandings, refreshStandings } from "@/features/draft/api";
import { ManualResultDialog } from "@/features/draft/components/ManualResultDialog";
import { useDraftDetail } from "@/features/draft/useDraft";

/**
 * S-36 成績画面（docs/draft/DESIGN.md §4.8〜§4.10、§4.15）。
 *
 * 取得は完全オンデマンド。この画面を開いただけでは公式サイトを叩かず、
 * 「最新の成績を取得」を押したときだけ取りに行く（1日1回まで）。
 */
export function DraftStandingsPage() {
  const { draftId } = useParams<{ draftId: string }>();
  const { userId } = useAuthUser();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();
  const [manualOpen, setManualOpen] = useState(false);

  const { data: draft } = useDraftDetail(draftId);
  const { data: standings, isLoading } = useQuery({
    queryKey: draftKeys.standings(draftId!),
    queryFn: () => getStandings(draftId!),
    enabled: !!draftId,
  });

  const refreshMutation = useMutation({
    mutationFn: () => refreshStandings(draftId!),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: draftKeys.standings(draftId!) });
      toast.success(
        result.refreshed
          ? `最新の成績を取得しました（${result.latestPlayedDate ?? "-"}まで）`
          : "今日はすでに取得済みです",
      );
    },
    onError: handleApiError,
  });

  if (isLoading) {
    return (
      <div className="flex flex-col gap-3 p-4">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  if (!standings) {
    return <EmptyState message="成績が取得できません" />;
  }

  const isHost = draft?.hostUserId === userId;

  return (
    <div className="flex flex-col gap-4 p-4">
      <Card>
        <CardContent className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">{standings.season}シーズン</span>
            {/* §4.9: 19時は最新確定日の計算を変えない。バッジの表示判定にだけ使う。 */}
            {standings.inGameWindow && <Badge variant="destructive">対局中</Badge>}
          </div>
          {/* §7: 取得に失敗していても古いデータを出し続ける。そのかわり
              「いつ時点のデータか」は必ず出す。 */}
          <p className="text-muted-foreground text-xs">
            最終更新: {formatDateTime(standings.lastUpdatedAt) ?? "未取得"}
            {standings.latestPlayedDate && <>（{standings.latestPlayedDate}の対局まで）</>}
          </p>
          <p className="text-muted-foreground text-xs">
            集計範囲:{" "}
            {standings.regularSeasonEndDate
              ? `${standings.regularSeasonEndDate}まで（レギュラーシーズン）`
              : "シーズン全体（レギュラーシーズン終了日が未設定）"}
          </p>
          <Button
            onClick={() => refreshMutation.mutate()}
            disabled={refreshMutation.isPending || !standings.canRefresh}
          >
            {standings.canRefresh ? "最新の成績を取得" : "今日は取得済みです"}
          </Button>
          {isHost && (
            <Button variant="outline" size="sm" onClick={() => setManualOpen(true)}>
              結果を手動で入力する
            </Button>
          )}
        </CardContent>
      </Card>

      {standings.lastError && (
        <Card>
          <CardContent className="flex flex-col gap-1">
            <p className="text-destructive text-sm font-medium">
              公式サイトからの取得に失敗しています
            </p>
            <p className="text-muted-foreground text-xs">{standings.lastError}</p>
            <p className="text-muted-foreground text-xs">
              表示しているのは最終更新時点の成績です。
              {isHost && "直らない場合は手動入力で続けられます。"}
            </p>
          </CardContent>
        </Card>
      )}

      {standings.mismatchedPlayers.length > 0 && (
        <Card>
          <CardContent className="flex flex-col gap-1">
            <p className="text-sm font-medium">公式の累計と一致しない選手がいます</p>
            <p className="text-muted-foreground text-xs">
              {standings.mismatchedPlayers.join("、")}
            </p>
            <p className="text-muted-foreground text-xs">
              ポストシーズンが始まると公式のレギュラー累計とはズレるため、
              その時期であれば想定どおりです。
            </p>
          </CardContent>
        </Card>
      )}

      {standings.standings.map((row) => (
        <Card key={row.userId}>
          <CardContent className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-2 text-sm font-medium">
                <Badge variant={row.rank === 1 ? "default" : "outline"}>{row.rank}位</Badge>
                {row.displayName}
              </span>
              <span className="text-base font-semibold">{formatPoints(row.totalPoints)}</span>
            </div>
            <ul className="flex flex-col gap-1">
              {row.players.map((player) => (
                <li key={player.playerId} className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2">
                    {player.playerName}
                    {player.isFemale && (
                      <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">
                        女流
                      </Badge>
                    )}
                    <span className="text-muted-foreground text-xs">{player.teamName}</span>
                  </span>
                  <span className="text-muted-foreground text-xs">
                    {formatPoints(player.points)} / {player.games}半荘
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ))}

      <p className="text-muted-foreground text-xs">
        消化 {standings.playedGamedayCount}節 ／ 残り {standings.scheduledGamedayCount}節
      </p>

      {isHost && draftId && (
        <ManualResultDialog
          draftId={draftId}
          open={manualOpen}
          onClose={() => setManualOpen(false)}
        />
      )}
    </div>
  );
}

/** ポイントは小数第1位まで。プラスは符号付きで見せる。 */
function formatPoints(points: number): string {
  return `${points > 0 ? "+" : ""}${points.toFixed(1)}pt`;
}

function formatDateTime(iso: string | null): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("ja-JP", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
