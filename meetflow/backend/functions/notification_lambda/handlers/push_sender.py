import json
import os

import boto3
from boto3.dynamodb.conditions import Key
from pywebpush import WebPushException, webpush

# Lambda設計書v1.2 §9.3b。VAPID_SECRET_NAME/VAPID_SUBJECTは
# meetflow_compute_stack.pyの`_build_notification_lambda`が設定する。
# シークレットの値はJSON:
# {"vapidPrivateKey": "<base64url>", "vapidPublicKey": "<base64url>"}
# -- pywebpush.webpush()は文字列のvapid_private_keyをファイルパス、または
# （Vapid.from_stringにフォールバックして）base64urlエンコードされた生鍵
# のいずれかとして扱い、PEMブロックとしては扱わない。そのためシークレット
# にはPEMテキストではなく生鍵を保持させる必要がある。
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
    """あるユーザーの登録済み全デバイス（PushSubscription、DynamoDB物理
    設計書v1.4 §3.17）へのベストエフォートなWeb Pushファンアウト。決して
    例外を送出しない -- 失敗/期限切れのプッシュエンドポイントが、直前に
    作成したアプリ内Notificationレコードを失敗させたり、これを発火させた
    EventBridge Ruleを他の全対象ユーザー分リトライストームさせたりしては
    ならないため。
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
