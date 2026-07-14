import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { GAME_TYPE_LABELS, type GameType } from "@/features/user/types";

const GAME_TYPES: GameType[] = ["MAHJONG4", "MAHJONG3"];

type GameTypeCheckboxGroupProps = {
  value: GameType[];
  onChange: (value: GameType[]) => void;
};

export function GameTypeCheckboxGroup({ value, onChange }: GameTypeCheckboxGroupProps) {
  return (
    <div className="flex flex-col gap-2">
      {GAME_TYPES.map((gameType) => (
        <div key={gameType} className="flex items-center gap-2">
          <Checkbox
            id={`game-type-${gameType}`}
            checked={value.includes(gameType)}
            onCheckedChange={(checked) =>
              onChange(checked ? [...value, gameType] : value.filter((v) => v !== gameType))
            }
          />
          <Label htmlFor={`game-type-${gameType}`} className="font-normal">
            {GAME_TYPE_LABELS[gameType]}
          </Label>
        </div>
      ))}
    </div>
  );
}
