import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { CurrentWave } from "@/features/draft/types";

type Props = {
  wave: CurrentWave;
  rounds: number;
  nameOf: (userId: string) => string;
};

/**
 * 進行中のwaveの状況。
 *
 * DESIGN.md §4.6: 開示前に見せてよいのは「誰が提出済みか」だけで、中身は出さない。
 * 未提出者を名前で出すのは、§4.7の通り制限時間を設けない代わりに
 * 主催者が催促できるようにするため。
 */
export function WaveProgress({ wave, rounds, nameOf }: Props) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">
            {wave.round}巡目
            {wave.wave > 1 && <span className="text-muted-foreground">（{wave.wave}回目の指名）</span>}
          </span>
          <span className="text-muted-foreground text-xs">全{rounds}巡</span>
        </div>

        {wave.revealed ? (
          <RevealedPicks wave={wave} nameOf={nameOf} />
        ) : (
          <>
            <p className="text-sm">
              {wave.submittedUserIds.length} / {wave.expectedUserIds.length}人 提出完了
            </p>
            {wave.pendingUserIds.length > 0 && (
              <p className="text-muted-foreground text-xs">
                未提出: {wave.pendingUserIds.map(nameOf).join("、")}
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function RevealedPicks({ wave, nameOf }: { wave: CurrentWave; nameOf: (id: string) => string }) {
  return (
    <ul className="flex flex-col gap-1">
      {(wave.picks ?? []).map((pick) => (
        <li key={pick.userId} className="flex items-center justify-between text-sm">
          <span className="flex items-center gap-2">
            <span className="text-muted-foreground">{nameOf(pick.userId)}</span>
            <span>{pick.playerName}</span>
            {pick.byProxy && (
              <Badge variant="outline" className="px-1.5 py-0 text-[10px]">
                代理
              </Badge>
            )}
          </span>
          <PickOutcomeBadge outcome={pick.outcome} />
        </li>
      ))}
    </ul>
  );
}

function PickOutcomeBadge({ outcome }: { outcome: "PENDING" | "CONFIRMED" | "LOST" }) {
  if (outcome === "CONFIRMED") return <Badge variant="secondary">確定</Badge>;
  if (outcome === "LOST") return <Badge variant="outline">落選</Badge>;
  return <Badge variant="destructive">抽選待ち</Badge>;
}
