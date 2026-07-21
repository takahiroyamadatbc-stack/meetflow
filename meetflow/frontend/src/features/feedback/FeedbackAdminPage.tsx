import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import { toast } from "sonner";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { EmptyState } from "@/components/feedback/EmptyState";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { useIsOperator } from "@/features/auth/useIsOperator";
import {
  feedbackKeys,
  getFeedback,
  getFeedbackStats,
  listFeedback,
  updateFeedback,
  type FeedbackListFilters,
} from "@/features/feedback/api";
import {
  FEEDBACK_CATEGORY_LABELS,
  FEEDBACK_PRIORITY_LABELS,
  FEEDBACK_RATING_LABELS,
  FEEDBACK_STATUS_LABELS,
  RELATED_FEATURE_OPTIONS,
  type FeedbackItem,
  type FeedbackPriority,
  type FeedbackRating,
  type FeedbackStats,
  type FeedbackStatus,
  type QuickStatsPeriod,
} from "@/features/feedback/types";

const RELATED_FEATURE_LABELS: Record<string, string> = Object.fromEntries(
  RELATED_FEATURE_OPTIONS.map((o) => [o.value, o.label]),
);

const QUICK_STATS_PERIOD_LABELS: Record<QuickStatsPeriod, string> = {
  WEEK: "週次",
  MONTH: "月次",
};

// GOOD/NEUTRAL/BADはカテゴリ色ではなく状態(良い/ふつう/悪い)を表す
// ステータス色として扱う(dataviz skill references/palette.md参照)。
const RATING_CHART_CONFIG: ChartConfig = {
  GOOD: { label: FEEDBACK_RATING_LABELS.GOOD, color: "var(--color-status-good)" },
  NEUTRAL: { label: FEEDBACK_RATING_LABELS.NEUTRAL, color: "var(--color-status-warning)" },
  BAD: { label: FEEDBACK_RATING_LABELS.BAD, color: "var(--color-status-critical)" },
};

