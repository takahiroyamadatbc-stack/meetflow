import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { parseISO } from "date-fns";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { availabilityKeys, listAvailability } from "@/features/availability/api";
import { paths } from "@/routes/paths";

/**
 * Issue #95: 対局終了直後・ホーム画面で、次回の空き予定が未提出のユーザーに
 * 前向きな文言（「未入力です」ではなく「次の候補、今出しとく?」）で提出を
 * 促す。「未提出」はAvailabilityRequest（管理者トリガーの募集）の有無に
 * 依存せず、当該コミュニティで今日以降の日時のAvailabilityを1件も
 * 持っていないことで判定する（常に動作するシンプルな基準）。
 */
export function AvailabilitySubmitPrompt({ communityId }: { communityId: string }) {
  const { data: availabilities } = useQuery({
    queryKey: availabilityKeys.list(communityId),
    queryFn: () => listAvailability(communityId),
  });

  if (!availabilities) {
    return null;
  }
  const hasFutureAvailability = availabilities.some(
    (a) => parseISO(a.startTime).getTime() > Date.now(),
  );
  if (hasFutureAvailability) {
    return null;
  }

  return (
    <Card>
      <CardContent className="flex items-center justify-between gap-2">
        <p className="text-sm">次の候補、今出しとく?</p>
        <Link to={paths.availabilityCalendar(communityId)}>
          <Button size="sm">空き予定を登録</Button>
        </Link>
      </CardContent>
    </Card>
  );
}
