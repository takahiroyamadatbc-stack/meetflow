import { format, formatDistanceToNow, parseISO } from "date-fns";
import { ja } from "date-fns/locale";
import { Link } from "react-router-dom";
import { AlertTriangle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { Candidate } from "@/features/matching/types";
import { paths } from "@/routes/paths";

export function CandidateCard({
  communityId,
  candidate,
}: {
  communityId: string;
  candidate: Candidate;
}) {
  return (
    <Link to={paths.matchingCandidateDetail(communityId, candidate.candidateId)}>
      <Card>
        <CardContent className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-lg font-semibold">
              {candidate.score !== null ? `${candidate.score}点` : "手動作成"}
            </span>
            {candidate.startTime && (
              <span className="text-muted-foreground text-sm">
                {format(parseISO(candidate.startTime), "M月d日 HH:mm")}
              </span>
            )}
          </div>

          <span className="text-muted-foreground text-xs">
            {formatDistanceToNow(parseISO(candidate.createdAt), { addSuffix: true, locale: ja })}
            に生成
          </span>

          {candidate.members.some((m) => m.conflictWarning) && (
            <div className="text-destructive flex items-center gap-1 text-xs">
              <AlertTriangle className="size-3.5" />
              メンバーの一部が他の予定と重複の可能性があります
            </div>
          )}

          <div className="flex flex-wrap gap-1">
            {candidate.members.map((member) => (
              <Badge key={member.userId} variant="secondary">
                {member.nickname}
              </Badge>
            ))}
          </div>

          <div className="flex flex-wrap gap-1">
            {candidate.reasons.map((reason) => (
              <Badge key={reason} variant="outline">
                {reason}
              </Badge>
            ))}
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
