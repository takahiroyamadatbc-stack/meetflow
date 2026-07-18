import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { getUserResults, resultKeys } from "@/features/result/api";
import type { ResultSummaryStats } from "@/features/result/types";
import { GAME_TYPE_LABELS, type GameType } from "@/features/user/types";

const GAME_TYPES: GameType[] = ["MAHJONG4", "MAHJONG3"];

function statCards(stats: ResultSummaryStats) {
  return [
    { label: "総対局数", value: `${stats.totalGames}局` },
    { label: "平均順位", value: stats.averageRank.toFixed(2) },
    { label: "1位率", value: `${Math.round(stats.firstPlaceRate * 100)}%` },
    { label: "ラス率", value: `${Math.round(stats.lastPlaceRate * 100)}%` },
    { label: "累計ポイント", value: `${stats.totalPoints}pt` },
    // チップは点数・ウマオカの集計とは別枠で保持する仕様のため、totalPoints
    // には含めず単独の統計カードとして表示する。
    { label: "累計チップ", value: `${stats.totalChips}枚` },
  ];
}

/** S-22 成績一覧・集計画面 */
export function ResultSummaryPage() {
  const { communityId, userId } = useParams<{ communityId: string; userId: string }>();

  const { data: summary, isLoading } = useQuery({
    queryKey: resultKeys.summary(communityId!, userId!),
    queryFn: () => getUserResults(userId!, communityId!),
    enabled: !!communityId && !!userId,
  });

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4 p-4">
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  const playedGameTypes = GAME_TYPES.filter(
    (gt) => (summary?.byGameType[gt]?.totalGames ?? 0) > 0,
  );

  if (!summary || playedGameTypes.length === 0) {
    return <EmptyState message="対局記録がありません" />;
  }

  return (
    <div className="flex flex-col gap-6 p-4">
      {playedGameTypes.map((gt) => (
        <div key={gt}>
          <h2 className="mb-2 text-base font-semibold">{GAME_TYPE_LABELS[gt]}</h2>
          <div className="grid grid-cols-2 gap-3">
            {statCards(summary.byGameType[gt]).map((stat) => (
              <Card key={stat.label}>
                <CardContent className="flex flex-col gap-1">
                  <p className="text-muted-foreground text-xs">{stat.label}</p>
                  <p className="text-lg font-semibold">{stat.value}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
