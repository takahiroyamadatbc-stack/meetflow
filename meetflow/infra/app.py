#!/usr/bin/env python3
import os

import aws_cdk as cdk

from meetflow_infra.meetflow_auth_stack import MeetFlowAuthStack
from meetflow_infra.meetflow_compute_stack import MeetFlowComputeStack
from meetflow_infra.meetflow_data_stack import MeetFlowDataStack

app = cdk.App()

# Single-account, prefix-based environment separation (dev / staging / prod),
# per AWSシステム構成設計書v1.2 §15. Override with `cdk deploy -c env=prod`.
env_name = app.node.try_get_context("env") or "dev"

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
    env=env,
    description="MeetFlow domain Lambda stack: shared Layer + UserLambda (Lambda設計書v1.1)",
)

# Wired after both stacks exist: this only configures the User Pool side
# (via a predicted ARN, not a construct reference), so it has no dependency
# on compute_stack -- see MeetFlowAuthStack.add_post_confirmation_trigger.
auth_stack.add_post_confirmation_trigger()

app.synth()
