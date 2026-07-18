import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { CandidateCard } from "@/features/matching/components/CandidateCard";
import {
  generateCandidates,
  listCandidates,
  listEventTemplates,
  matchingKeys,
} from "@/features/matching/api";
import { GAME_TYPE_LABELS } from "@/features/user/types";
import { QuickFeedbackPrompt } from "@/features/feedback/QuickFeedbackPrompt";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";

/** S-12 マッチング候補一覧画面 */
export function MatchingCandidateListPage() {
  const { communityId } = useParams<{ communityId: string }>();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [showQuickFeedback, setShowQuickFeedback] = useState(false);

  const { data: templates, isLoading: isLoadingTemplates } = useQuery({
    queryKey: matchingKeys.templates(communityId!),
    queryFn: () => listEventTemplates(communityId!),
    enabled: !!communityId,
  });

  const { data: candidates, isLoading: isLoadingCandidates } = useQuery({
    queryKey: matchingKeys.candidates(communityId!),
    queryFn: () => listCandidates(communityId!),
    enabled: !!communityId,
  });

  const generateMutation = useMutation({
    mutationFn: (templateId: string) => generateCandidates(communityId!, templateId),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: matchingKeys.candidates(communityId!) });
      toast.success(
        created.length > 0
          ? `候補を${created.length}件生成しました`
          : "条件に合う候補が見つかりませんでした",
      );
      if (created.length > 0) {
        setShowQuickFeedback(true);
      }
    },
    onError: handleApiError,
  });

  if (isLoadingTemplates || isLoadingCandidates) {
    return (
      <div className="flex flex-col gap-3 p-4">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex flex-col gap-2">
        <p className="text-sm font-medium">開催条件を選んで候補を生成</p>
        <div className="flex flex-wrap gap-2">
          {(templates ?? []).map((template) => (
            <Button
              key={template.templateId}
              type="button"
              variant={selectedTemplateId === template.templateId ? "default" : "outline"}
              size="sm"
              onClick={() => setSelectedTemplateId(template.templateId)}
            >
              {GAME_TYPE_LABELS[template.gameType]}（優先度{template.priority}）
            </Button>
          ))}
        </div>
        <Button
          disabled={!selectedTemplateId || generateMutation.isPending}
          onClick={() => selectedTemplateId && generateMutation.mutate(selectedTemplateId)}
        >
          候補を生成
        </Button>
      </div>

      {showQuickFeedback && (
        <QuickFeedbackPrompt
          relatedFeature="MATCHING_CANDIDATE"
          storageKey={`matching:${communityId}:${candidates?.map((c) => c.candidateId).join(",")}`}
        />
      )}

      {(candidates ?? []).length === 0 ? (
        <EmptyState
          message="候補がまだありません"
          description="開催条件を選んで候補を生成してください"
        />
      ) : (
        <div className="flex flex-col gap-3">
          {(candidates ?? [])
            .filter((c) => c.status === "PENDING")
            .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
            .map((candidate) => (
              <CandidateCard
                key={candidate.candidateId}
                communityId={communityId!}
                candidate={candidate}
              />
            ))}
        </div>
      )}
    </div>
  );
}
