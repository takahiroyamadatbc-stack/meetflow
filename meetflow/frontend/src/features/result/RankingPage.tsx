import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EmptyState } from "@/components/feedback/EmptyState";
import { communityKeys, getCommunity } from "@/features/community/api";
import type { RankingMetric, RankingPeriodType } from "@/features/community/types";
import { getCommunityRanking, resultKeys } from "@/features/result/api";
import {
  RANKING_ASCENDING_METRICS,
  RANKING_METRIC_LABELS,
  RANKING_MIN_GAMES_APPLICABLE_METRICS,
  getRankingMetricValue,
  type RankingMemberStats,
  type RankingPeriodParams,
} from "@/features/result/types";
import { GAME_TYPE_LABELS, type GameType } from "@/features/user/types";
import { paths } from "@/routes/paths";

const PERIOD_TYPE_LABELS: Record<RankingPeriodType, string> = {
  MONTH: "月",
  QUARTER: "四半期",
  HALF_YEAR: "半期",
  YEAR: "年",
  ALL_TIME: "通算",
};

const now = new Date();
const CURRENT_YEAR = now.getFullYear();
const CURRENT_MONTH = now.getMonth() + 1;
const CURRENT_QUARTER = Math.ceil(CURRENT_MONTH / 3);
const CURRENT_HALF = CURRENT_MONTH <= 6 ? 1 : 2;

function formatMetricValue(metric: RankingMetric, value: number): string {
  switch (metric) {
    case "AVERAGE_RANK":
    case "AVERAGE_CHIPS":
      return value.toFixed(2);
    case "FIRST_PLACE_RATE":
    case "SECOND_PLACE_RATE":
    case "TOP_TWO_RATE":
    case "NON_LAST_RATE":
      return `${Math.round(value * 100)}%`;
    case "TOTAL_POINTS":
      return `${value}pt`;
    case "TOTAL_GAMES":
      return `${value}局`;
    case "PARTICIPATED_EVENTS":
      return `${value}件`;
    case "TOTAL_CHIPS":
      return `${value}枚`;
    default:
      return String(value);
  }
}

