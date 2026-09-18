import { draftApiClient } from "@/api/client";
import type {
  DraftCreateInput,
  DraftDetail,
  DraftPlayer,
  DraftSummary,
  LotteryRecord,
  ManualResultInput,
  RefreshResult,
  RosterMap,
  Standings,
} from "@/features/draft/types";

export const draftKeys = {
  list: (communityId: string) => ["drafts", "community", communityId] as const,
  detail: (draftId: string) => ["drafts", draftId] as const,
  players: (draftId: string) => ["drafts", draftId, "players"] as const,
  rosters: (draftId: string) => ["drafts", draftId, "rosters"] as const,
  lotteries: (draftId: string) => ["drafts", draftId, "lotteries"] as const,
  standings: (draftId: string) => ["drafts", draftId, "standings"] as const,
};

/** POST /communities/{communityId}/drafts */
export function createDraft(communityId: string, input: DraftCreateInput) {
  return draftApiClient.post<DraftSummary>(`/communities/${communityId}/drafts`, input);
}

/** GET /communities/{communityId}/drafts */
export function listDrafts(communityId: string) {
  return draftApiClient
    .get<{ drafts: DraftSummary[] }>(`/communities/${communityId}/drafts`)
    .then((data) => data.drafts);
}

/** GET /drafts/{draftId} — ポーリング先（DESIGN.md §4.12） */
export function getDraft(draftId: string) {
  return draftApiClient.get<DraftDetail>(`/drafts/${draftId}`);
}

/** GET /drafts/{draftId}/players — 指名対象の選手一覧（確保済みフラグ付き） */
export function listDraftPlayers(draftId: string) {
  return draftApiClient
    .get<{ players: DraftPlayer[] }>(`/drafts/${draftId}/players`)
    .then((data) => data.players);
}

/** GET /drafts/{draftId}/rosters */
export function getRosters(draftId: string) {
  return draftApiClient
    .get<{ rosters: RosterMap }>(`/drafts/${draftId}/rosters`)
    .then((data) => data.rosters);
}

/** GET /drafts/{draftId}/lotteries — 抽選の記録（DESIGN.md §4.14） */
export function listLotteries(draftId: string) {
  return draftApiClient
    .get<{ lotteries: LotteryRecord[] }>(`/drafts/${draftId}/lotteries`)
    .then((data) => data.lotteries);
}

/** POST /drafts/{draftId}/start — 主催者 */
export function startDraft(draftId: string) {
  return draftApiClient.post<DraftSummary>(`/drafts/${draftId}/start`);
}

/** POST /drafts/{draftId}/picks */
export function submitPick(draftId: string, playerId: string) {
  return draftApiClient.post<{ playerId: string; playerName: string }>(
    `/drafts/${draftId}/picks`,
    { playerId },
  );
}

/** POST /drafts/{draftId}/picks/proxy — 主催者による代理指名（DESIGN.md §4.7） */
export function submitProxyPick(draftId: string, userId: string, playerId: string) {
  return draftApiClient.post<{ playerId: string; playerName: string }>(
    `/drafts/${draftId}/picks/proxy`,
    { userId, playerId },
  );
}

/** POST /drafts/{draftId}/reveal — 主催者 */
export function revealWave(draftId: string) {
  return draftApiClient.post<DraftSummary & { lotteryRequired: boolean }>(
    `/drafts/${draftId}/reveal`,
  );
}

/** POST /drafts/{draftId}/lottery — 主催者 */
export function runLottery(draftId: string) {
  return draftApiClient.post<DraftSummary & { loserUserIds: string[] }>(
    `/drafts/${draftId}/lottery`,
  );
}

/** POST /drafts/{draftId}/advance — 主催者 */
export function advanceDraft(draftId: string) {
  return draftApiClient.post<DraftSummary>(`/drafts/${draftId}/advance`);
}

// --- 成績追跡（docs/draft/DESIGN.md §4.8〜§4.10） ---

/** GET /drafts/{draftId}/standings */
export function getStandings(draftId: string) {
  return draftApiClient.get<Standings>(`/drafts/${draftId}/standings`);
}

/**
 * POST /drafts/{draftId}/standings/refresh
 *
 * DESIGN.md §4.8: 完全オンデマンド。誰かが押したときだけ公式サイトを取りに行く。
 * 1日1回までで、上限に達している場合は `refreshed: false` が返る（エラーではない）。
 */
export function refreshStandings(draftId: string) {
  return draftApiClient.post<RefreshResult>(`/drafts/${draftId}/standings/refresh`);
}

/**
 * POST /drafts/{draftId}/standings/manual
 *
 * DESIGN.md §7の手動入力フォールバック。公式サイトのHTMLが変わって
 * パースが直らない間も、主催者が打ち込めば集計を続けられる。
 */
export function submitManualResult(draftId: string, input: ManualResultInput) {
  return draftApiClient.post<{ date: string; no: number; gameCount: number }>(
    `/drafts/${draftId}/standings/manual`,
    input,
  );
}
