import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { LotteryRecord } from "@/features/draft/types";

type Props = {
  lotteries: LotteryRecord[];
  nameOf: (userId: string) => string;
};

/**
 * 抽選の記録（docs/draft/DESIGN.md §4.14）。
 * 検証可能性は「操作ログを残す」ところまでと決めたので、候補者・当選者・
 * 時刻をそのまま見せる。commit-revealのようなハッシュ表示は無い。
 */
export function LotteryLog({ lotteries, nameOf }: Props) {
  if (lotteries.length === 0) {
    return <p className="text-muted-foreground text-sm">まだ抽選は行われていません</p>;
  }
  return (
    <div className="flex flex-col gap-2">
      {lotteries.map((lottery, index) => (
        <Card key={`${lottery.round}-${lottery.wave}-${index}`}>
          <CardContent className="flex flex-col gap-1">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground text-xs">
                {lottery.round}巡目 / {lottery.wave}回目
              </span>
              <Badge variant="outline">
                {lottery.type === "PLAYER" ? "指名が重複" : "女流枠の抽選"}
              </Badge>
            </div>
            {lottery.playerName && <p className="text-sm font-medium">{lottery.playerName}</p>}
            <p className="text-sm">
              当選: <span className="font-medium">{nameOf(lottery.winnerUserId)}</span>
            </p>
            <p className="text-muted-foreground text-xs">
              候補: {lottery.candidates.map(nameOf).join("、")}
            </p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
