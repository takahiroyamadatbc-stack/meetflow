import json
import os

import boto3
from boto3.dynamodb.conditions import Key
from pywebpush import WebPushException, webpush

# Lambda設計書v1.2 §9.3b. VAPID_SECRET_NAME/VAPID_SUBJECT are set by
# meetflow_compute_stack.py's `_build_notification_lambda`. The secret value
# is JSON: {"vapidPrivateKey": "<base64url>", "vapidPublicKey": "<base64url>"}
# -- pywebpush.webpush() treats a plain string vapid_private_key as either a
# file path or (falling through Vapid.from_string) a base64url-encoded raw
# key, never a PEM block, so the secret must hold the raw key, not PEM text.
_vapid_private_key = None
_secrets_client = None


def _get_vapid_private_key():
    global _vapid_private_key, _secrets_client
    if _vapid_private_key is None:
        if _secrets_client is None:
            _secrets_client = boto3.client("secretsmanager")
        secret = _secrets_client.get_secret_value(SecretId=os.environ["VAPID_SECRET_NAME"])
        _vapid_private_key = json.loads(secret["SecretString"])["vapidPrivateKey"]
    return _vapid_private_key


def send_push_to_user(table, user_id, *, title, body, notif_type):
    """Best-effort Web Push fan-out for one user's registered devices
    (PushSubscription, DynamoDB物理設計書v1.4 §3.17). Never raises -- a
    failed/expired push endpoint must not fail the in-app Notification
    record that was just created, nor retry-storm the EventBridge rule that
    triggered it for every other target user.
    """
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"USER#{user_id}")
        & Key("SK").begins_with("PUSHSUB#"),
    )
    subscriptions = resp.get("Items", [])
    if not subscriptions:
        return

    private_key = _get_vapid_private_key()
    payload = json.dumps({"title": title, "body": body, "type": notif_type})
    vapid_claims = {"sub": os.environ.get("VAPID_SUBJECT", "mailto:admin@meetflow.jp")}

    for subscription in subscriptions:
        subscription_info = {
            "endpoint": subscription["endpoint"],
            "keys": {
                "p256dh": subscription["p256dh"],
                "auth": subscription["auth"],
            },
        }
        try:
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=private_key,
                vapid_claims=dict(vapid_claims),
            )
        except WebPushException as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code in (404, 410):
                table.delete_item(
                    Key={"PK": subscription["PK"], "SK": subscription["SK"]}
                )
            else:
                print(f"Web Push送信に失敗しました(userId={user_id}): {exc}")
