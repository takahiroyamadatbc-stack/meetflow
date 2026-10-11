import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import {
  communityKeys,
  getCommunity,
  updateGameDefaults,
} from "@/features/community/api";
import type { GameDefaults } from "@/features/community/types";
import { expectedPlayerCount, resolveGameDefaults } from "@/features/result/calc";
import { GAME_TYPE_LABELS, type GameType } from "@/features/user/types";
import { paths } from "@/routes/paths";

const GAME_TYPES: GameType[] = ["MAHJONG4", "MAHJONG3"];

/** 入力途中の値（空欄を許すため文字列で持つ） */
type EntryDraft = {
  enabled: boolean;
  startingPoints: string;
  returnPoints: string;
  umaByRank: string[];
};

function toDraft(gameType: GameType, gameDefaults: GameDefaults | null): EntryDraft {
  const entry = resolveGameDefaults(gameType, gameDefaults);
  return {
    enabled: !!gameDefaults?.[gameType],
    startingPoints: String(entry.startingPoints),
    returnPoints: String(entry.returnPoints),
    umaByRank: entry.umaByRank.map(String),
  };
}

function isIntString(value: string): boolean {
  return /^-?\d+$/.test(value.trim());
}

function isNonNegativeIntString(value: string): boolean {
  return /^\d+$/.test(value.trim());
}

function isDraftValid(draft: EntryDraft): boolean {
  if (!draft.enabled) return true;
  return (
    isNonNegativeIntString(draft.startingPoints) &&
    isNonNegativeIntString(draft.returnPoints) &&
    draft.umaByRank.every(isIntString)
  );
}

/**
 * S-05f 成績入力のデフォルト設定変更（S-05から遷移、Issue #115）。
 * 成績入力（自動計算）の配給原点・返し点・ウマのデフォルト値を、種目ごとに設定する。
 * 同一イベント内に前回の半荘がある場合は、そちらの設定が優先される。
 */
export function GameDefaultsEditPage() {
  const { communityId } = useParams<{ communityId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();

  const { data: community, isLoading } = useQuery({
    queryKey: communityKeys.detail(communityId!),
    queryFn: () => getCommunity(communityId!),
    enabled: !!communityId,
  });

  const [drafts, setDrafts] = useState<Record<GameType, EntryDraft> | null>(null);

  if (community && !drafts) {
    setDrafts({
      MAHJONG4: toDraft("MAHJONG4", community.gameDefaults),
      MAHJONG3: toDraft("MAHJONG3", community.gameDefaults),
    });
  }

  const mutation = useMutation({
    mutationFn: () => {
      const gameDefaults: GameDefaults = {};
      for (const gt of GAME_TYPES) {
        const draft = drafts![gt];
        if (!draft.enabled) continue;
        gameDefaults[gt] = {
          startingPoints: Number(draft.startingPoints),
          returnPoints: Number(draft.returnPoints),
          umaByRank: draft.umaByRank.map(Number),
        };
      }
      return updateGameDefaults(communityId!, gameDefaults);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: communityKeys.detail(communityId!) });
      toast.success("成績入力のデフォルト設定を変更しました");
      navigate(paths.communityDetail(communityId!));
    },
    onError: handleApiError,
  });

  if (isLoading || !drafts) {
    return (
      <div className="flex flex-col gap-4 p-4">
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  const updateDraft = (gameType: GameType, patch: Partial<EntryDraft>) => {
    setDrafts((prev) => (prev ? { ...prev, [gameType]: { ...prev[gameType], ...patch } } : prev));
  };
  const canSave = GAME_TYPES.every((gt) => isDraftValid(drafts[gt]));

  return (
    <div className="flex flex-col gap-4 p-4">
      <p className="text-muted-foreground text-sm">
        成績入力（自動計算）を開いたときの配給原点・返し点・ウマの初期値を設定します。同じイベントで前に入力した半荘がある場合は、その半荘の設定が優先されます。
      </p>

      {GAME_TYPES.map((gt) => (
        <GameDefaultsSection
          key={gt}
          gameType={gt}
          draft={drafts[gt]}
          onChange={(patch) => updateDraft(gt, patch)}
        />
      ))}

      <Button onClick={() => mutation.mutate()} disabled={!canSave || mutation.isPending}>
        保存する
      </Button>
    </div>
  );
}

function GameDefaultsSection({
  gameType,
  draft,
  onChange,
}: {
  gameType: GameType;
  draft: EntryDraft;
  onChange: (patch: Partial<EntryDraft>) => void;
}) {
  const label = GAME_TYPE_LABELS[gameType];
  const checkboxId = `game-defaults-${gameType}`;
  const playerCount = expectedPlayerCount(gameType);
  const okaPreview =
    isNonNegativeIntString(draft.startingPoints) && isNonNegativeIntString(draft.returnPoints)
      ? ((Number(draft.returnPoints) - Number(draft.startingPoints)) * playerCount) / 1000
      : null;
  const umaSum = draft.umaByRank.every(isIntString)
    ? draft.umaByRank.reduce((sum, v) => sum + Number(v), 0)
    : null;

  return (
    <section className="flex flex-col gap-3 rounded-md border p-3" aria-label={label}>
      <div className="flex items-center gap-2">
        <Checkbox
          id={checkboxId}
          checked={draft.enabled}
          onCheckedChange={(checked) => onChange({ enabled: checked === true })}
        />
        <label htmlFor={checkboxId} className="text-sm font-medium">
          {label}のデフォルトを設定する
        </label>
      </div>

      {draft.enabled ? (
        <>
          <div className="grid grid-cols-2 gap-2">
            <label className="flex flex-col gap-1 text-xs">
              配給原点
              <Input
                type="number"
                inputMode="numeric"
                value={draft.startingPoints}
                onChange={(e) => onChange({ startingPoints: e.target.value })}
              />
            </label>
            <label className="flex flex-col gap-1 text-xs">
              返し点
              <Input
                type="number"
                inputMode="numeric"
                value={draft.returnPoints}
                onChange={(e) => onChange({ returnPoints: e.target.value })}
              />
            </label>
          </div>
          {okaPreview !== null && (
            <p className="text-muted-foreground text-xs">
              オカ（トップ取り）：{okaPreview > 0 ? "+" : ""}
              {okaPreview}
            </p>
          )}

          <div className="flex flex-col gap-1">
            <span className="text-xs">ウマ</span>
            <div className={playerCount === 4 ? "grid grid-cols-4 gap-2" : "grid grid-cols-3 gap-2"}>
              {draft.umaByRank.map((value, index) => (
                <label key={index} className="flex flex-col gap-1 text-xs">
                  {index + 1}位
                  <Input
                    type="number"
                    inputMode="numeric"
                    value={value}
                    onChange={(e) =>
                      onChange({
                        umaByRank: draft.umaByRank.map((v, i) => (i === index ? e.target.value : v)),
                      })
                    }
                  />
                </label>
              ))}
            </div>
            {umaSum !== null && umaSum !== 0 && (
              <p className="text-destructive text-xs">
                ウマの合計が{umaSum > 0 ? "+" : ""}
                {umaSum}になっています（通常は0）
              </p>
            )}
          </div>
        </>
      ) : (
        <p className="text-muted-foreground text-xs">
          未設定の場合、成績入力ではシステム既定値（配給原点・返し点は
          {resolveGameDefaults(gameType, null).startingPoints}/
          {resolveGameDefaults(gameType, null).returnPoints}、ウマは0）を使います。
        </p>
      )}
    </section>
  );
}
