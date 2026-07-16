import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { getUserResults, resultKeys } from "@/features/result/api";

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

  if (!summary || summary.totalGames === 0) {
    return <EmptyState message="対局記録がありません" />;
  }

  const stats = [
    { label: "総対局数", value: `${summary.totalGames}局` },
    { label: "平均順位", value: summary.averageRank.toFixed(2) },
    { label: "1位率", value: `${Math.round(summary.firstPlaceRate * 100)}%` },
    { label: "ラス率", value: `${Math.round(summary.lastPlaceRate * 100)}%` },
    { label: "累計ポイント", value: `${summary.totalPoints}pt` },
    // チップは点数・ウマオカの集計とは別枠で保持する仕様のため、totalPoints
    // には含めず単独の統計カードとして表示する。
    { label: "累計チップ", value: `${summary.totalChips}枚` },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 p-4">
      {stats.map((stat) => (
        <Card key={stat.label}>
          <CardContent className="flex flex-col gap-1">
            <p className="text-muted-foreground text-xs">{stat.label}</p>
            <p className="text-lg font-semibold">{stat.value}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
