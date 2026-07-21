from aws_cdk import (
    CfnOutput,
    RemovalPolicy,
    Stack,
    aws_apigateway as apigateway,
    aws_cognito as cognito,
    aws_lambda as lambda_,
    aws_logs as logs,
)
from constructs import Construct

# このスタックは、これまで他のすべてのスタックが存在を前提としてきただけの
# API Gatewayレイヤーを実装する：AWSシステム構成設計書v1.3 §5-6（REST API、
# Cognito Authorizer、独自のAuthLambdaは無し）およびAPI設計書v1.5（エンド
# ポイント一覧）。各ドメインLambdaの`handler.py`はすでに
# `event["httpMethod"]`/`event["resource"]`/`event["pathParameters"]`で
# ディスパッチしており、呼び出し元のuserIdを
# `event["requestContext"]["authorizer"]["claims"]["sub"]`から読み取って
# いる（meetflow_common.router.dispatch / auth.get_authenticated_user_id）
# -- これはREST APIのLambdaプロキシ統合（ペイロード形式1.0）の形であり、
# HTTP APIのv2形式ではない。そのためここでは`aws_apigateway.RestApi`を
# 使う必要があり、`aws_apigatewayv2.HttpApi`は使えない。
#
# AWSシステム構成設計書v1.3 §6の「ドメイン単位ルーティング」表
# （`/communities/*` -> CommunityLambda等）は例示であって文字通りの規定
# ではない：いくつかのドメインは、本来別のドメインが所有するプレフィックス
# の下に、より具体的なサブパスを切り出している（例：
# `/communities/{communityId}/availability/*`はCommunityLambdaではなく
# AvailabilityLambda）。プレフィックス/プロキシベースの統合ではこれを
# 表現できないため、以下の(method, path)の組はすべて各ドメインの
# `_ROUTES`辞書から一字一句そのまま取得している -- ドキュメントの要約表
# ではなく実際の実装から：
#   backend/functions/user_lambda/handler.py
#   backend/functions/community_lambda/handler.py
#   backend/functions/availability_lambda/handler.py
#   backend/functions/matching_lambda/handler.py
#   backend/functions/event_lambda/handler.py
#   backend/functions/result_lambda/handler.py
#   backend/functions/notification_lambda/handler.py
#
# `GET /communities/{communityId}/logs`と`GET /users/{userId}/logs`
# （API設計書v1.7 §12、OperationLog）はどちらもCommunityLambda
# （`community_lambda/handlers/logs.py`）が担当する。後者はURLパスこそ
# `/users/`始まりだが、権限判定（本人 or 同一コミュニティのOWNER/ADMIN）が
# Membership/roleに依存するため、それらを扱うCommunityLambda側に置いている
# （`GET /users/{userId}/results`がResultLambda担当なのと同様、URLプレフィックス
# と担当Lambdaが必ずしも一致しない例）。
_ROUTES: list[tuple[str, str, str]] = [
    # UserLambda
    ("GET", "/users/me", "user"),
    ("PUT", "/users/me", "user"),
    ("DELETE", "/users/me", "user"),
    ("POST", "/users/me/avatar/upload-url", "user"),
    ("DELETE", "/users/me/avatar", "user"),
    # CommunityLambda
    ("POST", "/communities", "community"),
    ("GET", "/communities", "community"),
    ("PUT", "/communities/order", "community"),
    ("GET", "/communities/{communityId}", "community"),
    ("PUT", "/communities/{communityId}", "community"),
    ("DELETE", "/communities/{communityId}", "community"),
    ("PUT", "/communities/{communityId}/theme-color", "community"),
    ("PUT", "/communities/{communityId}/ranking-settings", "community"),
    ("POST", "/communities/{communityId}/icon/upload-url", "community"),
    ("POST", "/communities/{communityId}/owner-transfer", "community"),
    ("POST", "/communities/{communityId}/invite", "community"),
    ("GET", "/invites/{token}", "community"),
    ("POST", "/invites/{token}/join", "community"),
    ("POST", "/invites/{token}/revoke", "community"),
    ("GET", "/communities/{communityId}/members", "community"),
    ("PUT", "/communities/{communityId}/members/{userId}", "community"),
    ("POST", "/communities/{communityId}/members/me/leave", "community"),
    ("PUT", "/communities/{communityId}/members/me/display-name", "community"),
    ("PUT", "/communities/{communityId}/members/me/auto-approve", "community"),
    ("PUT", "/communities/{communityId}/members/me/frequency-limit", "community"),
    ("GET", "/communities/{communityId}/join-requests", "community"),
    (
        "POST",
        "/communities/{communityId}/join-requests/{requestId}/approve",
        "community",
    ),
    (
        "POST",
        "/communities/{communityId}/join-requests/{requestId}/reject",
        "community",
    ),
    ("GET", "/communities/{communityId}/locations", "community"),
    ("POST", "/communities/{communityId}/locations", "community"),
    ("GET", "/communities/{communityId}/logs", "community"),
    ("GET", "/users/{userId}/logs", "community"),
    # AvailabilityLambda
    ("POST", "/communities/{communityId}/availability", "availability"),
    ("POST", "/communities/{communityId}/availability/batch", "availability"),
    ("GET", "/communities/{communityId}/availability", "availability"),
    ("PUT", "/availability/{availabilityId}", "availability"),
    ("DELETE", "/availability/{availabilityId}", "availability"),
    ("POST", "/communities/{communityId}/availability-requests", "availability"),
    ("GET", "/communities/{communityId}/availability-requests", "availability"),
    (
        "GET",
        "/communities/{communityId}/availability-requests/{requestId}/pending-members",
        "availability",
    ),
    # MatchingLambda
    ("POST", "/communities/{communityId}/event-templates", "matching"),
    ("GET", "/communities/{communityId}/event-templates", "matching"),
    ("PUT", "/communities/{communityId}/event-templates/{templateId}", "matching"),
    ("DELETE", "/communities/{communityId}/event-templates/{templateId}", "matching"),
    ("POST", "/communities/{communityId}/matching", "matching"),
    ("POST", "/communities/{communityId}/matching/candidates/manual", "matching"),
    ("GET", "/communities/{communityId}/matching/candidates", "matching"),
    ("GET", "/matching/candidates/{candidateId}", "matching"),
    # EventLambda
    ("POST", "/events", "event"),
    ("GET", "/users/me/events", "event"),
    ("GET", "/events/{eventId}", "event"),
    ("POST", "/events/{eventId}/confirm", "event"),
    ("POST", "/events/{eventId}/cancel", "event"),
    ("POST", "/events/{eventId}/complete", "event"),
    ("GET", "/communities/{communityId}/events", "event"),
    ("GET", "/events/{eventId}/participants", "event"),
    ("POST", "/events/{eventId}/participants", "event"),
    ("POST", "/events/{eventId}/participants/{userId}/remove", "event"),
    ("GET", "/events/{eventId}/cancel-requests", "event"),
    ("POST", "/events/{eventId}/cancel-request", "event"),
    ("POST", "/events/{eventId}/cancel-requests/{userId}/approve", "event"),
    ("POST", "/events/{eventId}/participants/me/approve", "event"),
    ("POST", "/events/{eventId}/participants/me/reject", "event"),
    # ResultLambda
    ("POST", "/events/{eventId}/sessions", "result"),
    ("GET", "/events/{eventId}/sessions", "result"),
    ("PUT", "/events/{eventId}/sessions/{sessionNo}", "result"),
    ("DELETE", "/events/{eventId}/sessions/{sessionNo}", "result"),
    ("GET", "/communities/{communityId}/game-sessions/last-settings", "result"),
    ("GET", "/users/{userId}/results", "result"),
    ("GET", "/communities/{communityId}/rankings", "result"),
    # NotificationLambda
    ("GET", "/notifications", "notification"),
    ("PUT", "/notifications/{notificationId}/read", "notification"),
    ("POST", "/users/me/push-subscriptions", "notification"),
    ("DELETE", "/users/me/push-subscriptions", "notification"),
    # FeedbackLambda
    ("POST", "/feedback", "feedback"),
    ("GET", "/feedback", "feedback"),
    ("GET", "/feedback/stats", "feedback"),
    ("GET", "/feedback/{feedbackId}", "feedback"),
    ("PATCH", "/feedback/{feedbackId}", "feedback"),
    ("POST", "/feedback/attachments/presign", "feedback"),
    ("GET", "/announcements", "feedback"),
    ("POST", "/announcements", "feedback"),
    ("PUT", "/announcements/{announcementId}", "feedback"),
]


