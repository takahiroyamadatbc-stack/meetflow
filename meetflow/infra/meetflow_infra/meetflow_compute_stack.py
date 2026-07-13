from pathlib import Path

from aws_cdk import (
    Annotations,
    CfnOutput,
    Duration,
    Stack,
    aws_cognito as cognito,
    aws_dynamodb as dynamodb,
    aws_events as events,
    aws_events_targets as events_targets,
    aws_iam as iam,
    aws_lambda as lambda_,
)
from constructs import Construct

from .naming import user_lambda_function_name

_BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"


class MeetFlowComputeStack(Stack):
    """CDK stack for MeetFlow's domain Lambdas (Lambda設計書v1.1).

    All 7 domain Lambdas: shared Layer (§12.1) + UserLambda (§3) +
    CommunityLambda (§4) + AvailabilityLambda (§5) + MatchingLambda (§6) +
    EventLambda (§7) + ResultLambda (§8) + NotificationLambda (§9).
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        table: dynamodb.ITable,
        user_pool: cognito.IUserPool,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # This stack takes cross-stack references to both MeetFlowDataStack
        # (`table`) and MeetFlowAuthStack (`user_pool`), which makes CDK
        # warn about the default "strong" cross-stack reference export
        # behavior. Setting the `@aws-cdk/core:crossStackReferencesDefaultStrong`
        # context flag in cdk.json alone did not suppress it in practice, so
        # explicitly acknowledge it here using the id CDK's own warning
        # printed -- "strong" (the current default) is the right choice for
        # this project anyway: it protects the producer stacks (data/auth)
        # from being updated in a way that would break this consumer stack.
        Annotations.of(self).acknowledge_warning(
            "@aws-cdk/core:crossStackReferencesDefaultStrong"
        )

        self.env_name = env_name
        self.table = table

        # Lambda設計書v1.1 §12.1: DynamoDB client/query helpers, membership +
        # permission checks, OperationLog writer, and common error
        # responses, shared by every domain Lambda.
        self.common_layer = lambda_.LayerVersion(
            self,
            "MeetFlowCommonLayer",
            layer_version_name=f"{env_name}-meetflow-common",
            code=lambda_.Code.from_asset(str(_BACKEND_DIR / "layers" / "common")),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description="Shared DynamoDB/auth/OperationLog/error helpers for all domain Lambdas",
        )

        self.user_lambda = self._build_user_lambda()
        self._grant_cognito_invoke(user_pool)

        self.community_lambda = self._build_community_lambda()
        self.availability_lambda = self._build_availability_lambda()
        self.matching_lambda = self._build_matching_lambda()
        self.event_lambda = self._build_event_lambda()
        self.result_lambda = self._build_result_lambda()
        self.notification_lambda = self._build_notification_lambda()

    def _build_function(
        self,
        construct_id: str,
        *,
        function_name: str,
        code_subdir: str,
        timeout: Duration = None,
        memory_size: int = 256,
    ) -> lambda_.Function:
        """Shared scaffolding for every domain Lambda: same runtime,
        `handler.handler` entry point convention, common Layer attachment,
        and TABLE_NAME env var. Individual `_build_*_lambda` methods only
        need to add their own IAM grants on top of this.
        """
        return lambda_.Function(
            self,
            construct_id,
            function_name=function_name,
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset(str(_BACKEND_DIR / "functions" / code_subdir)),
            layers=[self.common_layer],
            timeout=timeout or Duration.seconds(10),
            memory_size=memory_size,
            environment={"TABLE_NAME": self.table.table_name},
        )

    def _build_user_lambda(self) -> lambda_.Function:
        fn = self._build_function(
            "UserLambda",
            # Explicit, predictable name: MeetFlowAuthStack's Post
            # Confirmation trigger references this exact name (see
            # naming.py) without importing this stack's construct, to avoid
            # a circular cross-stack dependency (see
            # MeetFlowAuthStack.add_post_confirmation_trigger).
            function_name=user_lambda_function_name(self.env_name),
            code_subdir="user_lambda",
        )

        # Lambda設計書v1.1 §3.3: PutItem (profile creation only), GetItem,
        # UpdateItem, scoped to this table's actions. Note: DynamoDB's
        # `dynamodb:LeadingKeys` IAM condition only supports exact
        # partition-key matches (typically used for per-identity access from
        # federated/Cognito Identity Pool credentials) -- it cannot express
        # a "PK begins_with USER#" condition for a Lambda execution role. So
        # the enforceable IAM boundary here is action-level (no
        # DeleteItem/Query/Scan); the PK-prefix isolation the design doc
        # describes is enforced by this Lambda's own code, not by IAM.
        self.table.grant(
            fn, "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"
        )
        if self.table.encryption_key:
            self.table.encryption_key.grant_encrypt_decrypt(fn)

        CfnOutput(
            self,
            "UserLambdaArn",
            value=fn.function_arn,
            description="UserLambda function ARN",
        )
        return fn

    def _build_community_lambda(self) -> lambda_.Function:
        fn = self._build_function(
            "CommunityLambda",
            function_name=f"{self.env_name}-meetflow-community-lambda",
            code_subdir="community_lambda",
        )

        # Lambda設計書v1.1 §4.3: Community, Membership, Invite, JoinRequest,
        # Place -- PutItem/GetItem/UpdateItem/Query, plus TransactWriteItems
        # for join-request approval and OWNER transfer (DynamoDB物理設計書
        # v1.3 §5). DeleteItem is needed for forced member removal (F-104,
        # 要件定義書v1.2 §10.3) even though the Lambda design doc's action
        # list for this Lambda doesn't explicitly call it out. As with
        # UserLambda, `dynamodb:LeadingKeys` can't express "PK begins_with
        # COMMUNITY#" for a Lambda execution role, so entity-prefix
        # isolation is enforced by this Lambda's own code, not IAM.
        self.table.grant(
            fn,
            "dynamodb:GetItem",
            "dynamodb:PutItem",
            "dynamodb:UpdateItem",
            "dynamodb:DeleteItem",
            "dynamodb:Query",
            "dynamodb:TransactWriteItems",
        )
        if self.table.encryption_key:
            self.table.encryption_key.grant_encrypt_decrypt(fn)

        CfnOutput(
            self,
            "CommunityLambdaArn",
            value=fn.function_arn,
            description="CommunityLambda function ARN",
        )
        return fn

    def _build_availability_lambda(self) -> lambda_.Function:
        fn = self._build_function(
            "AvailabilityLambda",
            function_name=f"{self.env_name}-meetflow-availability-lambda",
            code_subdir="availability_lambda",
        )

        # Lambda設計書v1.1 §5.3: PutItem/BatchWriteItem/GetItem/UpdateItem/
        # DeleteItem/Query on Availability's PK/SK + GSI1. TransactWriteItems
        # is needed too (not listed in §5.3, which predates this
        # implementation choice): editing an availability's startTime
        # changes its SK/GSI1SK, and DynamoDB item keys can't be updated in
        # place, so that case is an atomic delete+recreate.
        self.table.grant(
            fn,
            "dynamodb:GetItem",
            "dynamodb:PutItem",
            "dynamodb:UpdateItem",
            "dynamodb:DeleteItem",
            "dynamodb:Query",
            "dynamodb:BatchWriteItem",
            "dynamodb:TransactWriteItems",
        )
        if self.table.encryption_key:
            self.table.encryption_key.grant_encrypt_decrypt(fn)

        CfnOutput(
            self,
            "AvailabilityLambdaArn",
            value=fn.function_arn,
            description="AvailabilityLambda function ARN",
        )
        return fn

    def _build_matching_lambda(self) -> lambda_.Function:
        fn = self._build_function(
            "MatchingLambda",
            function_name=f"{self.env_name}-meetflow-matching-lambda",
            code_subdir="matching_lambda",
            # F-401 candidate generation is the "heavy" path this Lambda was
            # split out for (Lambda設計書v1.1 §1, §6.4): longer timeout and
            # more memory than the CRUD-style domain Lambdas.
            timeout=Duration.seconds(30),
            memory_size=512,
        )

        # Lambda設計書v1.1 §6.5: Query (Availability, EventTemplate),
        # PutItem/GetItem/Query (MatchCandidate incl. GSI2),
        # PutItem/UpdateItem/Query (CandidateMember incl. GSI1). UpdateItem/
        # DeleteItem on EventTemplate are needed for F-303/F-304 (edit/
        # delete) even though §6.5's action list doesn't call them out
        # (same kind of gap as CommunityLambda's DeleteItem).
        self.table.grant(
            fn,
            "dynamodb:GetItem",
            "dynamodb:PutItem",
            "dynamodb:UpdateItem",
            "dynamodb:DeleteItem",
            "dynamodb:Query",
        )
        if self.table.encryption_key:
            self.table.encryption_key.grant_encrypt_decrypt(fn)

        # §6.5: `events:PutEvents` for `CandidateConflictDetected`.
        events.EventBus.grant_all_put_events(fn)

        # §6.1/§6.7: subscribe to `EventConfirmed` (published later by
        # EventLambda) for post-hoc double-booking detection. The rule can
        # be created before EventLambda exists -- it just won't have
        # anything to match yet. The source/detail-type strings must match
        # backend/layers/common/python/meetflow_common/events_bus.py
        # (EVENT_SOURCE, EVENT_CONFIRMED) -- CDK (this file) and the Lambda
        # runtime code are separate Python environments, so this can't
        # import that module directly.
        events.Rule(
            self,
            "MatchingEventConfirmedRule",
            rule_name=f"{self.env_name}-meetflow-matching-event-confirmed",
            event_pattern=events.EventPattern(
                source=["meetflow.events"], detail_type=["EventConfirmed"]
            ),
            targets=[events_targets.LambdaFunction(fn)],
        )

        CfnOutput(
            self,
            "MatchingLambdaArn",
            value=fn.function_arn,
            description="MatchingLambda function ARN",
        )
        return fn

    def _build_event_lambda(self) -> lambda_.Function:
        fn = self._build_function(
            "EventLambda",
            function_name=f"{self.env_name}-meetflow-event-lambda",
            code_subdir="event_lambda",
        )

        # Lambda設計書v1.1 §7.4: Event, Participant (incl. GSI1 for the
        # double-booking check), CancelRequest, EventStatusHistory --
        # PutItem/GetItem/UpdateItem/Query, TransactWriteItems (event
        # confirmation). Also needs read/update access to MatchCandidate +
        # CandidateMember (incl. GSI2, to resolve candidateId at creation/
        # confirm time and mark them used), and read access to Place/User
        # for the event detail/list responses -- all the same table, so
        # granted as one set of table-level actions like the other domain
        # Lambdas.
        self.table.grant(
            fn,
            "dynamodb:GetItem",
            "dynamodb:PutItem",
            "dynamodb:UpdateItem",
            "dynamodb:Query",
            "dynamodb:TransactWriteItems",
        )
        if self.table.encryption_key:
            self.table.encryption_key.grant_encrypt_decrypt(fn)

        # §7.4: `events:PutEvents` for EventConfirmed/EventCancelled/
        # CancelApproved.
        events.EventBus.grant_all_put_events(fn)

        CfnOutput(
            self,
            "EventLambdaArn",
            value=fn.function_arn,
            description="EventLambda function ARN",
        )
        return fn

    def _build_result_lambda(self) -> lambda_.Function:
        fn = self._build_function(
            "ResultLambda",
            function_name=f"{self.env_name}-meetflow-result-lambda",
            code_subdir="result_lambda",
        )

        # Lambda設計書v1.1 §8.4: PutItem/Query (GameSession, GameResult incl.
        # GSI1). GetItem is also needed (not listed in §8.4) to look up the
        # Event/Membership context for permission checks.
        self.table.grant(
            fn,
            "dynamodb:GetItem",
            "dynamodb:PutItem",
            "dynamodb:Query",
        )
        if self.table.encryption_key:
            self.table.encryption_key.grant_encrypt_decrypt(fn)

        CfnOutput(
            self,
            "ResultLambdaArn",
            value=fn.function_arn,
            description="ResultLambda function ARN",
        )
        return fn

    def _build_notification_lambda(self) -> lambda_.Function:
        fn = self._build_function(
            "NotificationLambda",
            function_name=f"{self.env_name}-meetflow-notification-lambda",
            code_subdir="notification_lambda",
        )

        # Lambda設計書v1.1 §9.4: PutItem/Query/UpdateItem (Notification).
        # Query on Membership (via primary key, not a new grant) is needed
        # too, to resolve a community's OWNER/ADMIN user ids for
        # CandidateConflictDetected -- same table, same action set.
        self.table.grant(
            fn,
            "dynamodb:GetItem",
            "dynamodb:PutItem",
            "dynamodb:UpdateItem",
            "dynamodb:Query",
        )
        if self.table.encryption_key:
            self.table.encryption_key.grant_encrypt_decrypt(fn)

        # §9.1: subscribe to every domain event that fans out to a
        # notification. Source/detail-type strings must match
        # backend/layers/common/python/meetflow_common/events_bus.py.
        events.Rule(
            self,
            "NotificationDomainEventsRule",
            rule_name=f"{self.env_name}-meetflow-notification-domain-events",
            event_pattern=events.EventPattern(
                source=["meetflow.events"],
                detail_type=[
                    "EventConfirmed",
                    "EventCancelled",
                    "CancelApproved",
                    "CandidateConflictDetected",
                ],
            ),
            targets=[events_targets.LambdaFunction(fn)],
        )

        CfnOutput(
            self,
            "NotificationLambdaArn",
            value=fn.function_arn,
            description="NotificationLambda function ARN",
        )
        return fn

    def _grant_cognito_invoke(self, user_pool: cognito.IUserPool) -> None:
        """Grant Cognito permission to invoke UserLambda as its Post
        Confirmation trigger.

        This is the other half of the wiring described in
        MeetFlowAuthStack.add_post_confirmation_trigger: this stack owns the
        real Lambda resource, so the AWS::Lambda::Permission must be created
        here. It only needs a one-directional import of the User Pool's ARN
        (this stack already depends on MeetFlowAuthStack for the User Pool
        object itself, via the `user_pool` constructor argument), so no
        cycle is introduced.
        """
        self.user_lambda.add_permission(
            "AllowCognitoInvokePostConfirmation",
            principal=iam.ServicePrincipal("cognito-idp.amazonaws.com"),
            action="lambda:InvokeFunction",
            source_arn=user_pool.user_pool_arn,
        )
