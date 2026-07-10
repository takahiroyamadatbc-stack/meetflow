from aws_cdk import (
    Annotations,
    ArnFormat,
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_cognito as cognito,
    aws_lambda as lambda_,
)
from constructs import Construct

from .naming import user_lambda_function_name

# This stack implements AWSシステム構成設計書v1.2 §5 (認証) and the parts of
# Lambda設計書v1.1 §3 that concern Cognito.
#
# Design points carried over from the docs:
#   - Cognito holds ONLY email + password. Nickname/profile/etc. live in
#     DynamoDB (MeetFlowDataStack), created by UserLambda off the Post
#     Confirmation trigger (Lambda設計書v1.1 §3.1, F-001). There is no public
#     `POST /users` endpoint.
#   - JWT verification is done entirely by API Gateway's Cognito Authorizer;
#     there is no custom AuthLambda (AWSシステム構成設計書v1.2 §5, §13).
#     Domain Lambdas only receive already-verified claims via the event.
#   - 画面設計書v1.2 S-01 is a custom email/password screen, not Cognito
#     Hosted UI, so no OAuth/Hosted UI domain is configured here — the SPA
#     talks to Cognito directly via SRP (e.g. Amplify/aws-sdk).
#
# UserLambda lives in a separate stack (MeetFlowComputeStack), so the Post
# Confirmation trigger is wired via `add_post_confirmation_trigger()` using a
# *predicted* Lambda ARN rather than a real cross-stack construct reference,
# to avoid a circular stack dependency — see that method's docstring for why.


class MeetFlowAuthStack(Stack):
    """CDK stack for MeetFlow's Cognito User Pool (email/password auth)."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name
        is_prod = env_name == "prod"

        # F-001: email + password registration. Nickname is NOT a Cognito
        # attribute (Lambda設計書v1.1 §3.1) — it is created in DynamoDB by
        # UserLambda after Post Confirmation, so no custom attributes are
        # declared here.
        self.user_pool = cognito.UserPool(
            self,
            "MeetFlowUserPool",
            user_pool_name=f"{env_name}-meetflow-user-pool",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True, username=False),
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=True),
            ),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            # MVP uses Cognito's built-in email sending for verification
            # codes. SES integration (custom FROM address, SPF/DKIM) is only
            # required for the Phase2 notification-email channel
            # (AWSシステム構成設計書v1.2 §11), which is a separate concern
            # from Cognito's own verification emails.
            email=cognito.UserPoolEmail.with_cognito(),
            # 要件定義書24章「セキュリティ」に対する妥当な既定値。docs内に
            # 具体的なパスワードポリシーの規定はないため、一般的な安全な
            # 最低ラインを設定する。
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=False,
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY,
            deletion_protection=is_prod,
        )

        # Public SPA client (画面設計書v1.2: モバイルファーストのReact SPA).
        # No client secret — a browser client cannot keep one confidential.
        # SRP is the standard secure flow for a custom (non-Hosted-UI) login
        # screen; no OAuth flows are configured since S-01 is a custom
        # email/password form, not Cognito Hosted UI.
        self.user_pool_client = self.user_pool.add_client(
            "MeetFlowWebClient",
            user_pool_client_name=f"{env_name}-meetflow-web-client",
            generate_secret=False,
            auth_flows=cognito.AuthFlow(user_srp=True),
            prevent_user_existence_errors=True,
            access_token_validity=Duration.hours(1),
            id_token_validity=Duration.hours(1),
            refresh_token_validity=Duration.days(30),
        )

        CfnOutput(
            self,
            "UserPoolId",
            value=self.user_pool.user_pool_id,
            description="Cognito User Pool ID",
        )
        CfnOutput(
            self,
            "UserPoolArn",
            value=self.user_pool.user_pool_arn,
            description="Cognito User Pool ARN",
        )
        CfnOutput(
            self,
            "UserPoolClientId",
            value=self.user_pool_client.user_pool_client_id,
            description="Cognito User Pool Web Client ID",
        )

    def add_post_confirmation_trigger(self) -> None:
        """Wire UserLambda's Post Confirmation trigger onto this User Pool.

        UserLambda itself is built in MeetFlowComputeStack, a separate
        stack. Passing that stack's real Lambda construct into
        `add_trigger()` here would force a *two-way* cross-stack dependency
        that CDK refuses to synthesize:
          - this User Pool's LambdaConfig would need to import UserLambda's
            ARN from the compute stack, AND
          - `add_trigger()` also tries to grant Cognito permission to
            invoke the function, which must be attached to the Lambda
            resource itself (i.e. in the compute stack), scoped to *this*
            User Pool's ARN.
        Each stack would need to import a value from the other -- a cycle.

        Instead, the target ARN is *predicted* here from the shared naming
        convention (`naming.user_lambda_function_name`), built only from
        this stack's own account/region tokens -- no reference to the
        compute stack at all, so this half of the wiring has zero
        cross-stack dependency. `add_trigger()` will also try to grant an
        invoke permission on this predicted/imported function reference,
        which is a harmless no-op (CDK cannot attach permissions to a
        function it doesn't own here) -- the real permission is granted
        from MeetFlowComputeStack instead, which owns the actual Lambda and
        only needs a one-directional import of this User Pool's ARN (see
        that stack's `_grant_cognito_invoke`).

        MeetFlowComputeStack must actually be deployed, with a function name
        matching this convention, for sign-up to work end-to-end -- this
        method alone only configures the User Pool side.
        """
        predicted_arn = self.format_arn(
            service="lambda",
            resource="function",
            resource_name=user_lambda_function_name(self.env_name),
            arn_format=ArnFormat.COLON_RESOURCE_NAME,
        )
        predicted_user_lambda = lambda_.Function.from_function_arn(
            self, "UserLambdaPostConfirmationRef", predicted_arn
        )
        self.user_pool.add_trigger(
            cognito.UserPoolOperation.POST_CONFIRMATION, predicted_user_lambda
        )

        # CDK warns that `add_trigger`'s automatic `addPermission()` call on
        # this imported reference "has no effect", because it can't prove
        # same-account/region for an ARN built from unresolved tokens. That
        # is expected here -- we deliberately do NOT want this call to
        # create the permission (see docstring above); the real one is
        # granted from MeetFlowComputeStack, which owns the real resource.
        Annotations.of(predicted_user_lambda).acknowledge_warning(
            "UnclearLambdaEnvironment"
        )
