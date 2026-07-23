import base64
import json

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

    # Issue #103: S3側でファイルサイズ上限を強制するcontent-length-range
    # 条件がpresigned POSTのpolicyに含まれていることを検証する。
    policy = json.loads(base64.b64decode(data["uploadFields"]["policy"]))
    assert ["content-length-range", 0, attachments._MAX_ATTACHMENT_SIZE_BYTES] in policy[
        "conditions"
    ]


def test_create_attachment_upload_url_rejects_unsupported_content_type(table):
    resp = attachments.create_attachment_upload_url(
        "user-1", api_event(body={"contentType": "application/pdf"})
    )
    assert resp["statusCode"] == 400
    assert body_of(resp)["error"]["code"] == "INVALID_PARAMETER"
