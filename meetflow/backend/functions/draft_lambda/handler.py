from meetflow_common import dispatch

from errors import DraftError, draft_error
from handlers import drafts, picks, progress

# DraftLambda（DESIGN.md §4.11: 8つ目のドメインLambda。既存5スタックとは
# 別の MeetFlowDraftStack に属し、専用テーブル・専用API Gatewayを持つ）。
_ROUTES = {
    ("POST", "/communities/{communityId}/drafts"): drafts.create_draft,
    ("GET", "/communities/{communityId}/drafts"): drafts.list_drafts,
    ("GET", "/drafts/{draftId}"): drafts.get_draft,
    ("GET", "/drafts/{draftId}/rosters"): drafts.get_rosters,
    ("GET", "/drafts/{draftId}/lotteries"): drafts.get_lotteries,
    ("POST", "/drafts/{draftId}/start"): drafts.start_draft,
    ("POST", "/drafts/{draftId}/picks"): picks.submit_pick,
    ("POST", "/drafts/{draftId}/picks/proxy"): picks.submit_proxy_pick,
    ("POST", "/drafts/{draftId}/reveal"): progress.reveal,
    ("POST", "/drafts/{draftId}/lottery"): progress.run_lottery,
    ("POST", "/drafts/{draftId}/advance"): progress.advance,
}


def handler(event, context):
    # 共通の`dispatch`はAuthError/BadRequestしか知らないため、ドラフト固有の
    # DraftErrorはここで受けてエラーエンベロープに変換する
    # （errors.pyのコード表を共通レイヤーに入れない理由もそちらのdocstring参照）。
    try:
        return dispatch(_ROUTES, event)
    except DraftError as exc:
        return draft_error(exc.code, exc.message)
