/**
 * Mリーグドラフト企画の型（docs/draft/DESIGN.md）。
 * バックエンドは本体とは別のAPI Gateway（MeetFlowDraftStackのDraftApi）に立つ
 * ため、既存featureの型とは独立している。
 */

/** ドラフトの進行状態（DESIGN.md §4.2） */
export type DraftStatus = "SETUP" | "NOMINATING" | "REVEAL" | "LOTTERY" | "COMPLETED";

export const DRAFT_STATUS_LABELS: Record<DraftStatus, string> = {
  SETUP: "開始前",
  NOMINATING: "指名中",
  REVEAL: "開示済み",
  LOTTERY: "抽選済み",
  COMPLETED: "完了",
};

export type DraftSummary = {
  draftId: string;
  communityId: string;
  name: string;
  season: string;
  hostUserId: string;
  status: DraftStatus;
  /** 何巡目か（SETUP時は0） */
  round: number;
  /** その巡の中の再指名回数（DESIGN.md §4.2） */
  wave: number;
  /** 総巡数。4人のチームを編成するので4 */
  rounds: number;
  /** 単調増加のリビジョン番号。ポーリングはこれが変わったかだけ見る（§4.12） */
  version: number;
  participantCount: number;
  femalePlayerCount: number;
  /** 女流余剰枠の残り（DESIGN.md §4.3(b)） */
  femaleSurplusRemaining: number;
  /** レギュラーシーズン終了日（DESIGN.md §4.15）。未設定ならnull */
  regularSeasonEndDate: string | null;
  createdAt: string;
  updatedAt: string;
};

export type DraftParticipant = {
  userId: string;
  displayName: string;
  playerCount: number;
  femaleCount: number;
};

export type RosterEntry = {
  playerId: string;
  playerName: string;
  teamId: string;
  teamName: string;
  isFemale: boolean;
  round: number;
  wave: number;
};

/** userId -> 確定した選手の一覧 */
export type RosterMap = Record<string, RosterEntry[]>;

export type RevealedPick = {
  userId: string;
  playerId: string;
  playerName: string;
  outcome: "PENDING" | "CONFIRMED" | "LOST";
  byProxy: boolean;
};

/**
 * 進行中のwaveの状況。
 * 開示前は他人の指名内容を含まない（DESIGN.md §4.6）。
 */
export type CurrentWave = {
  round: number;
  wave: number;
  /** この巡で指名が必要な人 */
  expectedUserIds: string[];
  submittedUserIds: string[];
  pendingUserIds: string[];
  revealed: boolean;
  /** 開示後のみ。抽選待ちの指名が残っているか */
  lotteryRequired?: boolean;
  /** 開示後のみ */
  picks?: RevealedPick[];
  /** 開示前のみ。自分の指名（押し間違い確認用） */
  myPick?: { playerId: string; playerName: string } | null;
};

export type DraftDetail = DraftSummary & {
  participants: DraftParticipant[];
  rosters: RosterMap;
  currentWave: CurrentWave | null;
};

export type DraftPlayer = {
  playerId: string;
  name: string;
  kana: string | null;
  teamId: string;
  teamName: string;
  isFemale: boolean;
  /** 確保済みなら指名した人のuserId。まだ誰も取っていなければnull */
  takenByUserId: string | null;
};

export type LotteryType = "PLAYER" | "FEMALE_SURPLUS";

export type LotteryRecord = {
  round: number;
  wave: number;
  type: LotteryType;
  playerId: string | null;
  playerName: string | null;
  candidates: string[];
  winnerUserId: string;
  drawnAt: string;
};

export type DraftCreateInput = {
  name: string;
  participantUserIds: string[];
  season?: string;
  regularSeasonEndDate?: string;
};

/** ドラフトが進行中（＝ポーリングを続けるべき状態）か */
export function isDraftActive(status: DraftStatus): boolean {
  return status !== "SETUP" && status !== "COMPLETED";
}

// --- 成績追跡（docs/draft/DESIGN.md §4.8〜§4.10、§4.15） ---

export type StandingPlayer = {
  playerId: string;
  playerName: string;
  teamName: string;
  isFemale: boolean;
  /** レギュラーシーズン終了日までの獲得ポイント合計 */
  points: number;
  /** 出場半荘数 */
  games: number;
};

export type StandingRow = {
  userId: string;
  displayName: string;
  totalPoints: number;
  rank: number;
  players: StandingPlayer[];
};

export type Standings = {
  season: string;
  /** §4.15。未設定ならシーズン全体を集計している */
  regularSeasonEndDate: string | null;
  standings: StandingRow[];
  /** 最後に取得に成功した時刻。§7の「最終更新を必ず出す」 */
  lastUpdatedAt: string | null;
  lastError: string | null;
  lastErrorAt: string | null;
  /** 日別積算と公式の累計が食い違った選手（SCRAPING.md §3の検算） */
  mismatchedPlayers: string[];
  /** 結果側にいて誰のチームにも紐づかなかった名前（表記ゆれの検知用） */
  unmatchedPlayerNames: string[];
  playedGamedayCount: number;
  scheduledGamedayCount: number;
  latestPlayedDate: string | null;
  /** 19:00〜翌2:00か。「対局中」バッジの表示判定にだけ使う（§4.9） */
  inGameWindow: boolean;
  latestConfirmedDate: string | null;
  /** 今日まだ取得していないか（§4.8「取得は1日1回まで」） */
  canRefresh: boolean;
};

export type RefreshResult = {
  refreshed: boolean;
  reason?: string;
  gamedayCount?: number;
  latestPlayedDate?: string | null;
  mismatchedPlayers?: string[];
};

export type ManualResultInput = {
  date: string;
  no: number;
  games: { label: string; rows: { rank: number; name: string; point: number }[] }[];
};
