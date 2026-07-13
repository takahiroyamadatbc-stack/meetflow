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
    # Lambda設計書v1.1 §6.2 documents these without a communityId segment
    # (`PUT/DELETE /event-templates/{templateId}`); corrected here since
    # EventTemplate has no GSI to resolve templateId -> communityId
    # (see handlers/event_templates.py docstrings).
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
        "GET",
        "/communities/{communityId}/matching/candidates",
    ): matching.list_candidates,
    ("GET", "/matching/candidates/{candidateId}"): matching.get_candidate_detail,
}


def handler(event, context):
    # EventBridge events (§6.7 EventConfirmed subscription) carry
    # `detail-type`/`source`, never `httpMethod`.
    if "detail-type" in event:
        return conflict_detection.handle_event_confirmed(event)
    return dispatch(_ROUTES, event)
