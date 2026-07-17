from meetflow_common import dispatch

from handlers import announcements, attachments, feedback

# FeedbackLambda (Lambda設計書v1.7 §9b)。
_ROUTES = {
    ("POST", "/feedback"): feedback.create_feedback,
    ("GET", "/feedback"): feedback.list_feedback,
    ("GET", "/feedback/stats"): feedback.get_feedback_stats,
    ("GET", "/feedback/{feedbackId}"): feedback.get_feedback,
    ("PATCH", "/feedback/{feedbackId}"): feedback.update_feedback,
    ("POST", "/feedback/attachments/presign"): attachments.create_attachment_upload_url,
    ("GET", "/announcements"): announcements.list_announcements,
    ("POST", "/announcements"): announcements.create_announcement,
    ("PUT", "/announcements/{announcementId}"): announcements.update_announcement,
}


def handler(event, context):
    return dispatch(_ROUTES, event)
