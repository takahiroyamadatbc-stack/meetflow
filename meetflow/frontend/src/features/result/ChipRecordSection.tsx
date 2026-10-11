import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import {
  createChipRecord,
  deleteChipRecord,
  resultKeys,
  updateChipRecord,
} from "@/features/result/api";
import { formatChipMismatch } from "@/features/result/calc";
import type { ChipRecord, ChipRecordInput } from "@/features/result/types";
import { GAME_TYPE_LABELS, type GameType } from "@/features/user/types";

const GAME_TYPES: GameType[] = ["MAHJONG4", "MAHJONG3"];

/**
 * チップ記録（Issue #116）。チップは半荘に紐付けず、イベント内で好きなタイミングで
 * 何回でも記録できる。合計が±0でない場合は警告を出すが、登録はできる
 * （点数合計の不一致と同じ扱い）。登録は誰でも、編集・削除はOWNER/ADMINのみ。
 */
export function ChipRecordSection({
  eventId,
  rows,
  isAdmin,
  chipRecords,
  nicknameByUserId,
  defaultGameType,
}: {
  eventId: string;
  rows: { userId: string; nickname: string }[];
  isAdmin: boolean;
  chipRecords: ChipRecord[];
  nicknameByUserId: Map<string, string>;
  defaultGameType: GameType;
}) {
  const orderedRecords = [...chipRecords].sort(
    (a, b) => Number(a.recordNo) - Number(b.recordNo),
  );

  return (
    <div className="flex flex-col gap-4">
      {orderedRecords.length > 0 && (
        <div>
          <h2 className="mb-2 text-base font-semibold">チップの記録</h2>
          <div className="flex flex-col gap-1">
            {orderedRecords.map((record) => (
              <ChipRecordRow
                key={record.recordNo}
                eventId={eventId}
                record={record}
                rows={rows}
                isAdmin={isAdmin}
                nicknameByUserId={nicknameByUserId}
              />
            ))}
          </div>
        </div>
      )}

      <div>
        <h2 className="mb-2 text-base font-semibold">チップを記録</h2>
        <p className="text-muted-foreground mb-2 text-xs">
          半荘とは別に、好きなタイミングで何回でも記録できます。記録したチップはイベントの累計に合算されます。
        </p>
        <ChipRecordForm
          rows={rows}
          initialGameType={defaultGameType}
          submitLabel="チップを記録する"
          resetOnSuccess
          onSubmit={(input) => createChipRecord(eventId, input)}
          onSuccess={() => toast.success("チップを記録しました")}
          eventId={eventId}
        />
      </div>
    </div>
  );
}

