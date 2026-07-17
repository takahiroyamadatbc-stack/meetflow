"""イベント確定フローの中間状態（Issue #10: 仮確定→全員承認→本確定）で
新たに導入するstatus文字列を一元管理する。

既存のEvent.status/Participant.status文字列（PENDING_APPROVAL/CONFIRMED等）
は14ファイルに分散したハードコード文字列のままだが、これらを一括で定数化
するリファクタリングは本Issueのスコープ外とする（既存コードへの無関係な
変更を持ち込むリスクを避けるため）。ここでは今回新規に導入する文字列のみを
対象にする。
"""

EVENT_STATUS_AWAITING_MEMBER_APPROVAL = "AWAITING_MEMBER_APPROVAL"

PARTICIPANT_STATUS_AWAITING_APPROVAL = "AWAITING_APPROVAL"
PARTICIPANT_STATUS_REJECTED = "REJECTED"

# ダブルブッキング事前チェック（confirm_event）で「予約済み」とみなす
# Participant.statusの集合。仮確定時点で承認待ちの参加者も、他の候補との
# 二重予約を防ぐ対象に含める必要があるため、CONFIRMEDだけでなく
# AWAITING_APPROVALも含める。
RESERVED_PARTICIPANT_STATUSES = frozenset(
    {"CONFIRMED", PARTICIPANT_STATUS_AWAITING_APPROVAL}
)
