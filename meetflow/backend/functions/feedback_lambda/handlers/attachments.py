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
# Issue #103: スクリーンショットはアバター/コミュニティアイコンと違い
# フロントエンドでリサイズされないため、高解像度スクリーンショットを
# 見込んでやや大きめの上限にしている。
_MAX_ATTACHMENT_SIZE_BYTES = 10 * 1024 * 1024

_s3_client = None


def _get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


def create_attachment_upload_url(user_id, event):
    """F-1402 (API設計書v1.17 §12b.2)。スクリーンショットはAPI Gateway/
    Lambda経由でバイナリを中継せず、フロントエンドがS3へ直接POSTする
    (Lambda設計書v1.7 §9b.3)。フロントは返却された`uploadUrl`/`uploadFields`
    で画像をアップロードした後、`attachmentKey`を`POST /feedback`の
    attachmentKeysに含める。
    presigned PUT方式はConditionsを指定できずS3側でファイルサイズを
    強制できないため、Issue #103でpresigned POST方式に切り替えて
    content-length-range条件を付与している。
    """
    body = parse_body(event)
    content_type = body.get("contentType")
    if content_type not in _ALLOWED_CONTENT_TYPES:
        return error_response("INVALID_PARAMETER", "contentTypeが不正です")

    ext = _ALLOWED_CONTENT_TYPES[content_type]
    attachment_key = f"feedback/{user_id}/{uuid.uuid4().hex}.{ext}"
    presigned_post = _get_s3_client().generate_presigned_post(
        Bucket=os.environ["FEEDBACK_ATTACHMENTS_BUCKET_NAME"],
        Key=attachment_key,
        Fields={"Content-Type": content_type},
        Conditions=[
            {"Content-Type": content_type},
            ["content-length-range", 0, _MAX_ATTACHMENT_SIZE_BYTES],
        ],
        ExpiresIn=_EXPIRES_IN_SECONDS,
    )

    return success_response(
        {
            "uploadUrl": presigned_post["url"],
            "uploadFields": presigned_post["fields"],
            "attachmentKey": attachment_key,
            "expiresIn": _EXPIRES_IN_SECONDS,
        }
    )


def generate_view_url(attachment_key: str) -> str:
    """Lambda設計書v1.7 §9b.3: 運営者がフィードバック管理画面(S-29)から
    スクリーンショットを閲覧する際、都度署名付きGET URLを発行する
    (バケット自体は非公開のため)。フィードバック詳細取得(feedback.
    get_feedback)からのみ呼ばれる想定で、一覧取得では呼ばない
    (attachmentKeysの数だけ署名生成コストがかかるため)。
    """
    return _get_s3_client().generate_presigned_url(
        "get_object",
        Params={
            "Bucket": os.environ["FEEDBACK_ATTACHMENTS_BUCKET_NAME"],
            "Key": attachment_key,
        },
        ExpiresIn=_EXPIRES_IN_SECONDS,
    )
