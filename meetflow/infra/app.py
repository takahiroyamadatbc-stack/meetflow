#!/usr/bin/env python3
import os

import aws_cdk as cdk

from meetflow_infra.meetflow_api_stack import MeetFlowApiStack
from meetflow_infra.meetflow_auth_stack import MeetFlowAuthStack
from meetflow_infra.meetflow_compute_stack import MeetFlowComputeStack
from meetflow_infra.meetflow_data_stack import MeetFlowDataStack
from meetflow_infra.meetflow_frontend_stack import MeetFlowFrontendStack

app = cdk.App()

# AWSシステム構成設計書v1.2 §15に従い、単一アカウント内でのプレフィックス
# ベースの環境分離(dev / staging / prod)を行う。`cdk deploy -c env=prod`で
# 上書きできる。
env_name = app.node.try_get_context("env") or "dev"

# 招待URLのベースURL(CommunityLambdaのINVITE_BASE_URL環境変数に渡す)。
# `cdk deploy -c invite_base_url=https://xxxx.cloudfront.net/invite`で
# 指定する(DEPLOY.md手順4b参照)。未指定時はNoneのままcompute_stackに渡り、
# Lambda側のハードコードされたデフォルトにフォールバックする。
invite_base_url = app.node.try_get_context("invite_base_url")

env = cdk.Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT"),
    region=os.getenv("CDK_DEFAULT_REGION"),
)

data_stack = MeetFlowDataStack(
    app,
    f"{env_name}-MeetFlowDataStack",
    env_name=env_name,
    env=env,
    description="MeetFlow single-table DynamoDB stack (DynamoDB物理設計書v1.3 §3)",
)

auth_stack = MeetFlowAuthStack(
    app,
    f"{env_name}-MeetFlowAuthStack",
    env_name=env_name,
    env=env,
    description="MeetFlow Cognito User Pool stack (AWSシステム構成設計書v1.2 §5)",
)

compute_stack = MeetFlowComputeStack(
    app,
    f"{env_name}-MeetFlowComputeStack",
    env_name=env_name,
    table=data_stack.table,
    user_pool=auth_stack.user_pool,
    invite_base_url=invite_base_url,
    env=env,
    description="MeetFlow domain Lambda stack: shared Layer + UserLambda (Lambda設計書v1.1)",
)

# 両スタックが存在した後に配線する: これはUser Pool側のみを
# (constructの参照ではなく、予測したARN経由で)設定するので、
# compute_stackへの依存は無い -- MeetFlowAuthStack.
# add_post_confirmation_triggerを参照。
auth_stack.add_post_confirmation_trigger()

api_stack = MeetFlowApiStack(
    app,
    f"{env_name}-MeetFlowApiStack",
    env_name=env_name,
    user_pool=auth_stack.user_pool,
    user_lambda=compute_stack.user_lambda,
    community_lambda=compute_stack.community_lambda,
    availability_lambda=compute_stack.availability_lambda,
    matching_lambda=compute_stack.matching_lambda,
    event_lambda=compute_stack.event_lambda,
    result_lambda=compute_stack.result_lambda,
    notification_lambda=compute_stack.notification_lambda,
    feedback_lambda=compute_stack.feedback_lambda,
    env=env,
    description="MeetFlow REST API stack: API Gateway + Cognito Authorizer (API設計書v1.5)",
)

# 他スタックへの参照を持たないため、依存順という意味ではどのタイミングで
# デプロイしても良い。ビルド成果物のアップロードは別途手動(DEPLOY.md)。
frontend_stack = MeetFlowFrontendStack(
    app,
    f"{env_name}-MeetFlowFrontendStack",
    env_name=env_name,
    env=env,
    description="MeetFlow frontend delivery stack: S3 + CloudFront (AWSシステム構成設計書v1.3 §3-4)",
)

app.synth()
