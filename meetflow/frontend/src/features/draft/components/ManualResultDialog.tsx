import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/api/errors";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { draftKeys, submitManualResult } from "@/features/draft/api";

type Row = { name: string; point: string };

const EMPTY_ROWS: Row[] = [
  { name: "", point: "" },
  { name: "", point: "" },
  { name: "", point: "" },
  { name: "", point: "" },
];

/**
 * 手動入力のフォールバック（docs/draft/DESIGN.md §7）。
 *
 * 「手動入力のフォールバック画面を最初から作る。これがあれば最悪シーズンは
 * 回る」という方針に対応する画面。公式サイトのHTMLが変わってパースが直らない
 * 間も、主催者が打ち込めば集計を続けられる。
 *
 * 次に取得が成功すると公式の値で上書きされる（公式が正）。
 */
export function ManualResultDialog({
  draftId,
  open,
  onClose,
}: {
  draftId: string;
  open: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();
  const [date, setDate] = useState("");
  const [no, setNo] = useState("");
  const [firstGame, setFirstGame] = useState<Row[]>(EMPTY_ROWS);
  const [secondGame, setSecondGame] = useState<Row[] | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const reset = () => {
    setDate("");
    setNo("");
    setFirstGame(EMPTY_ROWS);
    setSecondGame(null);
    setFormError(null);
  };

  const mutation = useMutation({
    mutationFn: () =>
      submitManualResult(draftId, {
        date,
        no: Number(no),
        games: [
          { label: "第1回戦", rows: toRows(firstGame) },
          ...(secondGame ? [{ label: "第2回戦", rows: toRows(secondGame) }] : []),
        ],
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: draftKeys.standings(draftId) });
      toast.success("結果を登録しました");
      reset();
      onClose();
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === "DRAFT_VALIDATION_ERROR") {
        setFormError(error.message);
        return;
      }
      handleApiError(error);
    },
  });

  const filled = (rows: Row[]) => rows.every((row) => row.name.trim() && row.point.trim() !== "");
  const canSubmit =
    !!date && !!no && filled(firstGame) && (!secondGame || filled(secondGame));

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          reset();
          onClose();
        }
      }}
    >
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>結果を手動で入力</DialogTitle>
        </DialogHeader>
        <p className="text-muted-foreground text-xs">
          公式サイトから取得できないときの応急手段です。次に取得が成功すると
          公式の値で上書きされます。
        </p>

        <div className="flex gap-2">
          <div className="flex flex-1 flex-col gap-1">
            <Label htmlFor="manual-date">対局日</Label>
            <Input
              id="manual-date"
              type="date"
              value={date}
              onChange={(event) => setDate(event.target.value)}
            />
          </div>
          <div className="flex w-24 flex-col gap-1">
            <Label htmlFor="manual-no">節番号</Label>
            <Input
              id="manual-no"
              type="number"
              inputMode="numeric"
              value={no}
              onChange={(event) => setNo(event.target.value)}
            />
          </div>
        </div>

        <GameRows label="第1回戦" rows={firstGame} onChange={setFirstGame} />
        {secondGame ? (
          <GameRows label="第2回戦" rows={secondGame} onChange={setSecondGame} />
        ) : (
          <Button variant="outline" size="sm" onClick={() => setSecondGame(EMPTY_ROWS)}>
            ＋第2回戦を追加
          </Button>
        )}

        {formError && <p className="text-destructive text-sm">{formError}</p>}

        <Button disabled={!canSubmit || mutation.isPending} onClick={() => mutation.mutate()}>
          登録する
        </Button>
      </DialogContent>
    </Dialog>
  );
}

function GameRows({
  label,
  rows,
  onChange,
}: {
  label: string;
  rows: Row[];
  onChange: (rows: Row[]) => void;
}) {
  const update = (index: number, patch: Partial<Row>) =>
    onChange(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));

  return (
    <div className="flex flex-col gap-2">
      <Label>{label}</Label>
      {rows.map((row, index) => (
        <div key={index} className="flex gap-2">
          <Input
            aria-label={`${label} 選手${index + 1}`}
            placeholder="選手名"
            value={row.name}
            onChange={(event) => update(index, { name: event.target.value })}
          />
          <Input
            aria-label={`${label} ポイント${index + 1}`}
            className="w-28"
            inputMode="decimal"
            placeholder="±00.0"
            value={row.point}
            onChange={(event) => update(index, { point: event.target.value })}
          />
        </div>
      ))}
    </div>
  );
}

/** 着順はポイントの降順から導出する（入力項目を増やさないため）。 */
function toRows(rows: Row[]) {
  const parsed = rows.map((row) => ({
    name: row.name.trim(),
    point: Number(row.point),
  }));
  const ordered = [...parsed].sort((a, b) => b.point - a.point);
  return parsed.map((row) => ({
    rank: ordered.findIndex((entry) => entry.name === row.name) + 1,
    name: row.name,
    point: row.point,
  }));
}
