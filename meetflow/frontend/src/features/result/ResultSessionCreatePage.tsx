import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
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
import { EmptyState } from "@/components/feedback/EmptyState";
import { communityKeys, getCommunity } from "@/features/community/api";
import { eventKeys, getEvent, listParticipants } from "@/features/event/api";
import {
  createSession,
  deleteSession,
  getLastGameSettings,
  listEventSessions,
  resultKeys,
  updateSession,
} from "@/features/result/api";
import {
  aggregateSessionTotals,
  computeLiveResults,
  expectedPlayerCount,
  hasScoreMismatch,
  sortByTieOrder,
} from "@/features/result/calc";
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

function numeric(value: unknown): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

/** 点数欄が未入力（＝この半荘には参加していない）かどうかの判定。 */
function isFilledScore(value: unknown): boolean {
  return value !== undefined && value !== null && String(value).trim() !== "";
}

/**
 * S-21 成績登録・編集画面。
 * - `/events/:eventId/sessions/new`：イベント単位で半荘を1つずつ追加していく画面。
 *   累計成績・登録済み半荘一覧を表示しつつ、その場で次の半荘を続けて入力できる。
 * - `/events/:eventId/sessions/:sessionNo/edit`：登録済みの特定の半荘を編集する画面。
 * 入力（プレビュー含む）はイベント参加者全員が行えるが、実際の登録・編集（送信）は
 * コミュニティのOWNER/ADMINのみ。
 */
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
    enabled: !!eventId,
  });

  const { data: lastSettings } = useQuery({
    queryKey: resultKeys.lastSettings(event?.communityId ?? ""),
    queryFn: () => getLastGameSettings(event!.communityId),
    enabled: !!event?.communityId && !isEdit,
  });

  const isLoading =
    eventLoading || communityLoading || participantsLoading || sessionsLoading;

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4 p-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (!event || !community || !participants || !sessions) {
    return <EmptyState message="情報の取得に失敗しました" />;
  }

  const isAdmin = community.role === "OWNER" || community.role === "ADMIN";
  const nicknameByUserId = new Map(participants.map((p) => [p.userId, p.nickname]));

  if (isEdit) {
    const existingSession = sessions.find((s) => s.sessionNo === sessionNo);
    if (!existingSession) {
      return <EmptyState message="指定した対局が見つかりません" />;
    }
    const rows = existingSession.results.map((r) => ({
      userId: r.userId,
      nickname: nicknameByUserId.get(r.userId) ?? r.userId,
    }));
    return (
      <div className="p-4">
        <SessionEditForm
          eventId={eventId!}
          sessionNo={sessionNo!}
          rows={rows}
          isAdmin={isAdmin}
          existingSession={existingSession}
        />
      </div>
    );
  }

  const rows = participants
    .filter((p) => p.status !== "CANCELLED")
    .map((p) => ({ userId: p.userId, nickname: p.nickname }));

  if (rows.length === 0) {
    return <EmptyState message="対局に参加しているメンバーがいません" />;
  }

  return (
    <EventResultsPage
      eventId={eventId!}
      rows={rows}
      isAdmin={isAdmin}
      sessions={sessions}
      nicknameByUserId={nicknameByUserId}
      lastSettings={lastSettings}
    />
  );
}

