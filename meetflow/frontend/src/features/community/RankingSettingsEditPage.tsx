import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
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
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { communityKeys, getCommunity, updateRankingSettings } from "@/features/community/api";
import type { RankingMetric, RankingPeriodType } from "@/features/community/types";
import { RANKING_METRIC_LABELS } from "@/features/result/types";
import { GAME_TYPE_LABELS, type GameType } from "@/features/user/types";
import { paths } from "@/routes/paths";

const PERIOD_TYPE_LABELS: Record<RankingPeriodType, string> = {
  MONTH: "今月",
  QUARTER: "四半期",
  HALF_YEAR: "半期",
  YEAR: "年",
  ALL_TIME: "通算",
};

/** S-05e コミュニティ内ランキング設定変更（S-05から遷移、Issue #40） */
export function RankingSettingsEditPage() {
  const { communityId } = useParams<{ communityId: string }>();
  const navigate = useNavigate();
  const handleApiError = useApiErrorToast();

  const { data: community, isLoading } = useQuery({
    queryKey: communityKeys.detail(communityId!),
    queryFn: () => getCommunity(communityId!),
    enabled: !!communityId,
  });

  const [initialized, setInitialized] = useState(false);
  const [gameType, setGameType] = useState<GameType>("MAHJONG4");
  const [periodType, setPeriodType] = useState<RankingPeriodType>("MONTH");
  const [metric, setMetric] = useState<RankingMetric>("AVERAGE_RANK");
  const [minGames, setMinGames] = useState(0);

  if (community && !initialized) {
    setGameType(community.rankingDefaultGameType);
    setPeriodType(community.rankingDefaultPeriodType);
    setMetric(community.rankingDefaultMetric);
    setMinGames(community.rankingDefaultMinGames);
    setInitialized(true);
  }

  const mutation = useMutation({
    mutationFn: () =>
      updateRankingSettings(communityId!, { gameType, periodType, metric, minGames }),
    onSuccess: () => {
      toast.success("ランキング設定を変更しました");
      navigate(paths.communityDetail(communityId!));
    },
    onError: handleApiError,
  });

  if (isLoading || !initialized) {
    return (
      <div className="flex flex-col gap-4 p-4">
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <p className="text-muted-foreground text-sm">
        コミュニティ内ランキング画面を開いたときのデフォルトの表示条件を設定します。閲覧者はその場で切り替えられますが、選択状態は保存されず毎回この設定から始まります。
      </p>

      <div className="flex flex-col gap-2">
        <span className="text-sm font-medium">デフォルトの種目</span>
        <Select value={gameType} onValueChange={(v) => setGameType(v as GameType)}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="MAHJONG4">{GAME_TYPE_LABELS.MAHJONG4}</SelectItem>
            <SelectItem value="MAHJONG3">{GAME_TYPE_LABELS.MAHJONG3}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="flex flex-col gap-2">
        <span className="text-sm font-medium">デフォルトの集計期間</span>
        <Select
          value={periodType}
          onValueChange={(v) => setPeriodType(v as RankingPeriodType)}
        >
          <SelectTrigger>
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
      </div>

      <div className="flex flex-col gap-2">
        <span className="text-sm font-medium">デフォルトの指標</span>
        <Select value={metric} onValueChange={(v) => setMetric(v as RankingMetric)}>
          <SelectTrigger>
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
      </div>

      <div className="flex flex-col gap-2">
        <span className="text-sm font-medium">
          デフォルトの最低対局数（率・平均系の指標にのみ適用、0＝足切りなし）
        </span>
        <Input
          type="number"
          min={0}
          value={minGames}
          onChange={(e) => setMinGames(Math.max(0, Number(e.target.value) || 0))}
        />
      </div>

      <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
        保存する
      </Button>
    </div>
  );
}
