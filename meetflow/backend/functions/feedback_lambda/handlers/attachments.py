import os
import uuid

import boto3

from meetflow_common import error_response, parse_body, success_response

_EXPIRES_IN_SECONDS = 300
_ALLOWED_CONTENT_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}

_s3_client = None


def _get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


def create_attachment_upload_url(user_id, event):
    """F-1402 (API設計書v1.17 §12b.2)。スクリーンショットはAPI Gateway/
    Lambda経由でバイナリを中継せず、フロントエンドがS3へ直接PUTする
    (Lambda設計書v1.7 §9b.3)。フロントは返却された`uploadUrl`へ画像を
    PUTした後、`attachmentKey`を`POST /feedback`のattachmentKeysに含める。
    """
    body = parse_body(event)
    content_type = body.get("contentType")
    if content_type not in _ALLOWED_CONTENT_TYPES:
        return error_response("INVALID_PARAMETER", "contentTypeが不正です")

    ext = _ALLOWED_CONTENT_TYPES[content_type]
    attachment_key = f"feedback/{user_id}/{uuid.uuid4().hex}.{ext}"
    upload_url = _get_s3_client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": os.environ["FEEDBACK_ATTACHMENTS_BUCKET_NAME"],
            "Key": attachment_key,
            "ContentType": content_type,
        },
        ExpiresIn=_EXPIRES_IN_SECONDS,
    )

    return success_response(
        {
            "uploadUrl": upload_url,
            "attachmentKey": attachment_key,
            "expiresIn": _EXPIRES_IN_SECONDS,
        }
    )
