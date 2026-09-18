import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { PICK_BLOCK_MESSAGES, type PickBlockReason } from "@/features/draft/rules";
import type { DraftPlayer } from "@/features/draft/types";

type Props = {
  players: DraftPlayer[];
  /** 指名できない理由（指名できるならnull） */
  blockReasonOf: (player: DraftPlayer) => PickBlockReason | null;
  selectedPlayerId: string | null;
  onSelect: (playerId: string) => void;
  /** userId -> 表示名（確保済みの選手に「〇〇さんが指名済み」を出すため） */
  nameOf: (userId: string) => string;
  disabled?: boolean;
};

/**
 * チームごとにまとめた選手の選択リスト。
 * ロゴ・選手写真は使わない（docs/draft/DESIGN.md §7「使わないもの」）ため、
 * 文字とバッジだけで構成する。
 */
export function PlayerPicker({
  players,
  blockReasonOf,
  selectedPlayerId,
  onSelect,
  nameOf,
  disabled,
}: Props) {
  const teams = groupByTeam(players);

  return (
    <div className="flex flex-col gap-3">
      {teams.map(([teamName, teamPlayers]) => (
        <Card key={teamName}>
          <CardContent className="flex flex-col gap-1">
            <p className="text-muted-foreground mb-1 text-xs font-medium">{teamName}</p>
            {teamPlayers.map((player) => {
              const reason = blockReasonOf(player);
              const selected = selectedPlayerId === player.playerId;
              const blocked = reason !== null || disabled;
              return (
                <button
                  key={player.playerId}
                  type="button"
                  disabled={blocked}
                  aria-pressed={selected}
                  onClick={() => onSelect(player.playerId)}
                  className={cn(
                    "flex items-center justify-between rounded-md px-2 py-2 text-left text-sm",
                    selected && "bg-primary/10 ring-primary ring-1",
                    blocked && "text-muted-foreground opacity-60",
                    !blocked && !selected && "hover:bg-accent",
                  )}
                >
                  <span className="flex items-center gap-2">
                    <span className={cn(player.takenByUserId && "line-through")}>
                      {player.name}
                    </span>
                    {player.isFemale && (
                      <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">
                        女流
                      </Badge>
                    )}
                  </span>
                  <span className="text-muted-foreground text-xs">
                    {player.takenByUserId
                      ? `${nameOf(player.takenByUserId)}が指名済み`
                      : reason
                        ? PICK_BLOCK_MESSAGES[reason]
                        : ""}
                  </span>
                </button>
              );
            })}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function groupByTeam(players: DraftPlayer[]): [string, DraftPlayer[]][] {
  const map = new Map<string, DraftPlayer[]>();
  for (const player of players) {
    const list = map.get(player.teamName);
    if (list) list.push(player);
    else map.set(player.teamName, [player]);
  }
  return [...map.entries()];
}