class MeetFlowApiStack(Stack):
    """MeetFlowのREST API用CDKスタック（API設計書v1.5、AWSシステム構成
    設計書v1.3 §5-6）：8つのドメインLambdaすべての前段に配置する単一の
    API Gateway RestApi。すべてのメソッドでCognito User Pool Authorizerを
    必須とする（全ルートにログイン済みの呼び出し元が必要であり、公開
    エンドポイントは存在しない）。
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        user_pool: cognito.IUserPool,
        user_lambda: lambda_.IFunction,
        community_lambda: lambda_.IFunction,
        availability_lambda: lambda_.IFunction,
        matching_lambda: lambda_.IFunction,
        event_lambda: lambda_.IFunction,
        result_lambda: lambda_.IFunction,
        notification_lambda: lambda_.IFunction,
        feedback_lambda: lambda_.IFunction,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name
        lambdas_by_domain = {
            "user": user_lambda,
            "community": community_lambda,
            "availability": availability_lambda,
            "matching": matching_lambda,
            "event": event_lambda,
            "result": result_lambda,
            "notification": notification_lambda,
            "feedback": feedback_lambda,
        }

        # アクセスログの書き込みには、アカウント/リージョンごとに一度だけ
        # 必要なCloudWatch書き込み用IAMロール(`AWS::ApiGateway::Account`)が
        # 要る。`RestApi`の`cloud_watch_role`はデフォルトTrueで、これを
        # 自動的に作成・管理してくれるため、ここでは明示的に触っていない
        # (手動で作ると`AWS::ApiGateway::Account`が重複して衝突する)。
        access_log_group = logs.LogGroup(
            self,
            "ApiAccessLogGroup",
            log_group_name=f"/aws/apigateway/{env_name}-meetflow-api-access",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # REGIONAL, not EDGE: AWSシステム構成設計書v1.3のアーキテクチャ図
        # (`User → CloudFront → API Gateway → Lambda`) はCloudFrontを前段に
        # 置く前提なので、API Gateway自体をエッジ最適化して二重CDNにしない。
        self.api = apigateway.RestApi(
            self,
            "MeetFlowApi",
            rest_api_name=f"{env_name}-meetflow-api",
            endpoint_types=[apigateway.EndpointType.REGIONAL],
            deploy_options=apigateway.StageOptions(
                stage_name=env_name,
                # docsに具体的な数値の規定は無いため、個人開発MVP規模に対す
                # る妥当な既定値。
                throttling_rate_limit=50,
                throttling_burst_limit=100,
                # 障害時にAPI Gateway側(どのリクエストがどう失敗したか)を
                # 追えるようにするアクセスログ。X-Rayトレーシングは規模と
                # 複雑さの割に旨味が薄いため見送り。
                access_log_destination=apigateway.LogGroupLogDestination(
                    access_log_group
                ),
                access_log_format=apigateway.AccessLogFormat.json_with_standard_fields(
                    caller=False,
                    http_method=True,
                    ip=True,
                    protocol=True,
                    request_time=True,
                    resource_path=True,
                    response_length=True,
                    status=True,
                    user=False,
                ),
            ),
            default_cors_preflight_options=apigateway.CorsOptions(
                # フロントエンドは未実装でオリジンも未確定のため暫定で全許可
                # (Authorizationヘッダーはbearerトークンでcredentials
                # (Cookie)は使わないため許容範囲)。フロントエンドのドメイン
                # 確定後に絞り込むこと。
                allow_origins=apigateway.Cors.ALL_ORIGINS,
                allow_methods=apigateway.Cors.ALL_METHODS,
                allow_headers=["Content-Type", "Authorization"],
            ),
        )

        # AWSシステム構成設計書v1.3 §5: JWT検証はAPI GatewayのCognito
        # Authorizerで完結させ、独自のAuthLambdaは持たない。
        authorizer = apigateway.CognitoUserPoolsAuthorizer(
            self, "MeetFlowCognitoAuthorizer", cognito_user_pools=[user_pool]
        )

        integrations: dict[str, apigateway.LambdaIntegration] = {}
        resource_cache: dict[str, apigateway.IResource] = {"": self.api.root}

        def _resource_for_path(path: str) -> apigateway.IResource:
            if path in resource_cache:
                return resource_cache[path]
            parent_path, _, part = path.rpartition("/")
            parent = _resource_for_path(parent_path)
            existing = parent.get_resource(part)
            resource = existing if existing is not None else parent.add_resource(part)
            resource_cache[path] = resource
            return resource

        for method, path, domain in _ROUTES:
            integration = integrations.get(domain)
            if integration is None:
                # allow_test_invoke=False: デフォルトTrueだと各メソッドご
                # とに「本番ステージ用」に加えて「APIGatewayコンソールの
                # テスト呼び出し用」のLambda::Permissionも追加され、Sta
                # tement数が実質倍になる。CommunityLambdaは24エンドポイ
                # ントを一手に引き受けており、両方作るとLambdaのリソース
                # ポリシーサイズ上限(20480バイト)を超えてCREATE_FAILEDに
                # なる（コンソールの「テスト」ボタンが使えなくなるだけで
                # 実際のAPI呼び出しには影響しない）。
                integration = apigateway.LambdaIntegration(
                    lambdas_by_domain[domain], allow_test_invoke=False
                )
                integrations[domain] = integration
            resource = _resource_for_path(path)
            resource.add_method(
                method,
                integration,
                authorizer=authorizer,
                authorization_type=apigateway.AuthorizationType.COGNITO,
            )

        CfnOutput(
            self,
            "ApiUrl",
            value=self.api.url,
            description="MeetFlow REST API invoke URL",
        )
