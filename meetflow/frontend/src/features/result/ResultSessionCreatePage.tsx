import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { EmptyState } from "@/components/feedback/EmptyState";
import { communityKeys, getCommunity } from "@/features/community/api";
import { eventKeys, getEvent, listParticipants } from "@/features/event/api";
import {
  createSession,
  getLastGameSettings,
  listEventSessions,
  resultKeys,
  updateSession,
} from "@/features/result/api";
import { computeLiveResults, hasScoreMismatch } from "@/features/result/calc";
import type {
  CalcMode,
  GameSessionDetail,
  LastGameSettings,
} from "@/features/result/types";
import { GAME_TYPE_LABELS, type GameType } from "@/features/user/types";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { getErrorDisplay, ApiError } from "@/api/errors";
import { paths } from "@/routes/paths";

const GAME_TYPES: GameType[] = ["MAHJONG4", "MAHJONG3"];
const CALC_MODES: { value: CalcMode; label: string }[] = [
  { value: "AUTO", label: "自動計算（ウマ・オカ）" },
  { value: "MANUAL", label: "手動計算（点数のみ）" },
];

const rowSchema = z.object({
  userId: z.string(),
  nickname: z.string(),
  score: z.coerce.number().int(),
  chipCount: z.coerce.number().int(),
});

const sessionSchema = z.object({
  gameType: z.enum(["MAHJONG4", "MAHJONG3"]),
  calcMode: z.enum(["AUTO", "MANUAL"]),
  startingPoints: z.coerce.number().int(),
  returnPoints: z.coerce.number().int(),
  umaByRank: z.array(z.coerce.number().int()),
  rows: z.array(rowSchema).min(1),
});
type SessionFormInput = z.input<typeof sessionSchema>;
type SessionFormValues = z.output<typeof sessionSchema>;

function numeric(value: unknown): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

/** S-21 成績登録・編集画面。入力（プレビュー含む）はイベント参加者全員が
 * 行えるが、実際の登録・編集（送信）はコミュニティのOWNER/ADMINのみ。 */
export function ResultSessionCreatePage() {
  const { eventId, sessionNo } = useParams<{ eventId: string; sessionNo?: string }>();
  const isEdit = !!sessionNo;

  const { data: event, isLoading: eventLoading } = useQuery({
    queryKey: eventKeys.detail(eventId!),
    queryFn: () => getEvent(eventId!),
    enabled: !!eventId,
  });

  const { data: community, isLoading: communityLoading } = useQuery({
    queryKey: communityKeys.detail(event?.communityId ?? ""),
    queryFn: () => getCommunity(event!.communityId),
    enabled: !!event?.communityId,
  });

  const { data: participants, isLoading: participantsLoading } = useQuery({
    queryKey: eventKeys.participants(eventId!),
    queryFn: () => listParticipants(eventId!),
    enabled: !!eventId,
  });

  const { data: sessions, isLoading: sessionsLoading } = useQuery({
    queryKey: resultKeys.eventSessions(eventId!),
    queryFn: () => listEventSessions(eventId!),
    enabled: !!eventId && isEdit,
  });

  const { data: lastSettings } = useQuery({
    queryKey: resultKeys.lastSettings(event?.communityId ?? ""),
    queryFn: () => getLastGameSettings(event!.communityId),
    enabled: !!event?.communityId && !isEdit,
  });

  const isLoading =
    eventLoading || communityLoading || participantsLoading || (isEdit && sessionsLoading);

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4 p-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (!event || !community || !participants) {
    return <EmptyState message="情報の取得に失敗しました" />;
  }

  const existingSession = isEdit
    ? sessions?.find((s) => s.sessionNo === sessionNo)
    : undefined;
  if (isEdit && !existingSession) {
    return <EmptyState message="指定した対局が見つかりません" />;
  }

  const nicknameByUserId = new Map(participants.map((p) => [p.userId, p.nickname]));
  const rows = existingSession
    ? existingSession.results.map((r) => ({
        userId: r.userId,
        nickname: nicknameByUserId.get(r.userId) ?? r.userId,
      }))
    : participants
        .filter((p) => p.status !== "CANCELLED")
        .map((p) => ({ userId: p.userId, nickname: p.nickname }));

  if (rows.length === 0) {
    return <EmptyState message="対局に参加しているメンバーがいません" />;
  }

  const isAdmin = community.role === "OWNER" || community.role === "ADMIN";

  return (
    <SessionForm
      eventId={eventId!}
      sessionNo={sessionNo}
      rows={rows}
      isAdmin={isAdmin}
      existingSession={existingSession}
      lastSettings={!isEdit ? lastSettings : undefined}
    />
  );
}

