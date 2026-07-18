from meetflow_common import dispatch

from handlers import conflict_detection, event_templates, matching

# MatchingLambda (Lambda設計書v1.1 §6).
_ROUTES = {
    (
        "POST",
        "/communities/{communityId}/event-templates",
    ): event_templates.create_template,
    (
        "GET",
        "/communities/{communityId}/event-templates",
    ): event_templates.list_templates,
    # Lambda設計書v1.1 §6.2ではcommunityIdセグメント無し
    # (`PUT/DELETE /event-templates/{templateId}`)と記載されているが、
    # EventTemplateにはtemplateId -> communityIdを解決するGSIが無いため
    # ここで修正している（handlers/event_templates.pyのdocstring参照）。
    (
        "PUT",
        "/communities/{communityId}/event-templates/{templateId}",
    ): event_templates.update_template,
    (
        "DELETE",
        "/communities/{communityId}/event-templates/{templateId}",
    ): event_templates.delete_template,
    ("POST", "/communities/{communityId}/matching"): matching.generate_candidates,
    (
        "POST",
        "/communities/{communityId}/matching/candidates/manual",
    ): matching.create_manual_candidate,
    (
        "GET",
        "/communities/{communityId}/matching/candidates",
    ): matching.list_candidates,
    ("GET", "/matching/candidates/{candidateId}"): matching.get_candidate_detail,
}


def handler(event, context):
    # EventBridgeイベント（§6.7 EventConfirmed購読）は`detail-type`/
    # `source`を持つが、`httpMethod`は持たない。
    if "detail-type" in event:
        return conflict_detection.handle_event_confirmed(event)
    return dispatch(_ROUTES, event)
