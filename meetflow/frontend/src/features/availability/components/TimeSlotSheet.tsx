import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { GameTypeCheckboxGroup } from "@/features/availability/components/GameTypeCheckboxGroup";
import type { GameType } from "@/features/user/types";

export type TimeSlotValue = {
  startHour: string;
  endHour: string;
  gameTypes: GameType[];
  comment: string;
};

type TimeSlotSheetProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedDateCount: number;
  onSubmit: (value: TimeSlotValue) => void;
  submitting?: boolean;
};

/**
 * S-09 空き予定登録画面の時間帯選択パネル。
 * カレンダーで選択した全ての日付に、ここで指定した同一の時間帯・条件を適用する。
 */
export function TimeSlotSheet({
  open,
  onOpenChange,
  selectedDateCount,
  onSubmit,
  submitting,
}: TimeSlotSheetProps) {
  const [startHour, setStartHour] = useState("19:00");
  const [endHour, setEndHour] = useState("22:00");
  const [gameTypes, setGameTypes] = useState<GameType[]>([]);
  const [comment, setComment] = useState("");

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="bottom">
        <SheetHeader>
          <SheetTitle>時間帯を選択</SheetTitle>
          <SheetDescription>選択した{selectedDateCount}日すべてに同じ時間帯を登録します</SheetDescription>
        </SheetHeader>
        <div className="flex flex-col gap-4 px-4">
          <div className="flex items-center gap-2">
            <div className="flex-1">
              <Label htmlFor="start-hour">開始時刻</Label>
              <Input
                id="start-hour"
                type="time"
                value={startHour}
                onChange={(e) => setStartHour(e.target.value)}
              />
            </div>
            <div className="flex-1">
              <Label htmlFor="end-hour">終了時刻</Label>
              <Input
                id="end-hour"
                type="time"
                value={endHour}
                onChange={(e) => setEndHour(e.target.value)}
              />
            </div>
          </div>
          <div>
            <Label className="mb-2">プレイしたいゲーム</Label>
            <GameTypeCheckboxGroup value={gameTypes} onChange={setGameTypes} />
          </div>
          <div>
            <Label htmlFor="comment" className="mb-2">
              コメント（任意）
            </Label>
            <Textarea id="comment" value={comment} onChange={(e) => setComment(e.target.value)} />
          </div>
        </div>
        <SheetFooter>
          <Button
            disabled={submitting}
            onClick={() => onSubmit({ startHour, endHour, gameTypes, comment })}
          >
            登録する
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
