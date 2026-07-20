import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
  formatScoreMismatch,
  scoreMismatchDiff,
  sortByTieOrder,
} from "@/features/result/calc";
import type {
  CalcMode,
  GameSessionDetail,
  LastGameSettings,
  TobiAssignment,
} from "@/features/result/types";
import { GAME_TYPE_LABELS, type GameType } from "@/features/user/types";
import { useApiErrorToast } from "@/components/feedback/useApiErrorToast";
import { getErrorDisplay, ApiError } from "@/api/errors";
import { paths } from "@/routes/paths";
import { cn } from "@/lib/utils";

/** 着順ごとのバッジ配色（色だけに頼らず数字自体も表示する）。 */
const RANK_BADGE_STYLES: Record<number, string> = {
  1: "border-amber-300 bg-amber-100 text-amber-800",
  2: "border-slate-300 bg-slate-100 text-slate-700",
  3: "border-orange-300 bg-orange-100 text-orange-800",
};
const RANK_BADGE_FALLBACK = "border-blue-200 bg-blue-50 text-blue-700";

function rankBadgeClass(rank: number): string {
  return RANK_BADGE_STYLES[rank] ?? RANK_BADGE_FALLBACK;
}

const GAME_TYPES: GameType[] = ["MAHJONG4", "MAHJONG3"];
const CALC_MODES: { value: CalcMode; label: string }[] = [
  { value: "AUTO", label: "自動計算（ウマ・オカ）" },
  { value: "MANUAL", label: "手動計算（点数のみ）" },
];
/** 箱下精算（Issue #67）: 対局終了時の持ち点がマイナスの場合の扱い。既定は「あり」（従来通りマイナスをそのまま使う）。 */
const BOX_UNDER_SETTLEMENT_OPTIONS: { value: boolean; label: string }[] = [
  { value: true, label: "あり" },
  { value: false, label: "なし（0点切り捨て）" },
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
              <SessionListRow
                key={s.sessionNo}
                eventId={eventId}
                session={s}
                isAdmin={isAdmin}
                nicknameByUserId={nicknameByUserId}
              />
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

/**
 * 登録済み半荘一覧の1行。1半荘=1行で、参加者ごとに着順バッジ＋ポイントを
 * 表示する（着順はサーバー側でscore降順に確定済みのresults配列の並び順）。
 * OWNER/ADMINには編集・削除の導線を出す（削除は確認ダイアログ経由）。
 */
function SessionListRow({
  eventId,
  session,
  isAdmin,
  nicknameByUserId,
}: {
  eventId: string;
  session: GameSessionDetail;
  isAdmin: boolean;
  nicknameByUserId: Map<string, string>;
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
    <div className="flex flex-col gap-1.5 border-b pb-2 last:border-b-0 last:pb-0">
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
      </div>
      <div className="flex gap-1.5 overflow-x-auto">
        {session.results.map((r) => (
          <div
            key={r.userId}
            className={cn(
              "flex min-w-16 shrink-0 flex-col items-center gap-0.5 rounded-md border px-2 py-1",
              rankBadgeClass(r.rank),
            )}
          >
            <span className="max-w-16 truncate text-[11px]">
              {nicknameByUserId.get(r.userId) ?? r.userId}
            </span>
            <span className="text-sm font-semibold">{r.rank}位</span>
            {session.calcMode === "AUTO" && (
              <span className="text-[11px]">{r.rankPoints}pt</span>
            )}
          </div>
        ))}
      </div>
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
  boxUnderSettlement: z.boolean(),
  tobiPoints: z.coerce.number().int().min(0),
  rows: z.array(hanchanRowSchema).min(1),
});
type HanchanFormInput = z.input<typeof hanchanSchema>;
type HanchanFormValues = z.output<typeof hanchanSchema>;

/** ゲーム種別ごとのデフォルト配給原点/返し点（Issue #64：三麻は四麻と異なる）。 */
const DEFAULT_POINTS_BY_GAME_TYPE: Record<
  GameType,
  { startingPoints: number; returnPoints: number }
> = {
  MAHJONG4: { startingPoints: 25000, returnPoints: 30000 },
  MAHJONG3: { startingPoints: 35000, returnPoints: 40000 },
};

function buildHanchanDefaults(
  rows: { userId: string; nickname: string }[],
  lastSettings: LastGameSettings | undefined,
): HanchanFormInput {
  const base = lastSettings?.found
    ? {
        gameType: lastSettings.gameType,
        calcMode: lastSettings.calcMode,
        startingPoints:
          lastSettings.startingPoints ??
          DEFAULT_POINTS_BY_GAME_TYPE[lastSettings.gameType].startingPoints,
        returnPoints:
          lastSettings.returnPoints ??
          DEFAULT_POINTS_BY_GAME_TYPE[lastSettings.gameType].returnPoints,
        umaByRank: lastSettings.umaByRank ?? [0, 0, 0, 0],
        boxUnderSettlement: lastSettings.boxUnderSettlement ?? true,
        tobiPoints: lastSettings.tobiPoints ?? 0,
      }
    : {
        gameType: "MAHJONG4" as GameType,
        calcMode: "AUTO" as CalcMode,
        ...DEFAULT_POINTS_BY_GAME_TYPE.MAHJONG4,
        umaByRank: [0, 0, 0, 0],
        boxUnderSettlement: true,
        tobiPoints: 0,
      };
  // 参加者選択チェックボックスの初期値（左詰めで対象人数分）と揃える。
  const defaultParticipantIds = new Set(
    rows.slice(0, expectedPlayerCount(base.gameType)).map((r) => r.userId),
  );
  return {
    gameType: base.gameType,
    calcMode: base.calcMode,
    startingPoints: base.startingPoints,
    returnPoints: base.returnPoints,
    boxUnderSettlement: base.boxUnderSettlement,
    tobiPoints: base.tobiPoints,
    umaByRank: [0, 1, 2, 3].map((i) => base.umaByRank[i] ?? 0),
    rows: rows.map((r) => ({
      userId: r.userId,
      nickname: r.nickname,
      // 自動計算モードでは、参加者としてデフォルトで選ばれている人の点数欄に
      // 配給原点をあらかじめ入力しておく（手動計算モードでは空欄のまま）。
      score: base.calcMode === "AUTO" && defaultParticipantIds.has(r.userId) ? base.startingPoints : "",
      chipCount: 0,
    })),
  };
}

/**
 * イベント参加者全員をカラムとして常時表示する。参加者数がゲーム種別の対象人数
 * （四麻=4人・三麻=3人）以下ならその半荘の参加者は全員固定、対象人数を超える
 * 場合のみ参加者選択チェックボックスを表示し、対象人数ぶんだけ選べるようにする。
 * 送信後は画面遷移せず点数欄だけをクリアして、続けて次の半荘を入力できるようにする。
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

  const defaultValues = buildHanchanDefaults(rows, lastSettings);
  const form = useForm<HanchanFormInput, unknown, HanchanFormValues>({
    resolver: zodResolver(hanchanSchema),
    defaultValues,
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
  const boxUnderSettlement = form.watch("boxUnderSettlement");
  const tobiPoints = form.watch("tobiPoints");
  /**
   * 飛び賞（Issue #66）: 誰がトビになったか（点数<0）はここで機械的に検知
   * できるが、誰がトビにしたか（受取人）は最終スコアだけからは分からない
   * ため、bustedUserId -> receiverUserIdの対応を管理者に選んでもらう。
   * 半荘ごとの実データのため、点数欄・参加者選択と同じくuseStateで管理し
   * （lastSettingsからは引き継がない）、次の半荘に進む際にリセットする。
   */
  const [tobiCredits, setTobiCredits] = useState<Record<string, string>>({});

  const expectedCount = expectedPlayerCount(gameType);
  const needsSelection = rows.length > expectedCount;
  /** 参加者数が対象人数を超える場合のみ使う、この半荘に参加するメンバーの選択状態。 */
  const [selectedUserIds, setSelectedUserIds] = useState<string[]>(() =>
    rows.slice(0, expectedPlayerCount(defaultValues.gameType)).map((r) => r.userId),
  );

  const fillDefaultScore = (userId: string) => {
    if (calcMode !== "AUTO") return;
    const index = rows.findIndex((r) => r.userId === userId);
    if (index === -1) return;
    form.setValue(`rows.${index}.score`, numeric(startingPoints));
  };

  const toggleParticipant = (userId: string) => {
    setSelectedUserIds((prev) => {
      if (prev.includes(userId)) {
        return prev.filter((id) => id !== userId);
      }
      if (prev.length >= expectedCount) {
        // 対象人数に達している場合は追加できない（先に他の人のチェックを外す）
        return prev;
      }
      return [...prev, userId];
    });
    fillDefaultScore(userId);
  };

  /**
   * ゲーム種別が変わったら対象人数も変わるため、選択を左詰めの初期状態に戻す。
   * 配給原点・返し点も、保存済み設定（lastSettings）が無い場合に限り、
   * 切り替え先のゲーム種別のデフォルト値に更新する（Issue #64）。保存済み
   * 設定がある場合はそちらを優先し、値を上書きしない。
   */
  const handleGameTypeChange = (nextGameType: GameType) => {
    form.setValue("gameType", nextGameType);
    setSelectedUserIds(rows.slice(0, expectedPlayerCount(nextGameType)).map((r) => r.userId));
    if (!lastSettings?.found) {
      const defaults = DEFAULT_POINTS_BY_GAME_TYPE[nextGameType];
      form.setValue("startingPoints", defaults.startingPoints);
      form.setValue("returnPoints", defaults.returnPoints);
    }
  };

  /** 手動計算→自動計算に切り替えた瞬間、参加中の全員の点数欄に配給原点を入力する。 */
  const handleCalcModeChange = (nextCalcMode: CalcMode) => {
    form.setValue("calcMode", nextCalcMode);
    if (nextCalcMode === "AUTO") {
      const participantIds = needsSelection ? selectedUserIds : rows.map((r) => r.userId);
      rows.forEach((r, index) => {
        if (participantIds.includes(r.userId)) {
          form.setValue(`rows.${index}.score`, numeric(form.getValues("startingPoints")));
        }
      });
    }
  };

  /**
   * 配給原点欄の値が変更されたら（Issue #65）、自動計算モードかつ参加者
   * として選択されている行のうち、現在「変更前の配給原点と同じ値」に
   * なっている点数欄だけを新しい配給原点の値に追従して更新する。既に
   * 異なる値へ個別入力済みの点数欄は上書きしない。
   */
  const handleStartingPointsChange = (
    e: React.ChangeEvent<HTMLInputElement>,
    fieldOnChange: (e: React.ChangeEvent<HTMLInputElement>) => void,
  ) => {
    const previousStartingPoints = numeric(form.getValues("startingPoints"));
    fieldOnChange(e);
    if (calcMode !== "AUTO") return;
    const nextStartingPoints = numeric(e.target.value);
    const participantIds = needsSelection ? selectedUserIds : rows.map((r) => r.userId);
    rows.forEach((r, index) => {
      if (!participantIds.includes(r.userId)) return;
      if (numeric(form.getValues(`rows.${index}.score`)) === previousStartingPoints) {
        form.setValue(`rows.${index}.score`, nextStartingPoints);
      }
    });
  };

  const participantIds = needsSelection ? selectedUserIds : rows.map((r) => r.userId);
  const filled = watchedRows
    .map((r, index) => ({ ...r, index }))
    .filter((r) => participantIds.includes(r.userId));
  const participantCountWarning = filled.length !== expectedCount;

  /** トビ（点数<0）になっている参加者。飛び賞パネルはこれが1件以上ある時だけ表示する。 */
  const bustedRows = filled.filter((r) => numeric(r.score) < 0);
  const activeTobiAssignments: TobiAssignment[] = bustedRows
    .map((r) => ({ bustedUserId: r.userId, receiverUserId: tobiCredits[r.userId] }))
    .filter((a): a is TobiAssignment => Boolean(a.receiverUserId));

  const liveResults = computeLiveResults(
    filled.map((r) => ({ userId: r.userId, nickname: r.nickname, score: numeric(r.score) })),
    calcMode,
    numeric(startingPoints),
    numeric(returnPoints),
    umaByRank.map(numeric),
    tieOrder,
    {
      boxUnderSettlement,
      tobiPoints: numeric(tobiPoints),
      tobiAssignments: activeTobiAssignments,
    },
  );
  const scoreMismatchAmount =
    calcMode === "AUTO" && filled.length > 0
      ? scoreMismatchDiff(
          filled.map((r) => ({ score: numeric(r.score) })),
          numeric(startingPoints),
        )
      : 0;
  /** 登録直前の確認ダイアログで使う、確定待ちの送信値（不一致が無ければ常にnull）。 */
  const [pendingValues, setPendingValues] = useState<HanchanFormValues | null>(null);

  const mutation = useMutation({
    mutationFn: (values: HanchanFormValues) => {
      const filledValues = values.rows.filter((r) => participantIds.includes(r.userId));
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
              boxUnderSettlement: values.boxUnderSettlement,
              tobiPoints: values.tobiPoints,
              tobiAssignments: activeTobiAssignments,
            }
          : {}),
      };
      return createSession(eventId, input);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: resultKeys.eventSessions(eventId) });
      toast.success("半荘の成績を登録しました。続けて次の半荘を入力できます。");
      // ゲーム種別・計算方法・配給原点は今回の入力値を引き継いだまま、
      // 点数欄と参加者選択だけを次の半荘用にリセットする。
      const currentGameType = form.getValues("gameType");
      const currentCalcMode = form.getValues("calcMode");
      const currentStartingPoints = form.getValues("startingPoints");
      const nextSelected = rows
        .slice(0, expectedPlayerCount(currentGameType))
        .map((r) => r.userId);
      form.setValue(
        "rows",
        rows.map((r) => ({
          userId: r.userId,
          nickname: r.nickname,
          score:
            currentCalcMode === "AUTO" && nextSelected.includes(r.userId)
              ? currentStartingPoints
              : "",
          chipCount: 0,
        })),
      );
      setTieOrder(rows.map((r) => r.userId));
      setSelectedUserIds(nextSelected);
      // 飛び賞の受取人選択は半荘ごとの実データのため次の半荘には引き継がない。
      setTobiCredits({});
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
    if (participantIds.length === 0) {
      toast.error("少なくとも1人分の点数を入力してください");
      return;
    }
    const missingScore = values.rows.some(
      (r) => participantIds.includes(r.userId) && !isFilledScore(r.score),
    );
    if (missingScore) {
      toast.error("参加者として選ばれている人の点数が未入力です");
      return;
    }
    if (scoreMismatchAmount !== 0) {
      setPendingValues(values);
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
                      onClick={() => handleGameTypeChange(gt)}
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
                      onClick={() => handleCalcModeChange(mode.value)}
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
                        <Input
                          type="number"
                          {...field}
                          value={field.value as number}
                          onChange={(e) => handleStartingPointsChange(e, field.onChange)}
                        />
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
              <FormField
                control={form.control}
                name="boxUnderSettlement"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="text-xs">箱下精算</FormLabel>
                    <div className="flex gap-2">
                      {BOX_UNDER_SETTLEMENT_OPTIONS.map((opt) => (
                        <Button
                          key={String(opt.value)}
                          type="button"
                          variant={field.value === opt.value ? "default" : "outline"}
                          onClick={() => field.onChange(opt.value)}
                        >
                          {opt.label}
                        </Button>
                      ))}
                    </div>
                  </FormItem>
                )}
              />
            </div>
          )}

          {calcMode === "AUTO" && bustedRows.length > 0 && (
            <div className="flex flex-col gap-3 rounded-lg border p-3">
              <FormField
                control={form.control}
                name="tobiPoints"
                render={({ field }) => (
                  <FormItem className="max-w-40">
                    <FormLabel className="text-xs">飛び賞（1件あたりのポイント）</FormLabel>
                    <FormControl>
                      <Input type="number" min={0} {...field} value={field.value as number} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <div className="flex flex-col gap-2">
                {bustedRows.map((busted) => (
                  <div key={busted.userId} className="flex items-center gap-2 text-sm">
                    <span className="min-w-28">{busted.nickname}をトビにした人</span>
                    <Select
                      value={tobiCredits[busted.userId] ?? ""}
                      onValueChange={(value) =>
                        setTobiCredits((prev) => ({ ...prev, [busted.userId]: value ?? "" }))
                      }
                    >
                      <SelectTrigger className="w-32">
                        <SelectValue placeholder="未選択" />
                      </SelectTrigger>
                      <SelectContent>
                        {filled
                          .filter((p) => p.userId !== busted.userId)
                          .map((p) => (
                            <SelectItem key={p.userId} value={p.userId}>
                              {p.nickname}
                            </SelectItem>
                          ))}
                      </SelectContent>
                    </Select>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div>
            <p className="mb-1 text-sm font-medium">点数</p>
            <p className="text-muted-foreground mb-2 text-xs">
              {needsSelection
                ? `この半荘に参加した${expectedCount}人にチェックを入れて点数を入力してください。`
                : `この半荘の参加者${rows.length}人分の点数を入力してください。`}
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
                  {needsSelection && (
                    <TableRow>
                      <TableCell className="font-medium">参加</TableCell>
                      {rows.map((r) => {
                        const checked = selectedUserIds.includes(r.userId);
                        return (
                          <TableCell key={r.userId}>
                            <Checkbox
                              checked={checked}
                              onCheckedChange={() => toggleParticipant(r.userId)}
                              disabled={!checked && selectedUserIds.length >= expectedCount}
                            />
                          </TableCell>
                        );
                      })}
                    </TableRow>
                  )}
                  <TableRow>
                    <TableCell className="font-medium">点数</TableCell>
                    {rows.map((r, index) => {
                      const isParticipant = participantIds.includes(r.userId);
                      return (
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
                                disabled={needsSelection && !isParticipant}
                              />
                            )}
                          />
                        </TableCell>
                      );
                    })}
                  </TableRow>
                </TableBody>
              </Table>
            </div>
            {participantCountWarning && (
              <p className="mt-2 text-sm text-amber-600">
                {needsSelection
                  ? `参加者として選択されている人が${filled.length}人です（${GAME_TYPE_LABELS[gameType]}は${expectedCount}人必要です）。チェックをご確認ください。`
                  : `この半荘の参加者が${filled.length}人です（${GAME_TYPE_LABELS[gameType]}は${expectedCount}人必要です）。入力内容をご確認ください（登録は可能です）。`}
              </p>
            )}
            {scoreMismatchAmount !== 0 && (
              <p className="mt-2 text-sm text-amber-600">
                点数の合計が配給原点×人数と{formatScoreMismatch(scoreMismatchAmount)}です。入力内容をご確認ください（登録は可能です）。
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

      <AlertDialog
        open={pendingValues !== null}
        onOpenChange={(open) => {
          if (!open) setPendingValues(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>点数の合計が配給原点と一致していません</AlertDialogTitle>
            <AlertDialogDescription>
              点数の合計が配給原点×人数と
              {pendingValues && formatScoreMismatch(scoreMismatchAmount)}
              です。本当によろしいですか？
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>キャンセル</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (pendingValues) mutation.mutate(pendingValues);
                setPendingValues(null);
              }}
            >
              登録する
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
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
  calcMode: z.enum(["AUTO", "MANUAL"]),
  startingPoints: z.coerce.number().int(),
  returnPoints: z.coerce.number().int(),
  umaByRank: z.array(z.coerce.number().int()),
  boxUnderSettlement: z.boolean(),
  tobiPoints: z.coerce.number().int().min(0),
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
      calcMode: existingSession.calcMode,
      startingPoints: existingSession.startingPoints ?? 25000,
      returnPoints: existingSession.returnPoints ?? 30000,
      umaByRank: rows.map((_, i) => existingSession.umaByRank?.[i] ?? 0),
      boxUnderSettlement: existingSession.boxUnderSettlement ?? true,
      tobiPoints: existingSession.tobiPoints ?? 0,
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
  const boxUnderSettlement = form.watch("boxUnderSettlement");
  const tobiPoints = form.watch("tobiPoints");
  /** 飛び賞の受取人選択（Issue #66）。既存の登録内容があればそれを初期値にする。 */
  const [tobiCredits, setTobiCredits] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      (existingSession.tobiAssignments ?? []).map((a) => [a.bustedUserId, a.receiverUserId]),
    ),
  );
  const bustedRows = watchedRows.filter((r) => numeric(r.score) < 0);
  const activeTobiAssignments: TobiAssignment[] = bustedRows
    .map((r) => ({ bustedUserId: r.userId, receiverUserId: tobiCredits[r.userId] }))
    .filter((a): a is TobiAssignment => Boolean(a.receiverUserId));

  const liveResults = computeLiveResults(
    watchedRows.map((r) => ({ userId: r.userId, nickname: r.nickname, score: numeric(r.score) })),
    calcMode,
    numeric(startingPoints),
    numeric(returnPoints),
    umaByRank.map(numeric),
    tieOrder,
    {
      boxUnderSettlement,
      tobiPoints: numeric(tobiPoints),
      tobiAssignments: activeTobiAssignments,
    },
  );
  const scoreMismatchAmount =
    calcMode === "AUTO"
      ? scoreMismatchDiff(
          watchedRows.map((r) => ({ score: numeric(r.score) })),
          numeric(startingPoints),
        )
      : 0;
  /** 登録直前の確認ダイアログで使う、確定待ちの送信値（不一致が無ければ常にnull）。 */
  const [pendingValues, setPendingValues] = useState<SessionEditFormValues | null>(null);

  const mutation = useMutation({
    mutationFn: (values: SessionEditFormValues) => {
      const orderedResults = sortByTieOrder(
        values.rows.map((r) => ({ userId: r.userId, score: r.score })),
        tieOrder,
      );
      const input = {
        gameType: existingSession.gameType,
        calcMode: values.calcMode,
        results: orderedResults,
        chips: values.rows.map((r) => ({ userId: r.userId, chipCount: r.chipCount })),
        ...(values.calcMode === "AUTO"
          ? {
              startingPoints: values.startingPoints,
              returnPoints: values.returnPoints,
              umaByRank: values.umaByRank,
              boxUnderSettlement: values.boxUnderSettlement,
              tobiPoints: values.tobiPoints,
              tobiAssignments: activeTobiAssignments,
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

  const onSubmit = (values: SessionEditFormValues) => {
    if (scoreMismatchAmount !== 0) {
      setPendingValues(values);
      return;
    }
    mutation.mutate(values);
  };

  return (
    <div>
      {!isAdmin && (
        <p className="text-muted-foreground mb-4 text-sm">
          入力内容はこの場で確認できますが、登録・編集は管理者のみ実行できます。
        </p>
      )}
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="grid gap-6">
          <FormItem>
            <FormLabel>ゲーム種別</FormLabel>
            <p className="text-sm">
              {GAME_TYPE_LABELS[existingSession.gameType]}（編集できません。人数や顔ぶれが変わる場合は新しい対局として登録してください）
            </p>
          </FormItem>

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
              <FormField
                control={form.control}
                name="boxUnderSettlement"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="text-xs">箱下精算</FormLabel>
                    <div className="flex gap-2">
                      {BOX_UNDER_SETTLEMENT_OPTIONS.map((opt) => (
                        <Button
                          key={String(opt.value)}
                          type="button"
                          variant={field.value === opt.value ? "default" : "outline"}
                          onClick={() => field.onChange(opt.value)}
                        >
                          {opt.label}
                        </Button>
                      ))}
                    </div>
                  </FormItem>
                )}
              />
            </div>
          )}

          {calcMode === "AUTO" && bustedRows.length > 0 && (
            <div className="flex flex-col gap-3 rounded-lg border p-3">
              <FormField
                control={form.control}
                name="tobiPoints"
                render={({ field }) => (
                  <FormItem className="max-w-40">
                    <FormLabel className="text-xs">飛び賞（1件あたりのポイント）</FormLabel>
                    <FormControl>
                      <Input type="number" min={0} {...field} value={field.value as number} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <div className="flex flex-col gap-2">
                {bustedRows.map((busted) => (
                  <div key={busted.userId} className="flex items-center gap-2 text-sm">
                    <span className="min-w-28">{busted.nickname}をトビにした人</span>
                    <Select
                      value={tobiCredits[busted.userId] ?? ""}
                      onValueChange={(value) =>
                        setTobiCredits((prev) => ({ ...prev, [busted.userId]: value ?? "" }))
                      }
                    >
                      <SelectTrigger className="w-32">
                        <SelectValue placeholder="未選択" />
                      </SelectTrigger>
                      <SelectContent>
                        {rows
                          .filter((p) => p.userId !== busted.userId)
                          .map((p) => (
                            <SelectItem key={p.userId} value={p.userId}>
                              {p.nickname}
                            </SelectItem>
                          ))}
                      </SelectContent>
                    </Select>
                  </div>
                ))}
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
            {scoreMismatchAmount !== 0 && (
              <p className="mt-2 text-sm text-amber-600">
                点数の合計が配給原点×人数と{formatScoreMismatch(scoreMismatchAmount)}です。入力内容をご確認ください（登録は可能です）。
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

      <AlertDialog
        open={pendingValues !== null}
        onOpenChange={(open) => {
          if (!open) setPendingValues(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>点数の合計が配給原点と一致していません</AlertDialogTitle>
            <AlertDialogDescription>
              点数の合計が配給原点×人数と
              {pendingValues && formatScoreMismatch(scoreMismatchAmount)}
              です。本当によろしいですか？
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>キャンセル</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (pendingValues) mutation.mutate(pendingValues);
                setPendingValues(null);
              }}
            >
              更新する
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
