import json

import boto3

# Lambda設計書v1.1 §7.3: publish/subscribeを行う各ドメインLambdaが
# 合意しておく必要があるEventBridgeのdetail-type名。
# EventLambda/MatchingLambda/NotificationLambdaに文字列リテラルとして
# 重複して持たせるのではなく、ここに一元化している。
EVENT_SOURCE = "meetflow.events"

EVENT_CONFIRMED = "EventConfirmed"
EVENT_CANCELLED = "EventCancelled"
CANCEL_APPROVED = "CancelApproved"
CANDIDATE_CONFLICT_DETECTED = "CandidateConflictDetected"
EVENT_STATUS_CHANGED = "EventStatusChanged"
AVAILABILITY_REQUEST_CREATED = "AvailabilityRequestCreated"
EVENT_AWAITING_APPROVAL = "EventAwaitingApproval"
EVENT_PARTICIPANT_REJECTED = "EventParticipantRejected"
FEEDBACK_REPLIED = "FeedbackReplied"
# Issue #97専用の狭い例外（Lambda設計書v1.10 §5.2の「MVP方針確認」注記
# 参照）。空き予定登録/更新のたびに発行するが、あくまで確定済み・定員
# 未充足イベントへの追加候補検知にのみ使う -- F-401マッチング候補生成の
# 自動実行トリガーには使わない（その方針自体は変更していない）。
AVAILABILITY_UPDATED = "AvailabilityUpdated"
CONFIRMED_EVENT_CANDIDATE_AVAILABLE = "ConfirmedEventCandidateAvailable"

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("events")
    return _client


def put_event(detail_type: str, detail: dict) -> None:
    """MeetFlowのドメインイベントを、アカウントのデフォルトEventBridgeバスに
    publishする（AWSシステム構成設計書v1.2 §9: 通知・衝突検知の
    ファンアウトにのみ使用し、マッチングを自動起動するためには使わない）。
    """
    _get_client().put_events(
        Entries=[
            {
                "Source": EVENT_SOURCE,
                "DetailType": detail_type,
                "Detail": json.dumps(detail, ensure_ascii=False),
            }
        ]
    )
