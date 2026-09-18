import { useQuery } from "@tanstack/react-query";
import { draftKeys, getDraft, listDraftPlayers } from "@/features/draft/api";
import { isDraftActive } from "@/features/draft/types";

/**
 * ドラフトの状態をポーリングで追う（docs/draft/DESIGN.md §4.12）。
 *
 * WebSocketは使わない。10人×30分・年1回のイベントなので、2.5秒間隔の
 * ポーリングで十分だと判断した。進行が終わった（SETUP/COMPLETED）状態では
 * ポーリングを止める。
 */
const POLL_INTERVAL_MS = 2500;

export function useDraftDetail(draftId: string | undefined) {
  return useQuery({
    queryKey: draftKeys.detail(draftId!),
    queryFn: () => getDraft(draftId!),
    enabled: !!draftId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && isDraftActive(status) ? POLL_INTERVAL_MS : false;
    },
  });
}

/**
 * 指名対象の選手一覧。誰が確保済みかはドラフトの進行で変わるため、
 * 状態が変わるたびに取り直す（呼び出し側がdraft.versionをキーに入れる）。
 */
export function useDraftPlayers(draftId: string | undefined, version: number | undefined) {
  return useQuery({
    queryKey: [...draftKeys.players(draftId!), version] as const,
    queryFn: () => listDraftPlayers(draftId!),
    enabled: !!draftId && version !== undefined,
  });
}
