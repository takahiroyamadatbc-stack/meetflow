import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { DraftParticipant, RosterMap } from "@/features/draft/types";

type Props = {
  participants: DraftParticipant[];
  rosters: RosterMap;
  rounds: number;
  /** 自分の行を強調する */
  highlightUserId?: string | null;
};

/** 参加者ごとの確定チーム一覧（プロジェクター画面と自分の画面で共用） */
export function RosterBoard({ participants, rosters, rounds, highlightUserId }: Props) {
  return (
    <div className="flex flex-col gap-3">
      {participants.map((participant) => {
        const roster = rosters[participant.userId] ?? [];
        const needsFemale = participant.femaleCount === 0;
        return (
          <Card
            key={participant.userId}
            className={cn(highlightUserId === participant.userId && "ring-primary ring-1")}
          >
            <CardContent className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{participant.displayName}</span>
                <span className="text-muted-foreground text-xs">
                  {participant.playerCount} / {rounds}人
                </span>
              </div>
              {roster.length === 0 ? (
                <p className="text-muted-foreground text-xs">まだ指名していません</p>
              ) : (
                <ul className="flex flex-col gap-1">
                  {roster.map((entry) => (
                    <li key={entry.playerId} className="flex items-center gap-2 text-sm">
                      <span className="text-muted-foreground w-8 text-xs">{entry.round}巡</span>
                      <span>{entry.playerName}</span>
                      {entry.isFemale && (
                        <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">
                          女流
                        </Badge>
                      )}
                      <span className="text-muted-foreground text-xs">{entry.teamName}</span>
                    </li>
                  ))}
                </ul>
              )}
              {needsFemale && (
                // DESIGN.md §4.3(a): 最終巡までに女性を1人確保する必要がある。
                <p className="text-muted-foreground text-xs">女流選手がまだいません</p>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
