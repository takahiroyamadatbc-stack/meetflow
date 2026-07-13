from aws_cdk import (
    CfnOutput,
    Stack,
    aws_apigateway as apigateway,
    aws_cognito as cognito,
    aws_lambda as lambda_,
)
from constructs import Construct

# This stack implements the API Gateway layer that every other stack has so
# far only assumed exists: AWSシステム構成設計書v1.3 §5-6 (REST API,
# Cognito Authorizer, no custom AuthLambda) and API設計書v1.5 (endpoint
# list). Every domain Lambda's `handler.py` already dispatches on
# `event["httpMethod"]`/`event["resource"]`/`event["pathParameters"]` and
# reads the caller's userId from
# `event["requestContext"]["authorizer"]["claims"]["sub"]`
# (meetflow_common.router.dispatch / auth.get_authenticated_user_id) --
# that is REST API's Lambda proxy integration (payload format 1.0) shape,
# not HTTP API's v2 shape, so this must be `aws_apigateway.RestApi`, not
# `aws_apigatewayv2.HttpApi`.
#
# AWSシステム構成設計書v1.3 §6's "ドメイン単位ルーティング" table
# (`/communities/*` -> CommunityLambda etc.) is illustrative, not literal:
# several domains carve out more specific sub-paths under a prefix another
# domain otherwise owns (e.g. `/communities/{communityId}/availability/*`
# is AvailabilityLambda, not CommunityLambda). A prefix/proxy-based
# integration can't express that, so every (method, path) pair below is
# taken verbatim from each domain's `_ROUTES` dict -- the actual
# implementation, not the doc's summary table:
#   backend/functions/user_lambda/handler.py
#   backend/functions/community_lambda/handler.py
#   backend/functions/availability_lambda/handler.py
#   backend/functions/matching_lambda/handler.py
#   backend/functions/event_lambda/handler.py
#   backend/functions/result_lambda/handler.py
#   backend/functions/notification_lambda/handler.py
#
# `GET /communities/{communityId}/logs` and `GET /users/{userId}/logs`
# (API設計書v1.5 §12, OperationLog) are documented but have no handler in
# any domain's `_ROUTES` yet, so they are intentionally omitted here --
# routing to a Lambda that would just 404 the path serves no purpose.
_ROUTES: list[tuple[str, str, str]] = [
    # UserLambda
    ("GET", "/users/me", "user"),
    ("PUT", "/users/me", "user"),
    # CommunityLambda
    ("POST", "/communities", "community"),
    ("GET", "/communities", "community"),
    ("PUT", "/communities/{communityId}", "community"),
    ("POST", "/communities/{communityId}/owner-transfer", "community"),
    ("POST", "/communities/{communityId}/invite", "community"),
    ("POST", "/invites/{token}/join", "community"),
    ("GET", "/communities/{communityId}/members", "community"),
    ("PUT", "/communities/{communityId}/members/{userId}", "community"),
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
    ("GET", "/communities/{communityId}/matching/candidates", "matching"),
    ("GET", "/matching/candidates/{candidateId}", "matching"),
    # EventLambda
    ("POST", "/events", "event"),
    ("GET", "/events/{eventId}", "event"),
    ("POST", "/events/{eventId}/confirm", "event"),
    ("POST", "/events/{eventId}/cancel", "event"),
    ("GET", "/communities/{communityId}/events", "event"),
    ("GET", "/events/{eventId}/participants", "event"),
    ("GET", "/events/{eventId}/cancel-requests", "event"),
    ("POST", "/events/{eventId}/cancel-request", "event"),
    ("POST", "/events/{eventId}/cancel-requests/{userId}/approve", "event"),
    # ResultLambda
    ("POST", "/events/{eventId}/sessions", "result"),
    ("GET", "/users/{userId}/results", "result"),
    # NotificationLambda
    ("GET", "/notifications", "notification"),
    ("PUT", "/notifications/{notificationId}/read", "notification"),
    ("POST", "/users/me/push-subscriptions", "notification"),
    ("DELETE", "/users/me/push-subscriptions", "notification"),
]


class MeetFlowApiStack(Stack):
    """CDK stack for MeetFlow's REST API (API設計書v1.5, AWSシステム構成
    設計書v1.3 §5-6): a single API Gateway RestApi in front of all 7 domain
    Lambdas, with every method requiring the Cognito User Pool Authorizer
    (every route needs a logged-in caller -- there is no public endpoint).
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
        }

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
                integration = apigateway.LambdaIntegration(lambdas_by_domain[domain])
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