/** S-29 フィードバック管理画面（運営者限定） */
export function FeedbackAdminPage() {
  const isOperator = useIsOperator();
  const [filters, setFilters] = useState<FeedbackListFilters>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [quickStatsPeriod, setQuickStatsPeriod] = useState<QuickStatsPeriod>("WEEK");

  const { data: stats } = useQuery({
    queryKey: feedbackKeys.stats(quickStatsPeriod),
    queryFn: () => getFeedbackStats(quickStatsPeriod),
    enabled: isOperator,
  });

  const { data: feedbacks, isLoading } = useQuery({
    queryKey: feedbackKeys.list(filters),
    queryFn: () => listFeedback(filters),
    enabled: isOperator,
  });
  // Issue #85: QUICK評価(絵文字1クリック評価)は詳細を持たず一覧のノイズに
  // なるため一覧からは外し、下のグラフでのみ集計表示する。
  const detailedFeedbacks = (feedbacks ?? []).filter((item) => item.kind !== "QUICK");

  if (!isOperator) {
    return <EmptyState message="この画面は運営者のみ利用できます" />;
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      {stats && (
        <Card>
          <CardContent className="flex flex-col gap-2">
            <p className="text-sm font-medium">集計</p>
            <div className="flex flex-wrap gap-1">
              {Object.entries(stats.byStatus).map(([status, count]) => (
                <Badge key={status} variant="outline">
                  {FEEDBACK_STATUS_LABELS[status as FeedbackStatus] ?? status} {count}
                </Badge>
              ))}
            </div>
            <div className="flex flex-wrap gap-1">
              {Object.entries(stats.byCategory).map(([category, count]) => (
                <Badge key={category} variant="secondary">
                  {FEEDBACK_CATEGORY_LABELS[category as keyof typeof FEEDBACK_CATEGORY_LABELS] ??
                    category}{" "}
                  {count}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {stats && (
        <QuickFeedbackStatsChart
          quickStats={stats.quickStats}
          period={quickStatsPeriod}
          onPeriodChange={setQuickStatsPeriod}
        />
      )}

      <div className="flex gap-2">
        <Select
          value={filters.status ?? "ALL"}
          onValueChange={(v) =>
            setFilters((f) => ({ ...f, status: !v || v === "ALL" ? undefined : v }))
          }
        >
          <SelectTrigger className="flex-1">
            <SelectValue placeholder="ステータス" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">すべてのステータス</SelectItem>
            {Object.entries(FEEDBACK_STATUS_LABELS).map(([value, label]) => (
              <SelectItem key={value} value={value}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={filters.category ?? "ALL"}
          onValueChange={(v) =>
            setFilters((f) => ({ ...f, category: !v || v === "ALL" ? undefined : v }))
          }
        >
          <SelectTrigger className="flex-1">
            <SelectValue placeholder="種別" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">すべての種別</SelectItem>
            {Object.entries(FEEDBACK_CATEGORY_LABELS).map(([value, label]) => (
              <SelectItem key={value} value={value}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {isLoading && (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      )}

      {!isLoading && detailedFeedbacks.length === 0 && (
        <EmptyState message="フィードバックはありません" />
      )}

      <div className="flex flex-col gap-2">
        {detailedFeedbacks.map((item) => (
          <FeedbackListCard
            key={item.feedbackId}
            item={item}
            expanded={selectedId === item.feedbackId}
            onToggle={() =>
              setSelectedId((prev) => (prev === item.feedbackId ? null : item.feedbackId))
            }
          />
        ))}
      </div>
    </div>
  );
}

/**
 * Issue #85: QUICK評価(絵文字1クリック評価)を`relatedFeature`×`rating`で
 * 期間ごとに集計したグラフ。機能改善のリリース時期と評価推移を突き合わせる
 * のが目的のため、期間軸(週次/月次)での時系列表示を優先し、機能は
 * セレクトで1つずつ切り替えて見る形にする(複数機能を1グラフに重ねると
 * 積み上げ棒の内訳が読めなくなるため)。
 */
function QuickFeedbackStatsChart({
  quickStats,
  period,
  onPeriodChange,
}: {
  quickStats: FeedbackStats["quickStats"];
  period: QuickStatsPeriod;
  onPeriodChange: (period: QuickStatsPeriod) => void;
}) {
  const featureOptions = useMemo(() => {
    const features = new Set<string>();
    for (const bucket of quickStats.buckets) {
      for (const feature of Object.keys(bucket.byFeatureRating)) {
        features.add(feature);
      }
    }
    return Array.from(features).sort();
  }, [quickStats.buckets]);

  const [selectedFeature, setSelectedFeature] = useState<string>("ALL");

  const chartData = useMemo(
    () =>
      quickStats.buckets.map((bucket) => {
        const counts: Record<FeedbackRating, number> = { GOOD: 0, NEUTRAL: 0, BAD: 0 };
        const featureEntries =
          selectedFeature === "ALL"
            ? Object.values(bucket.byFeatureRating)
            : bucket.byFeatureRating[selectedFeature]
              ? [bucket.byFeatureRating[selectedFeature]]
              : [];
        for (const ratingCounts of featureEntries) {
          for (const [rating, count] of Object.entries(ratingCounts)) {
            counts[rating as FeedbackRating] += count ?? 0;
          }
        }
        return { bucketStart: bucket.bucketStart, ...counts };
      }),
    [quickStats.buckets, selectedFeature],
  );

  const hasData = chartData.some((d) => d.GOOD + d.NEUTRAL + d.BAD > 0);

  return (
    <Card>
      <CardContent className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-medium">簡易評価の推移</p>
          <div className="flex gap-2">
            <Select value={period} onValueChange={(v) => v && onPeriodChange(v as QuickStatsPeriod)}>
              <SelectTrigger className="w-24">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(Object.entries(QUICK_STATS_PERIOD_LABELS) as [QuickStatsPeriod, string][]).map(
                  ([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  ),
                )}
              </SelectContent>
            </Select>
            <Select value={selectedFeature} onValueChange={(v) => v && setSelectedFeature(v)}>
              <SelectTrigger className="w-36">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">すべての機能</SelectItem>
                {featureOptions.map((feature) => (
                  <SelectItem key={feature} value={feature}>
                    {RELATED_FEATURE_LABELS[feature] ?? feature}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {!hasData ? (
          <p className="text-muted-foreground text-sm">この期間の簡易評価はまだありません</p>
        ) : (
          <ChartContainer config={RATING_CHART_CONFIG} className="aspect-auto h-48 w-full">
            <BarChart data={chartData}>
              <CartesianGrid vertical={false} />
              <XAxis
                dataKey="bucketStart"
                tickLine={false}
                axisLine={false}
                tickFormatter={(value: string) => format(parseISO(value), "M/d")}
              />
              <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={24} />
              <ChartTooltip
                content={
                  <ChartTooltipContent
                    labelFormatter={(value) => format(parseISO(String(value)), "M月d日")}
                  />
                }
              />
              <ChartLegend content={<ChartLegendContent />} />
              <Bar dataKey="GOOD" stackId="rating" fill="var(--color-status-good)" radius={[0, 0, 4, 4]} />
              <Bar dataKey="NEUTRAL" stackId="rating" fill="var(--color-status-warning)" />
              <Bar dataKey="BAD" stackId="rating" fill="var(--color-status-critical)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  );
}

function FeedbackListCard({
  item,
  expanded,
  onToggle,
}: {
  item: FeedbackItem;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <Card onClick={onToggle} className="cursor-pointer">
      <CardContent className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <div className="flex flex-wrap items-center gap-1">
            <Badge variant={item.kind === "QUICK" ? "secondary" : "outline"}>
              {item.kind === "QUICK" ? "簡易評価" : FEEDBACK_CATEGORY_LABELS[item.category!]}
            </Badge>
            <Badge variant="outline">{FEEDBACK_STATUS_LABELS[item.status]}</Badge>
            {item.priority && (
              <Badge variant="outline">優先度{FEEDBACK_PRIORITY_LABELS[item.priority]}</Badge>
            )}
          </div>
          <span className="text-muted-foreground text-xs">
            {format(parseISO(item.createdAt), "M月d日 HH:mm")}
          </span>
        </div>
        <p className="text-sm">{item.relatedFeature}</p>
        {item.content && <p className="text-muted-foreground text-sm">{item.content}</p>}
        {expanded && <FeedbackDetailPanel feedbackId={item.feedbackId} />}
      </CardContent>
    </Card>
  );
}

function FeedbackDetailPanel({ feedbackId }: { feedbackId: string }) {
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();
  const [replyText, setReplyText] = useState("");

  const { data: detail, isLoading } = useQuery({
    queryKey: feedbackKeys.detail(feedbackId),
    queryFn: () => getFeedback(feedbackId),
  });

  const updateMutation = useMutation({
    mutationFn: (input: { status?: string; priority?: string; reply?: string }) =>
      updateFeedback(feedbackId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: feedbackKeys.detail(feedbackId) });
      queryClient.invalidateQueries({ queryKey: feedbackKeys.all });
      toast.success("更新しました");
      setReplyText("");
    },
    onError: handleApiError,
  });

  if (isLoading || !detail) {
    return <Skeleton className="h-16 w-full" />;
  }

  return (
    <div
      className="flex flex-col gap-3 border-t pt-3"
      onClick={(e) => e.stopPropagation()}
    >
      {detail.attachmentUrls && detail.attachmentUrls.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {detail.attachmentUrls.map((url) => (
            <img key={url} src={url} alt="添付スクリーンショット" className="h-24 rounded-md" />
          ))}
        </div>
      )}

      {detail.reply && (
        <div className="bg-muted rounded-md p-2 text-sm">
          <p className="font-medium">返信済み</p>
          <p>{detail.reply.message}</p>
        </div>
      )}

      <div className="flex gap-2">
        <Select
          value={detail.status}
          onValueChange={(v) => v && updateMutation.mutate({ status: v })}
        >
          <SelectTrigger className="flex-1">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {Object.entries(FEEDBACK_STATUS_LABELS).map(([value, label]) => (
              <SelectItem key={value} value={value}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={detail.priority ?? ""}
          onValueChange={(v) => v && updateMutation.mutate({ priority: v })}
        >
          <SelectTrigger className="flex-1">
            <SelectValue placeholder="優先度" />
          </SelectTrigger>
          <SelectContent>
            {(Object.entries(FEEDBACK_PRIORITY_LABELS) as [FeedbackPriority, string][]).map(
              ([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ),
            )}
          </SelectContent>
        </Select>
      </div>

      <div className="flex flex-col gap-2">
        <Textarea
          placeholder="投稿者への返信"
          value={replyText}
          onChange={(e) => setReplyText(e.target.value)}
          rows={3}
        />
        <Button
          size="sm"
          disabled={!replyText || updateMutation.isPending}
          onClick={() => updateMutation.mutate({ reply: replyText })}
        >
          返信を送信
        </Button>
      </div>
    </div>
  );
}