function ChipRecordRow({
  eventId,
  record,
  rows,
  isAdmin,
  nicknameByUserId,
}: {
  eventId: string;
  record: ChipRecord;
  rows: { userId: string; nickname: string }[];
  isAdmin: boolean;
  nicknameByUserId: Map<string, string>;
}) {
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();
  const [editing, setEditing] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const deleteMutation = useMutation({
    mutationFn: () => deleteChipRecord(eventId, record.recordNo),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: resultKeys.eventChipRecords(eventId) });
      toast.success("チップの記録を削除しました");
    },
    onError: handleApiError,
  });

  const title = `チップ記録${Number(record.recordNo)}（${GAME_TYPE_LABELS[record.gameType]}）`;
  // 記録後に参加を取り消した人の行も編集で消えないよう、記録済みの参加者も入力欄に含める
  const editRows = [
    ...rows,
    ...record.chips
      .filter((c) => !rows.some((r) => r.userId === c.userId))
      .map((c) => ({ userId: c.userId, nickname: nicknameByUserId.get(c.userId) ?? c.userId })),
  ];

  return (
    <div className="flex flex-col gap-1.5 border-b pb-2 last:border-b-0 last:pb-0">
      <div className="flex items-center justify-between text-sm">
        <span>
          {title}
          <span className="text-muted-foreground ml-2 text-xs">
            {format(parseISO(record.recordedAt), "HH:mm")}
          </span>
        </span>
        {isAdmin && !editing && (
          <div className="flex items-center gap-3">
            <button type="button" className="underline" onClick={() => setEditing(true)}>
              編集
            </button>
            <button
              type="button"
              className="text-destructive underline"
              onClick={() => setConfirmOpen(true)}
            >
              削除
            </button>
          </div>
        )}
      </div>

      {editing ? (
        <ChipRecordForm
          rows={editRows}
          initialGameType={record.gameType}
          initialChips={record.chips}
          submitLabel="更新する"
          onSubmit={(input) => updateChipRecord(eventId, record.recordNo, input)}
          onSuccess={() => {
            toast.success("チップの記録を更新しました");
            setEditing(false);
          }}
          onCancel={() => setEditing(false)}
          eventId={eventId}
        />
      ) : (
        <>
          <div className="flex gap-1.5 overflow-x-auto">
            {record.chips.map((c) => (
              <div
                key={c.userId}
                className="flex min-w-16 shrink-0 flex-col items-center gap-0.5 rounded-md border px-2 py-1"
              >
                <span className="max-w-16 truncate text-[11px]">
                  {nicknameByUserId.get(c.userId) ?? c.userId}
                </span>
                <span className="text-sm font-semibold">
                  {c.chipCount > 0 ? `+${c.chipCount}` : c.chipCount}枚
                </span>
              </div>
            ))}
          </div>
          {record.chipTotal !== 0 && (
            <p className="text-xs text-amber-600">
              チップの合計が{formatChipMismatch(record.chipTotal)}です（±0になっていません）
            </p>
          )}
        </>
      )}

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{title}を削除しますか？</AlertDialogTitle>
            <AlertDialogDescription>
              このチップの記録が削除されます。この操作は取り消せません。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>キャンセル</AlertDialogCancel>
            <AlertDialogAction onClick={() => deleteMutation.mutate()}>削除する</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

/** チップの入力フォーム（新規記録・編集で共用）。0枚の参加者は送信しない。 */
function ChipRecordForm({
  eventId,
  rows,
  initialGameType,
  initialChips = [],
  submitLabel,
  resetOnSuccess = false,
  onSubmit,
  onSuccess,
  onCancel,
}: {
  eventId: string;
  rows: { userId: string; nickname: string }[];
  initialGameType: GameType;
  initialChips?: { userId: string; chipCount: number }[];
  submitLabel: string;
  resetOnSuccess?: boolean;
  onSubmit: (input: ChipRecordInput) => Promise<unknown>;
  onSuccess: () => void;
  onCancel?: () => void;
}) {
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();
  const initialValues = () =>
    Object.fromEntries(
      rows.map((r) => [
        r.userId,
        String(initialChips.find((c) => c.userId === r.userId)?.chipCount ?? ""),
      ]),
    );
  const [gameType, setGameType] = useState<GameType>(initialGameType);
  const [values, setValues] = useState<Record<string, string>>(initialValues);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const parsed = rows.map((r) => ({ userId: r.userId, raw: (values[r.userId] ?? "").trim() }));
  const hasInvalid = parsed.some((p) => p.raw !== "" && !/^-?\d+$/.test(p.raw));
  const chips = parsed
    .filter((p) => p.raw !== "" && /^-?\d+$/.test(p.raw) && Number(p.raw) !== 0)
    .map((p) => ({ userId: p.userId, chipCount: Number(p.raw) }));
  const total = chips.reduce((sum, c) => sum + c.chipCount, 0);

  const mutation = useMutation({
    mutationFn: () => onSubmit({ gameType, chips }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: resultKeys.eventChipRecords(eventId) });
      if (resetOnSuccess) setValues(Object.fromEntries(rows.map((r) => [r.userId, ""])));
      onSuccess();
    },
    onError: handleApiError,
  });

  const handleSubmit = () => {
    if (total !== 0) {
      setConfirmOpen(true);
      return;
    }
    mutation.mutate();
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex gap-2">
        {GAME_TYPES.map((gt) => (
          <Button
            key={gt}
            type="button"
            size="sm"
            variant={gameType === gt ? "default" : "outline"}
            onClick={() => setGameType(gt)}
          >
            {GAME_TYPE_LABELS[gt]}
          </Button>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-2">
        {rows.map((r) => (
          <label key={r.userId} className="flex flex-col gap-1 text-xs">
            {r.nickname}
            <Input
              type="number"
              inputMode="numeric"
              placeholder="0"
              value={values[r.userId] ?? ""}
              onChange={(e) => setValues((prev) => ({ ...prev, [r.userId]: e.target.value }))}
            />
          </label>
        ))}
      </div>

      {chips.length > 0 && total !== 0 && (
        <p className="text-sm text-amber-600">
          チップの合計が{formatChipMismatch(total)}です。±0になっているかご確認ください（登録は可能です）。
        </p>
      )}

      <div className="flex gap-2">
        <Button
          type="button"
          onClick={handleSubmit}
          disabled={chips.length === 0 || hasInvalid || mutation.isPending}
        >
          {submitLabel}
        </Button>
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel}>
            キャンセル
          </Button>
        )}
      </div>

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>チップの合計が±0になっていません</AlertDialogTitle>
            <AlertDialogDescription>
              チップの合計が{formatChipMismatch(total)}です。本当によろしいですか？
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>キャンセル</AlertDialogCancel>
            <AlertDialogAction onClick={() => mutation.mutate()}>このまま登録する</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
