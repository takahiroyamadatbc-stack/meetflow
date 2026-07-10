"""Resource-naming helpers shared across stacks.

Some cross-stack wiring (Cognito -> Lambda invoke permission; see
MeetFlowAuthStack.add_post_confirmation_trigger and
MeetFlowComputeStack._grant_cognito_invoke) needs one stack to predict
another stack's resource name before a real construct reference exists, in
order to avoid a circular CloudFormation stack dependency. Centralizing the
naming convention here keeps the stacks that need to agree on it in sync.
"""


def user_lambda_function_name(env_name: str) -> str:
    return f"{env_name}-meetflow-user-lambda"
