import { apiClient } from "@/api/client";
import type {
  Candidate,
  CreateManualCandidateInput,
  EventTemplate,
  EventTemplateInput,
} from "@/features/matching/types";

export const matchingKeys = {
  templates: (communityId: string) => ["communities", communityId, "event-templates"] as const,
  candidates: (communityId: string) => ["communities", communityId, "candidates"] as const,
  candidateDetail: (candidateId: string) => ["candidates", candidateId] as const,
};

/** GET /communities/{communityId}/event-templates */
export function listEventTemplates(communityId: string) {
  return apiClient
    .get<{ templates: EventTemplate[] }>(`/communities/${communityId}/event-templates`)
    .then((data) => data.templates);
}

/** POST /communities/{communityId}/event-templates */
export function createEventTemplate(communityId: string, input: EventTemplateInput) {
  return apiClient.post<EventTemplate>(`/communities/${communityId}/event-templates`, input);
}

/** PUT /communities/{communityId}/event-templates/{templateId} */
export function updateEventTemplate(
  communityId: string,
  templateId: string,
  input: EventTemplateInput,
) {
  return apiClient.put<EventTemplate>(
    `/communities/${communityId}/event-templates/${templateId}`,
    input,
  );
}

/** DELETE /communities/{communityId}/event-templates/{templateId} */
export function deleteEventTemplate(communityId: string, templateId: string) {
  return apiClient.delete(`/communities/${communityId}/event-templates/${templateId}`);
}

/** POST /communities/{communityId}/matching（候補生成の手動実行） */
export function generateCandidates(communityId: string, templateId: string) {
  return apiClient
    .post<{ candidates: Candidate[] }>(`/communities/${communityId}/matching`, { templateId })
    .then((data) => data.candidates);
}

/**
 * POST /communities/{communityId}/matching/candidates/manual（Issue #56）。
 * 開催条件・空き予定収集を経ずに、管理者がメンバー・日時を直接指定して
 * 承認フロー無しの候補を作成する。以降は既存の候補詳細→会場選択→
 * イベント作成のフロー（MatchingCandidateDetailPage）にそのまま乗る。
 */
export function createManualCandidate(communityId: string, input: CreateManualCandidateInput) {
  return apiClient.post<Candidate>(
    `/communities/${communityId}/matching/candidates/manual`,
    input,
  );
}

/** GET /communities/{communityId}/matching/candidates */
export function listCandidates(communityId: string) {
  return apiClient
    .get<{ candidates: Candidate[] }>(`/communities/${communityId}/matching/candidates`)
    .then((data) => data.candidates);
}

/** GET /matching/candidates/{candidateId} */
export function getCandidateDetail(candidateId: string) {
  return apiClient.get<Candidate>(`/matching/candidates/${candidateId}`);
}
