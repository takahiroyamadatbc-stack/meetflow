from unittest.mock import patch

import pytest

from meetflow_common import AuthError

from handlers import feedback

from _factories import api_event, body_of


def test_create_feedback_quick(table):
    resp = feedback.create_feedback(
        "user-1",
        api_event(
            body={
                "kind": "QUICK",
                "relatedFeature": "MATCHING_CANDIDATE_LIST",
                "rating": "GOOD",
            }
        ),
    )
    assert resp["statusCode"] == 201
    data = body_of(resp)["data"]
    assert data["feedbackId"]

    stored = table.get_item(
        Key={"PK": f"FEEDBACK#{data['feedbackId']}", "SK": "METADATA"}
    )["Item"]
    assert stored["userId"] == "user-1"
    assert stored["kind"] == "QUICK"
    assert stored["rating"] == "GOOD"
    assert stored["status"] == "UNHANDLED"
    assert "category" not in stored


def test_create_feedback_detailed_with_attachments(table):
    resp = feedback.create_feedback(
        "user-1",
        api_event(
            body={
                "kind": "DETAILED",
                "relatedFeature": "EVENT_DETAIL",
                "category": "BUG",
                "content": "詳細内容です",
                "attachmentKeys": ["feedback/user-1/a.png"],
            }
        ),
    )
    assert resp["statusCode"] == 201
    data = body_of(resp)["data"]

    stored = table.get_item(
        Key={"PK": f"FEEDBACK#{data['feedbackId']}", "SK": "METADATA"}
    )["Item"]
    assert stored["category"] == "BUG"
    assert stored["content"] == "詳細内容です"
    assert stored["attachmentKeys"] == {"feedback/user-1/a.png"}
    assert "rating" not in stored


def test_create_feedback_invalid_kind(table):
    resp = feedback.create_feedback(
        "user-1", api_event(body={"kind": "BOGUS", "relatedFeature": "X"})
    )
    assert resp["statusCode"] == 400
    assert body_of(resp)["error"]["code"] == "FEEDBACK_VALIDATION_ERROR"


def test_create_feedback_quick_missing_rating(table):
    resp = feedback.create_feedback(
        "user-1",
        api_event(body={"kind": "QUICK", "relatedFeature": "MATCHING_CANDIDATE_LIST"}),
    )
    assert resp["statusCode"] == 400
    assert body_of(resp)["error"]["code"] == "FEEDBACK_VALIDATION_ERROR"


def test_create_feedback_detailed_missing_category(table):
    resp = feedback.create_feedback(
        "user-1", api_event(body={"kind": "DETAILED", "relatedFeature": "EVENT_DETAIL"})
    )
    assert resp["statusCode"] == 400
    assert body_of(resp)["error"]["code"] == "FEEDBACK_VALIDATION_ERROR"


def test_list_feedback_requires_operator(table):
    with pytest.raises(AuthError) as exc_info:
        feedback.list_feedback("user-1", api_event(groups=["MEMBER"]))
    assert exc_info.value.code == "FORBIDDEN"


def test_list_feedback_returns_items_newest_first(table):
    feedback.create_feedback(
        "user-1",
        api_event(
            body={"kind": "QUICK", "relatedFeature": "A", "rating": "BAD"}
        ),
    )
    feedback.create_feedback(
        "user-2",
        api_event(
            body={"kind": "QUICK", "relatedFeature": "B", "rating": "GOOD"}
        ),
    )

    resp = feedback.list_feedback("op-1", api_event(groups=["Operators"]))
    assert resp["statusCode"] == 200
    items = body_of(resp)["data"]["feedbacks"]
    assert len(items) == 2
    assert items[0]["relatedFeature"] == "B"  # newest first


def test_list_feedback_filters_by_status(table):
    create_resp = feedback.create_feedback(
        "user-1",
        api_event(
            body={
                "kind": "DETAILED",
                "relatedFeature": "A",
                "category": "BUG",
                "content": "x",
            }
        ),
    )
    feedback_id = body_of(create_resp)["data"]["feedbackId"]
    feedback.update_feedback(
        "op-1",
        api_event(
            path_params={"feedbackId": feedback_id},
            body={"status": "PLANNED"},
            groups=["Operators"],
        ),
    )
    feedback.create_feedback(
        "user-2",
        api_event(
            body={
                "kind": "DETAILED",
                "relatedFeature": "B",
                "category": "UX_IMPROVEMENT",
                "content": "y",
            }
        ),
    )

    resp = feedback.list_feedback(
        "op-1", api_event(query={"status": "PLANNED"}, groups=["Operators"])
    )
    items = body_of(resp)["data"]["feedbacks"]
    assert len(items) == 1
    assert items[0]["feedbackId"] == feedback_id


def test_get_feedback_not_found(table):
    resp = feedback.get_feedback(
        "op-1", api_event(path_params={"feedbackId": "missing"}, groups=["Operators"])
    )
    assert resp["statusCode"] == 404
    assert body_of(resp)["error"]["code"] == "FEEDBACK_NOT_FOUND"


def test_update_feedback_reply_publishes_event(table):
    create_resp = feedback.create_feedback(
        "user-1",
        api_event(
            body={"kind": "QUICK", "relatedFeature": "A", "rating": "NEUTRAL"}
        ),
    )
    feedback_id = body_of(create_resp)["data"]["feedbackId"]

    with patch.object(feedback, "put_event") as mock_put_event:
        resp = feedback.update_feedback(
            "op-1",
            api_event(
                path_params={"feedbackId": feedback_id},
                body={"status": "DONE", "priority": "HIGH", "reply": "対応しました"},
                groups=["Operators"],
            ),
        )
    assert resp["statusCode"] == 200
    mock_put_event.assert_called_once()
    detail_type, detail = mock_put_event.call_args[0]
    assert detail_type == "FeedbackReplied"
    assert detail["feedbackId"] == feedback_id
    assert detail["targetUserId"] == "user-1"

    stored = table.get_item(
        Key={"PK": f"FEEDBACK#{feedback_id}", "SK": "METADATA"}
    )["Item"]
    assert stored["status"] == "DONE"
    assert stored["priority"] == "HIGH"
    assert stored["reply"]["message"] == "対応しました"
    assert stored["reply"]["repliedBy"] == "op-1"


def test_get_feedback_stats_aggregates(table):
    for i in range(2):
        create_resp = feedback.create_feedback(
            f"user-{i}",
            api_event(
                body={
                    "kind": "DETAILED",
                    "relatedFeature": "A",
                    "category": "BUG",
                    "content": "x",
                }
            ),
        )
        feedback_id = body_of(create_resp)["data"]["feedbackId"]
        feedback.update_feedback(
            "op-1",
            api_event(
                path_params={"feedbackId": feedback_id},
                body={"priority": "LOW"},
                groups=["Operators"],
            ),
        )

    resp = feedback.get_feedback_stats("op-1", api_event(groups=["Operators"]))
    data = body_of(resp)["data"]
    assert data["byCategory"] == {"BUG": 2}
    assert data["byStatus"] == {"UNHANDLED": 2}
    assert data["byPriority"] == {"LOW": 2}