function SessionForm({
  eventId,
  sessionNo,
  rows,
  isAdmin,
  existingSession,
  lastSettings,
}: {
  eventId: string;
  sessionNo?: string;
  rows: { userId: string; nickname: string }[];
  isAdmin: boolean;
  existingSession?: GameSessionDetail;
  lastSettings?: LastGameSettings;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();

  const defaults = existingSession
    ? {
        gameType: existingSession.gameType,
        calcMode: existingSession.calcMode,
        startingPoints: existingSession.startingPoints ?? 25000,
        returnPoints: existingSession.returnPoints ?? 30000,
        umaByRank: existingSession.umaByRank ?? rows.map(() => 0),
      }
    : lastSettings?.found
      ? {
          gameType: lastSettings.gameType,
          calcMode: lastSettings.calcMode,
          startingPoints: lastSettings.startingPoints ?? 25000,
          returnPoints: lastSettings.returnPoints ?? 30000,
          umaByRank: lastSettings.umaByRank ?? rows.map(() => 0),
        }
      : {
          gameType: "MAHJONG4" as GameType,
          calcMode: "MANUAL" as CalcMode,
          startingPoints: 25000,
          returnPoints: 30000,
          umaByRank: rows.map(() => 0),
        };

  const scoreByUserId = new Map((existingSession?.results ?? []).map((r) => [r.userId, r.score]));
  const chipByUserId = new Map(
    (existingSession?.chips ?? []).map((c) => [c.userId, c.chipCount]),
  );

  const form = useForm<SessionFormInput, unknown, SessionFormValues>({
    resolver: zodResolver(sessionSchema),
    defaultValues: {
      gameType: defaults.gameType,
      calcMode: defaults.calcMode,
      startingPoints: defaults.startingPoints,
      returnPoints: defaults.returnPoints,
      umaByRank: rows.map((_, i) => defaults.umaByRank[i] ?? 0),
      rows: rows.map((r) => ({
        userId: r.userId,
        nickname: r.nickname,
        score: scoreByUserId.get(r.userId) ?? 0,
        chipCount: chipByUserId.get(r.userId) ?? 0,
      })),
    },
  });

  const calcMode = form.watch("calcMode");
  const watchedRows = form.watch("rows");
  const startingPoints = form.watch("startingPoints");
  const returnPoints = form.watch("returnPoints");
  const umaByRank = form.watch("umaByRank");

  const liveResults = computeLiveResults(
    watchedRows.map((r) => ({ userId: r.userId, nickname: r.nickname, score: numeric(r.score) })),
    calcMode,
    numeric(startingPoints),
    numeric(returnPoints),
    umaByRank.map(numeric),
  );
  const scoreMismatch =
    calcMode === "AUTO" &&
    hasScoreMismatch(
      watchedRows.map((r) => ({ score: numeric(r.score) })),
      numeric(startingPoints),
    );

  const mutation = useMutation({
    mutationFn: (values: SessionFormValues) => {
      const input = {
        gameType: values.gameType,
        calcMode: values.calcMode,
        results: values.rows.map((r) => ({ userId: r.userId, score: r.score })),
        chips: values.rows.map((r) => ({ userId: r.userId, chipCount: r.chipCount })),
        ...(values.calcMode === "AUTO"
          ? {
              startingPoints: values.startingPoints,
              returnPoints: values.returnPoints,
              umaByRank: values.umaByRank,
            }
          : {}),
      };
      return sessionNo
        ? updateSession(eventId, sessionNo, input)
        : createSession(eventId, input);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: resultKeys.eventSessions(eventId) });
      toast.success(sessionNo ? "成績を更新しました" : "成績を登録しました");
      navigate(paths.eventDetail(eventId), { replace: true });
    },
    onError: (err) => {
      if (err instanceof ApiError && getErrorDisplay(err.code) === "inline") {
        toast.error(err.message);
        return;
      }
      handleApiError(err);
    },
  });

  return (
    <div className="p-4">
      {!isAdmin && (
        <p className="text-muted-foreground mb-4 text-sm">
          入力内容はこの場で確認できますが、登録・編集は管理者のみ実行できます。
        </p>
      )}
      <Form {...form}>
        <form
          onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
          className="grid gap-6"
        >
          <FormField
            control={form.control}
            name="gameType"
            render={({ field }) => (
              <FormItem>
                <FormLabel>ゲーム種別</FormLabel>
                <div className="flex gap-2">
                  {GAME_TYPES.map((gameType) => (
                    <Button
                      key={gameType}
                      type="button"
                      variant={field.value === gameType ? "default" : "outline"}
                      onClick={() => field.onChange(gameType)}
                    >
                      {GAME_TYPE_LABELS[gameType]}
                    </Button>
                  ))}
                </div>
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="calcMode"
            render={({ field }) => (
              <FormItem>
                <FormLabel>計算方法</FormLabel>
                <div className="flex gap-2">
                  {CALC_MODES.map((mode) => (
                    <Button
                      key={mode.value}
                      type="button"
                      variant={field.value === mode.value ? "default" : "outline"}
                      onClick={() => field.onChange(mode.value)}
                    >
                      {mode.label}
                    </Button>
                  ))}
                </div>
              </FormItem>
            )}
          />

          {calcMode === "AUTO" && (
            <div className="flex flex-col gap-3 rounded-lg border p-3">
              <div className="flex gap-2">
                <FormField
                  control={form.control}
                  name="startingPoints"
                  render={({ field }) => (
                    <FormItem className="flex-1">
                      <FormLabel className="text-xs">配給原点</FormLabel>
                      <FormControl>
                        <Input type="number" {...field} value={field.value as number} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="returnPoints"
                  render={({ field }) => (
                    <FormItem className="flex-1">
                      <FormLabel className="text-xs">返し点</FormLabel>
                      <FormControl>
                        <Input type="number" {...field} value={field.value as number} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
              <div>
                <p className="mb-1 text-xs font-medium">着順ごとのウマ</p>
                <div className="flex gap-2">
                  {rows.map((_, index) => (
                    <FormField
                      key={index}
                      control={form.control}
                      name={`umaByRank.${index}`}
                      render={({ field }) => (
                        <FormItem className="flex-1">
                          <FormLabel className="text-xs">{index + 1}位</FormLabel>
                          <FormControl>
                            <Input type="number" {...field} value={field.value as number} />
                          </FormControl>
                        </FormItem>
                      )}
                    />
                  ))}
                </div>
              </div>
            </div>
          )}

          <div>
            <p className="mb-2 text-sm font-medium">点数</p>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="min-w-20">項目</TableHead>
                    {rows.map((r) => (
                      <TableHead key={r.userId} className="min-w-24">
                        {r.nickname}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <TableRow>
                    <TableCell className="font-medium">点数</TableCell>
                    {rows.map((r, index) => (
                      <TableCell key={r.userId}>
                        <FormField
                          control={form.control}
                          name={`rows.${index}.score`}
                          render={({ field }) => (
                            <Input type="number" {...field} value={field.value as number} />
                          )}
                        />
                      </TableCell>
                    ))}
                  </TableRow>
                </TableBody>
              </Table>
            </div>
            {scoreMismatch && (
              <p className="mt-2 text-sm text-amber-600">
                点数の合計が配給原点×人数と一致していません。入力内容をご確認ください（登録は可能です）。
              </p>
            )}
          </div>

          {calcMode === "AUTO" && (
            <div>
              <p className="mb-2 text-sm font-medium">計算結果（プレビュー）</p>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="min-w-20">項目</TableHead>
                      {liveResults.map((r) => (
                        <TableHead key={r.userId} className="min-w-24">
                          {r.nickname}
                        </TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    <TableRow>
                      <TableCell className="font-medium">着順</TableCell>
                      {liveResults.map((r) => (
                        <TableCell key={r.userId}>{r.rank}位</TableCell>
                      ))}
                    </TableRow>
                    <TableRow>
                      <TableCell className="font-medium">ポイント</TableCell>
                      {liveResults.map((r) => (
                        <TableCell key={r.userId}>{r.rankPoints}</TableCell>
                      ))}
                    </TableRow>
                  </TableBody>
                </Table>
              </div>
            </div>
          )}

          <div>
            <p className="mb-2 text-sm font-medium">チップ（任意・成績集計とは別枠）</p>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="min-w-20">項目</TableHead>
                    {rows.map((r) => (
                      <TableHead key={r.userId} className="min-w-24">
                        {r.nickname}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <TableRow>
                    <TableCell className="font-medium">チップ枚数</TableCell>
                    {rows.map((r, index) => (
                      <TableCell key={r.userId}>
                        <FormField
                          control={form.control}
                          name={`rows.${index}.chipCount`}
                          render={({ field }) => (
                            <Input type="number" {...field} value={field.value as number} />
                          )}
                        />
                      </TableCell>
                    ))}
                  </TableRow>
                </TableBody>
              </Table>
            </div>
          </div>

          {isAdmin && (
            <Button type="submit" disabled={mutation.isPending}>
              {sessionNo ? "更新する" : "登録する"}
            </Button>
          )}
        </form>
      </Form>
    </div>
  );
}
