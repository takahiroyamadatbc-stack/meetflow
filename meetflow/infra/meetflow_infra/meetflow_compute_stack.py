from pathlib import Path

from aws_cdk import (
    CfnOutput,
    Duration,
    Stack,
    aws_cognito as cognito,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_lambda as lambda_,
)
from constructs import Construct

from .naming import user_lambda_function_name

_BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"


class MeetFlowComputeStack(Stack):
    """CDK stack for MeetFlow's domain Lambdas (Lambda設計書v1.1).

    Starts with the shared Layer (§12.1) + UserLambda (§3). The remaining
    six domain Lambdas (Community/Availability/Matching/Event/Result/
    Notification) are added incrementally as follow-up work.
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

    def _build_user_lambda(self) -> lambda_.Function:
        fn = lambda_.Function(
            self,
            "UserLambda",
            # Explicit, predictable name: MeetFlowAuthStack's Post
            # Confirmation trigger references this exact name (see
            # naming.py) without importing this stack's construct, to avoid
            # a circular cross-stack dependency (see
            # MeetFlowAuthStack.add_post_confirmation_trigger).
            function_name=user_lambda_function_name(self.env_name),
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset(
                str(_BACKEND_DIR / "functions" / "user_lambda")
            ),
            layers=[self.common_layer],
            timeout=Duration.seconds(10),
            memory_size=256,
            environment={"TABLE_NAME": self.table.table_name},
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
