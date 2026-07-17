from handlers import attachments

from _factories import api_event, body_of


def test_create_attachment_upload_url(table):
    resp = attachments.create_attachment_upload_url(
        "user-1", api_event(body={"contentType": "image/png"})
    )
    assert resp["statusCode"] == 200
    data = body_of(resp)["data"]
    assert data["attachmentKey"].startswith("feedback/user-1/")
    assert data["attachmentKey"].endswith(".png")
    assert data["uploadUrl"].startswith("https://")
    assert data["expiresIn"] == 300


def test_create_attachment_upload_url_rejects_unsupported_content_type(table):
    resp = attachments.create_attachment_upload_url(
        "user-1", api_event(body={"contentType": "application/pdf"})
    )
    assert resp["statusCode"] == 400
    assert body_of(resp)["error"]["code"] == "INVALID_PARAMETER"
