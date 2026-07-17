import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
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
  FEEDBACK_STATUS_LABELS,
  type FeedbackItem,
  type FeedbackPriority,
  type FeedbackStatus,
} from "@/features/feedback/types";

/** S-29 フィードバック管理画面（運営者限定） */
export function FeedbackAdminPage() {
  const isOperator = useIsOperator();
  const [filters, setFilters] = useState<FeedbackListFilters>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data: stats } = useQuery({
    queryKey: feedbackKeys.stats,
    queryFn: getFeedbackStats,
    enabled: isOperator,
  });

  const { data: feedbacks, isLoading } = useQuery({
    queryKey: feedbackKeys.list(filters),
    queryFn: () => listFeedback(filters),
    enabled: isOperator,
  });

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

      {!isLoading && (feedbacks ?? []).length === 0 && (
        <EmptyState message="フィードバックはありません" />
      )}

      <div className="flex flex-col gap-2">
        {(feedbacks ?? []).map((item) => (
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
