import type { DraftDetail, DraftParticipant, DraftPlayer } from "@/features/draft/types";

/**
 * 指名ルールの表示側判定（docs/draft/DESIGN.md §4.3）。
 *
 * 最終的な可否はサーバーが決める（同じルールが
 * backend/functions/draft_lambda/handlers/rules.py にある）。ここでの判定は
 * 「押せないボタンを押させない」ためのもので、押してからエラーで弾かれる
 * より先に理由を出すことが目的。
 */

/**
 * §4.3(a) 動的強制: 「残り巡数 ≦ 自分にまだ必要な女性数」になったら女性しか
 * 指名できない。必要な女性数は0か1しかないため、実際に効くのは
 * 「最終巡に入った時点で女性を1人も持っていない」ケースだけ。
 */
export function mustPickFemale(round: number, rounds: number, hasFemale: boolean): boolean {
  const roundsLeft = rounds - round + 1;
  const femalesNeeded = hasFemale ? 0 : 1;
  return roundsLeft <= femalesNeeded;
}

/**
 * §4.3(b) その指名が女流余剰枠を消費するか。
 * 1人目の女性は必要指名であって余剰ではないため消費しない。
 */
export function consumesSurplus(hasFemale: boolean, pickIsFemale: boolean): boolean {
  return hasFemale && pickIsFemale;
}

export type PickBlockReason = "TAKEN" | "FEMALE_REQUIRED" | "SURPLUS_EXHAUSTED";

/** 指名できない理由。指名できるならnull */
export function pickBlockReason(
  player: DraftPlayer,
  {
    round,
    rounds,
    hasFemale,
    femaleSurplusRemaining,
  }: { round: number; rounds: number; hasFemale: boolean; femaleSurplusRemaining: number },
): PickBlockReason | null {
  if (player.takenByUserId) return "TAKEN";
  if (mustPickFemale(round, rounds, hasFemale) && !player.isFemale) return "FEMALE_REQUIRED";
  if (consumesSurplus(hasFemale, player.isFemale) && femaleSurplusRemaining <= 0) {
    return "SURPLUS_EXHAUSTED";
  }
  return null;
}

export const PICK_BLOCK_MESSAGES: Record<PickBlockReason, string> = {
  TAKEN: "すでに指名されています",
  FEMALE_REQUIRED: "この巡は女性選手しか指名できません",
  SURPLUS_EXHAUSTED: "女流枠の余りがありません",
};

/** 自分がこの巡で指名する必要があるか（落選者のみ再指名する§4.2のwave） */
export function needsToPick(draft: DraftDetail, userId: string | null): boolean {
  if (!userId || draft.status !== "NOMINATING" || !draft.currentWave) return false;
  return draft.currentWave.expectedUserIds.includes(userId);
}

/** 自分がこの巡で提出済みか */
export function hasSubmitted(draft: DraftDetail, userId: string | null): boolean {
  if (!userId || !draft.currentWave) return false;
  return draft.currentWave.submittedUserIds.includes(userId);
}

export function findParticipant(
  draft: DraftDetail,
  userId: string | null,
): DraftParticipant | undefined {
  return draft.participants.find((p) => p.userId === userId);
}

/** userId -> 表示名。抽選の候補者表示などで引く */
export function displayNameMap(draft: DraftDetail): Record<string, string> {
  return Object.fromEntries(draft.participants.map((p) => [p.userId, p.displayName]));
}