/** イベント単位の累計成績・登録済み半荘一覧＋新規半荘の追加フォームをまとめた画面。 */
function EventResultsPage({
  eventId,
  rows,
  isAdmin,
  sessions,
  nicknameByUserId,
  lastSettings,
}: {
  eventId: string;
  rows: { userId: string; nickname: string }[];
  isAdmin: boolean;
  sessions: GameSessionDetail[];
  nicknameByUserId: Map<string, string>;
  lastSettings?: LastGameSettings;
}) {
  const orderedSessions = [...sessions].sort(
    (a, b) => Number(a.sessionNo) - Number(b.sessionNo),
  );
  const sessionsByGameType = GAME_TYPES.map((gt) => ({
    gameType: gt,
    totals: aggregateSessionTotals(
      sessions.filter((s) => s.gameType === gt),
      nicknameByUserId,
    ),
  })).filter((g) => g.totals.length > 0);

  return (
    <div className="flex flex-col gap-6 p-4">
      <div className="flex flex-col gap-4">
        <h2 className="text-base font-semibold">当日の累計成績</h2>
        <p className="text-muted-foreground -mt-2 text-xs">
          四麻と三麻は着順の定義が異なるため、平均順位は種別ごとに分けて集計しています。
        </p>
        {sessionsByGameType.length === 0 ? (
          <p className="text-muted-foreground text-sm">まだ対局は登録されていません</p>
        ) : (
          sessionsByGameType.map(({ gameType, totals }) => (
            <div key={gameType}>
              <h3 className="mb-2 text-sm font-medium">{GAME_TYPE_LABELS[gameType]}</h3>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>参加者</TableHead>
                      <TableHead>対局数</TableHead>
                      <TableHead>合計ポイント</TableHead>
                      <TableHead>平均順位</TableHead>
                      <TableHead>チップ</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {totals.map((t) => (
                      <TableRow key={t.userId}>
                        <TableCell>{t.nickname}</TableCell>
                        <TableCell>{t.games}</TableCell>
                        <TableCell>{t.totalRankPoints}</TableCell>
                        <TableCell>{t.averageRank}</TableCell>
                        <TableCell>{t.totalChips}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>
          ))
        )}
      </div>

      {orderedSessions.length > 0 && (
        <div>
          <h2 className="mb-2 text-base font-semibold">登録済みの半荘</h2>
          <div className="flex flex-col gap-1">
            {orderedSessions.map((s) => (
              <SessionListRow key={s.sessionNo} eventId={eventId} session={s} isAdmin={isAdmin} />
            ))}
          </div>
        </div>
      )}

      <div>
        <h2 className="mb-2 text-base font-semibold">半荘を追加</h2>
        <HanchanEntryForm eventId={eventId} rows={rows} lastSettings={lastSettings} />
      </div>
    </div>
  );
}

/** 登録済み半荘一覧の1行。OWNER/ADMINには編集・削除の導線を出す（削除は確認ダイアログ経由）。 */
function SessionListRow({
  eventId,
  session,
  isAdmin,
}: {
  eventId: string;
  session: GameSessionDetail;
  isAdmin: boolean;
}) {
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();
  const [confirmOpen, setConfirmOpen] = useState(false);

  const deleteMutation = useMutation({
    mutationFn: () => deleteSession(eventId, session.sessionNo),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: resultKeys.eventSessions(eventId) });
      toast.success("半荘の記録を削除しました");
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
    <div className="flex items-center justify-between text-sm">
      <span>
        対局{Number(session.sessionNo)}（{GAME_TYPE_LABELS[session.gameType]}）
      </span>
      {isAdmin && (
        <div className="flex items-center gap-3">
          <Link to={paths.resultSessionEdit(eventId, session.sessionNo)} className="underline">
            編集
          </Link>
          <button
            type="button"
            className="text-destructive underline"
            onClick={() => setConfirmOpen(true)}
          >
            削除
          </button>
        </div>
      )}
      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              対局{Number(session.sessionNo)}の記録を削除しますか？
            </AlertDialogTitle>
            <AlertDialogDescription>
              この半荘の点数・チップの記録が削除されます。この操作は取り消せません。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>キャンセル</AlertDialogCancel>
            <AlertDialogAction onClick={() => deleteMutation.mutate()}>
              削除する
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

const hanchanRowSchema = z.object({
  userId: z.string(),
  nickname: z.string(),
  score: z.union([z.literal(""), z.coerce.number().int()]),
  chipCount: z.coerce.number().int(),
});

const hanchanSchema = z.object({
  gameType: z.enum(["MAHJONG4", "MAHJONG3"]),
  calcMode: z.enum(["AUTO", "MANUAL"]),
  startingPoints: z.coerce.number().int(),
  returnPoints: z.coerce.number().int(),
  umaByRank: z.array(z.coerce.number().int()),
  rows: z.array(hanchanRowSchema).min(1),
});
type HanchanFormInput = z.input<typeof hanchanSchema>;
type HanchanFormValues = z.output<typeof hanchanSchema>;

function buildHanchanDefaults(
  rows: { userId: string; nickname: string }[],
  lastSettings: LastGameSettings | undefined,
): HanchanFormInput {
  const base = lastSettings?.found
    ? {
        gameType: lastSettings.gameType,
        calcMode: lastSettings.calcMode,
        startingPoints: lastSettings.startingPoints ?? 25000,
        returnPoints: lastSettings.returnPoints ?? 30000,
        umaByRank: lastSettings.umaByRank ?? [0, 0, 0, 0],
      }
    : {
        gameType: "MAHJONG4" as GameType,
        calcMode: "AUTO" as CalcMode,
        startingPoints: 25000,
        returnPoints: 30000,
        umaByRank: [0, 0, 0, 0],
      };
  return {
    gameType: base.gameType,
    calcMode: base.calcMode,
    startingPoints: base.startingPoints,
    returnPoints: base.returnPoints,
    umaByRank: [0, 1, 2, 3].map((i) => base.umaByRank[i] ?? 0),
    rows: rows.map((r) => ({ userId: r.userId, nickname: r.nickname, score: "", chipCount: 0 })),
  };
}

/**
 * イベント参加者全員をカラムとして常時表示し、点数が入力された人だけを
 * その半荘の参加者として扱う（卓の事前選択UIは持たない）。送信後は画面遷移せず
 * 点数欄だけをクリアして、続けて次の半荘を入力できるようにする。
 */
function HanchanEntryForm({
  eventId,
  rows,
  lastSettings,
}: {
  eventId: string;
  rows: { userId: string; nickname: string }[];
  lastSettings?: LastGameSettings;
}) {
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();

  const form = useForm<HanchanFormInput, unknown, HanchanFormValues>({
    resolver: zodResolver(hanchanSchema),
    defaultValues: buildHanchanDefaults(rows, lastSettings),
  });
  /** 点数が同点になった場合の並び順（先頭ほど上位）。既定は参加者一覧の並び順。 */
  const [tieOrder, setTieOrder] = useState<string[]>(() => rows.map((r) => r.userId));
  const swapTieOrder = (userIdA: string, userIdB: string) => {
    setTieOrder((prev) => {
      const next = [...prev];
      const ia = next.indexOf(userIdA);
      const ib = next.indexOf(userIdB);
      if (ia === -1 || ib === -1) return prev;
      [next[ia], next[ib]] = [next[ib], next[ia]];
      return next;
    });
  };

  const calcMode = form.watch("calcMode");
  const gameType = form.watch("gameType");
  const watchedRows = form.watch("rows");
  const startingPoints = form.watch("startingPoints");
  const returnPoints = form.watch("returnPoints");
  const umaByRank = form.watch("umaByRank");

  const expectedCount = expectedPlayerCount(gameType);
  const filled = watchedRows
    .map((r, index) => ({ ...r, index }))
    .filter((r) => isFilledScore(r.score));
  const participantCountWarning = filled.length > expectedCount;

  const liveResults = computeLiveResults(
    filled.map((r) => ({ userId: r.userId, nickname: r.nickname, score: numeric(r.score) })),
    calcMode,
    numeric(startingPoints),
    numeric(returnPoints),
    umaByRank.map(numeric),
    tieOrder,
  );
  const scoreMismatch =
    calcMode === "AUTO" &&
    filled.length > 0 &&
    hasScoreMismatch(
      filled.map((r) => ({ score: numeric(r.score) })),
      numeric(startingPoints),
    );

  const mutation = useMutation({
    mutationFn: (values: HanchanFormValues) => {
      const filledValues = values.rows.filter((r) => isFilledScore(r.score));
      const orderedResults = sortByTieOrder(
        filledValues.map((r) => ({ userId: r.userId, score: r.score as number })),
        tieOrder,
      );
      const input = {
        gameType: values.gameType,
        calcMode: values.calcMode,
        results: orderedResults,
        chips: filledValues.map((r) => ({ userId: r.userId, chipCount: r.chipCount })),
        ...(values.calcMode === "AUTO"
          ? {
              startingPoints: values.startingPoints,
              returnPoints: values.returnPoints,
              umaByRank: values.umaByRank.slice(0, filledValues.length),
            }
          : {}),
      };
      return createSession(eventId, input);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: resultKeys.eventSessions(eventId) });
      toast.success("半荘の成績を登録しました。続けて次の半荘を入力できます。");
      form.setValue(
        "rows",
        rows.map((r) => ({ userId: r.userId, nickname: r.nickname, score: "", chipCount: 0 })),
      );
      setTieOrder(rows.map((r) => r.userId));
    },
    onError: (err) => {
      if (err instanceof ApiError && getErrorDisplay(err.code) === "inline") {
        toast.error(err.message);
        return;
      }
      handleApiError(err);
    },
  });

  const onSubmit = (values: HanchanFormValues) => {
    if (!values.rows.some((r) => isFilledScore(r.score))) {
      toast.error("少なくとも1人分の点数を入力してください");
      return;
    }
    mutation.mutate(values);
  };

  return (
    <div>
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="grid gap-6">
          <FormField
            control={form.control}
            name="gameType"
            render={({ field }) => (
              <FormItem>
                <FormLabel>ゲーム種別</FormLabel>
                <div className="flex gap-2">
                  {GAME_TYPES.map((gt) => (
                    <Button
                      key={gt}
                      type="button"
                      variant={field.value === gt ? "default" : "outline"}
                      onClick={() => field.onChange(gt)}
                    >
                      {GAME_TYPE_LABELS[gt]}
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
                  {Array.from({ length: expectedCount }).map((_, index) => (
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
            <p className="mb-1 text-sm font-medium">点数</p>
            <p className="text-muted-foreground mb-2 text-xs">
              この半荘に実際に参加した{expectedCount}人分だけ点数を入力してください（空欄の人は参加していないものとして扱われます）。
            </p>
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
                            <Input
                              type="number"
                              {...field}
                              value={field.value as number | string}
                              placeholder="不参加"
                            />
                          )}
                        />
                      </TableCell>
                    ))}
                  </TableRow>
                </TableBody>
              </Table>
            </div>
            {participantCountWarning && (
              <p className="mt-2 text-sm text-amber-600">
                点数が入力されている人が{filled.length}人います（{GAME_TYPE_LABELS[gameType]}は
                {expectedCount}人です）。入力内容をご確認ください（登録は可能です）。
              </p>
            )}
            {scoreMismatch && (
              <p className="mt-2 text-sm text-amber-600">
                点数の合計が配給原点×人数と一致していません。入力内容をご確認ください（登録は可能です）。
              </p>
            )}
          </div>

          {calcMode === "AUTO" && filled.length > 0 && (
            <div>
              <p className="mb-2 text-sm font-medium">計算結果（プレビュー）</p>
              {liveResults.some((r, i) => liveResults[i + 1]?.score === r.score) && (
                <p className="text-muted-foreground mb-2 text-xs">
                  同点の場合は「⇄」で順位を入れ替えられます。
                </p>
              )}
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
                      {liveResults.map((r, i) => {
                        const nextTied = liveResults[i + 1]?.score === r.score;
                        return (
                          <TableCell key={r.userId}>
                            <div className="flex items-center gap-1">
                              <span>{r.rank}位</span>
                              {nextTied && (
                                <button
                                  type="button"
                                  className="text-muted-foreground hover:text-foreground text-xs underline"
                                  title="同点者の順位を入れ替える"
                                  onClick={() =>
                                    swapTieOrder(r.userId, liveResults[i + 1].userId)
                                  }
                                >
                                  ⇄
                                </button>
                              )}
                            </div>
                          </TableCell>
                        );
                      })}
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

          {filled.length > 0 && (
            <div>
              <p className="mb-2 text-sm font-medium">チップ（任意・成績集計とは別枠）</p>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="min-w-20">項目</TableHead>
                      {filled.map((r) => (
                        <TableHead key={r.userId} className="min-w-24">
                          {r.nickname}
                        </TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    <TableRow>
                      <TableCell className="font-medium">チップ枚数</TableCell>
                      {filled.map((r) => (
                        <TableCell key={r.userId}>
                          <FormField
                            control={form.control}
                            name={`rows.${r.index}.chipCount`}
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
          )}

          <Button type="submit" disabled={mutation.isPending}>
            この半荘を登録する
          </Button>
        </form>
      </Form>
    </div>
  );
}

const sessionEditRowSchema = z.object({
  userId: z.string(),
  nickname: z.string(),
  score: z.coerce.number().int(),
  chipCount: z.coerce.number().int(),
});

const sessionEditSchema = z.object({
  gameType: z.enum(["MAHJONG4", "MAHJONG3"]),
  calcMode: z.enum(["AUTO", "MANUAL"]),
  startingPoints: z.coerce.number().int(),
  returnPoints: z.coerce.number().int(),
  umaByRank: z.array(z.coerce.number().int()),
  rows: z.array(sessionEditRowSchema).min(1),
});
type SessionEditFormInput = z.input<typeof sessionEditSchema>;
type SessionEditFormValues = z.output<typeof sessionEditSchema>;

/** 登録済みの1半荘を編集する画面。参加者の入れ替えはできない（backendでも拒否される）。 */
function SessionEditForm({
  eventId,
  sessionNo,
  rows,
  isAdmin,
  existingSession,
}: {
  eventId: string;
  sessionNo: string;
  rows: { userId: string; nickname: string }[];
  isAdmin: boolean;
  existingSession: GameSessionDetail;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const handleApiError = useApiErrorToast();

  const scoreByUserId = new Map(existingSession.results.map((r) => [r.userId, r.score]));
  const chipByUserId = new Map(existingSession.chips.map((c) => [c.userId, c.chipCount]));

  const form = useForm<SessionEditFormInput, unknown, SessionEditFormValues>({
    resolver: zodResolver(sessionEditSchema),
    defaultValues: {
      gameType: existingSession.gameType,
      calcMode: existingSession.calcMode,
      startingPoints: existingSession.startingPoints ?? 25000,
      returnPoints: existingSession.returnPoints ?? 30000,
      umaByRank: rows.map((_, i) => existingSession.umaByRank?.[i] ?? 0),
      rows: rows.map((r) => ({
        userId: r.userId,
        nickname: r.nickname,
        score: scoreByUserId.get(r.userId) ?? 0,
        chipCount: chipByUserId.get(r.userId) ?? 0,
      })),
    },
  });
  /** 点数が同点になった場合の並び順（先頭ほど上位）。既定は参加者一覧の並び順。 */
  const [tieOrder, setTieOrder] = useState<string[]>(() => rows.map((r) => r.userId));
  const swapTieOrder = (userIdA: string, userIdB: string) => {
    setTieOrder((prev) => {
      const next = [...prev];
      const ia = next.indexOf(userIdA);
      const ib = next.indexOf(userIdB);
      if (ia === -1 || ib === -1) return prev;
      [next[ia], next[ib]] = [next[ib], next[ia]];
      return next;
    });
  };

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
    tieOrder,
  );
  const scoreMismatch =
    calcMode === "AUTO" &&
    hasScoreMismatch(
      watchedRows.map((r) => ({ score: numeric(r.score) })),
      numeric(startingPoints),
    );

  const mutation = useMutation({
    mutationFn: (values: SessionEditFormValues) => {
      const orderedResults = sortByTieOrder(
        values.rows.map((r) => ({ userId: r.userId, score: r.score })),
        tieOrder,
      );
      const input = {
        gameType: values.gameType,
        calcMode: values.calcMode,
        results: orderedResults,
        chips: values.rows.map((r) => ({ userId: r.userId, chipCount: r.chipCount })),
        ...(values.calcMode === "AUTO"
          ? {
              startingPoints: values.startingPoints,
              returnPoints: values.returnPoints,
              umaByRank: values.umaByRank,
            }
          : {}),
      };
      return updateSession(eventId, sessionNo, input);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: resultKeys.eventSessions(eventId) });
      toast.success("成績を更新しました");
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
    <div>
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
                  {GAME_TYPES.map((gt) => (
                    <Button
                      key={gt}
                      type="button"
                      variant={field.value === gt ? "default" : "outline"}
                      onClick={() => field.onChange(gt)}
                    >
                      {GAME_TYPE_LABELS[gt]}
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
              {liveResults.some((r, i) => liveResults[i + 1]?.score === r.score) && (
                <p className="text-muted-foreground mb-2 text-xs">
                  同点の場合は「⇄」で順位を入れ替えられます。
                </p>
              )}
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
                      {liveResults.map((r, i) => {
                        const nextTied = liveResults[i + 1]?.score === r.score;
                        return (
                          <TableCell key={r.userId}>
                            <div className="flex items-center gap-1">
                              <span>{r.rank}位</span>
                              {nextTied && (
                                <button
                                  type="button"
                                  className="text-muted-foreground hover:text-foreground text-xs underline"
                                  title="同点者の順位を入れ替える"
                                  onClick={() =>
                                    swapTieOrder(r.userId, liveResults[i + 1].userId)
                                  }
                                >
                                  ⇄
                                </button>
                              )}
                            </div>
                          </TableCell>
                        );
                      })}
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
              更新する
            </Button>
          )}
        </form>
      </Form>
    </div>
  );
}