/** S-31 コミュニティ内ランキング画面（Issue #40） */
export function RankingPage() {
  const { communityId } = useParams<{ communityId: string }>();

  const { data: community } = useQuery({
    queryKey: communityKeys.detail(communityId!),
    queryFn: () => getCommunity(communityId!),
    enabled: !!communityId,
  });
  const isAdmin = community?.role === "OWNER" || community?.role === "ADMIN";

  // 種目・期間・指標・足切りは、閲覧のたびにコミュニティ管理者のデフォルト
  // 設定から開始する（選択状態は保存しない、Issue #40決定事項7）。community
  // 取得後の最初の1回だけデフォルト値を注入する。
  const [initialized, setInitialized] = useState(false);
  const [gameType, setGameType] = useState<GameType>("MAHJONG4");
  const [periodType, setPeriodType] = useState<RankingPeriodType>("MONTH");
  const [year, setYear] = useState(CURRENT_YEAR);
  const [month, setMonth] = useState(CURRENT_MONTH);
  const [quarter, setQuarter] = useState(CURRENT_QUARTER);
  const [half, setHalf] = useState(CURRENT_HALF);
  const [metric, setMetric] = useState<RankingMetric>("AVERAGE_RANK");
  const [minGames, setMinGames] = useState(0);

  if (community && !initialized) {
    setGameType(community.rankingDefaultGameType);
    setPeriodType(community.rankingDefaultPeriodType);
    setMetric(community.rankingDefaultMetric);
    setMinGames(community.rankingDefaultMinGames);
    setInitialized(true);
  }

  const periodParams: RankingPeriodParams = useMemo(() => {
    switch (periodType) {
      case "MONTH":
        return { periodType: "MONTH", year, month };
      case "QUARTER":
        return { periodType: "QUARTER", year, quarter };
      case "HALF_YEAR":
        return { periodType: "HALF_YEAR", year, half };
      case "YEAR":
        return { periodType: "YEAR", year };
      default:
        return { periodType: "ALL_TIME" };
    }
  }, [periodType, year, month, quarter, half]);

  const { data: ranking, isLoading } = useQuery({
    queryKey: resultKeys.ranking(communityId!, gameType, periodParams),
    queryFn: () => getCommunityRanking(communityId!, gameType, periodParams),
    enabled: !!communityId && initialized,
  });

  const minGamesApplicable = RANKING_MIN_GAMES_APPLICABLE_METRICS.has(metric);

  const sortedMembers: RankingMemberStats[] = useMemo(() => {
    if (!ranking) return [];
    const eligible = minGamesApplicable
      ? ranking.members.filter((m) => m.totalGames >= minGames)
      : ranking.members;
    const ascending = RANKING_ASCENDING_METRICS.has(metric);
    return [...eligible].sort((a, b) => {
      const diff = getRankingMetricValue(a, metric) - getRankingMetricValue(b, metric);
      return ascending ? diff : -diff;
    });
  }, [ranking, metric, minGames, minGamesApplicable]);

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex gap-2">
        <Button
          type="button"
          variant={gameType === "MAHJONG4" ? "default" : "outline"}
          size="sm"
          onClick={() => setGameType("MAHJONG4")}
        >
          {GAME_TYPE_LABELS.MAHJONG4}
        </Button>
        <Button
          type="button"
          variant={gameType === "MAHJONG3" ? "default" : "outline"}
          size="sm"
          onClick={() => setGameType("MAHJONG3")}
        >
          {GAME_TYPE_LABELS.MAHJONG3}
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Select
          value={periodType}
          onValueChange={(v) => setPeriodType(v as RankingPeriodType)}
        >
          <SelectTrigger className="w-28">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(Object.keys(PERIOD_TYPE_LABELS) as RankingPeriodType[]).map((pt) => (
              <SelectItem key={pt} value={pt}>
                {PERIOD_TYPE_LABELS[pt]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {periodType !== "ALL_TIME" && (
          <Input
            type="number"
            className="w-24"
            value={year}
            onChange={(e) => setYear(Number(e.target.value) || CURRENT_YEAR)}
          />
        )}
        {periodType === "MONTH" && (
          <Select value={String(month)} onValueChange={(v) => setMonth(Number(v))}>
            <SelectTrigger className="w-20">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                <SelectItem key={m} value={String(m)}>
                  {m}月
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        {periodType === "QUARTER" && (
          <Select value={String(quarter)} onValueChange={(v) => setQuarter(Number(v))}>
            <SelectTrigger className="w-24">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {[1, 2, 3, 4].map((q) => (
                <SelectItem key={q} value={String(q)}>
                  第{q}四半期
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        {periodType === "HALF_YEAR" && (
          <Select value={String(half)} onValueChange={(v) => setHalf(Number(v))}>
            <SelectTrigger className="w-24">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="1">上半期</SelectItem>
              <SelectItem value="2">下半期</SelectItem>
            </SelectContent>
          </Select>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Select value={metric} onValueChange={(v) => setMetric(v as RankingMetric)}>
          <SelectTrigger className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(Object.keys(RANKING_METRIC_LABELS) as RankingMetric[]).map((m) => (
              <SelectItem key={m} value={m}>
                {RANKING_METRIC_LABELS[m]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {minGamesApplicable && (
          <div className="flex items-center gap-1">
            <span className="text-muted-foreground text-xs">最低対局数</span>
            <Input
              type="number"
              min={0}
              className="w-16"
              value={minGames}
              onChange={(e) => setMinGames(Math.max(0, Number(e.target.value) || 0))}
            />
          </div>
        )}
      </div>

      {isAdmin && (
        <Link to={paths.communityRankingSettingsEdit(communityId!)}>
          <Button type="button" variant="outline" size="sm">
            ランキング設定を変更
          </Button>
        </Link>
      )}

      {isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : sortedMembers.length === 0 ? (
        <EmptyState message="この期間の対局記録がありません" />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>順位</TableHead>
              <TableHead>メンバー</TableHead>
              <TableHead>{RANKING_METRIC_LABELS[metric]}</TableHead>
              <TableHead>対局数</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sortedMembers.map((m, index) => (
              <TableRow key={m.userId}>
                <TableCell>{index + 1}</TableCell>
                <TableCell>{m.displayName}</TableCell>
                <TableCell>
                  {formatMetricValue(metric, getRankingMetricValue(m, metric))}
                </TableCell>
                <TableCell>{m.totalGames}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
