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

# このスタックは、AWSシステム構成設計書v1.2 §5（認証）と、Lambda設計書v1.1
# §3のうちCognitoに関する部分を実装する。
#
# ドキュメントから引き継いでいる設計上のポイント：
#   - Cognitoが保持するのはメールアドレス＋パスワードのみ。ニックネーム／
#     プロフィール等はDynamoDB（MeetFlowDataStack）に置かれ、Post
#     Confirmationトリガー経由でUserLambdaが作成する（Lambda設計書v1.1
#     §3.1、F-001）。公開の`POST /users`エンドポイントは存在しない。
#   - JWT検証はAPI GatewayのCognito Authorizerで完結させ、独自のAuthLambda
#     は持たない（AWSシステム構成設計書v1.2 §5、§13）。ドメインLambdaは
#     eventを通じてすでに検証済みのクレームを受け取るのみ。
#   - 画面設計書v1.2 S-01はCognito Hosted UIではなく独自のメール／パスワード
#     画面のため、OAuth/Hosted UIドメインはここでは設定しない -- SPAは
#     SRP経由（例：Amplify/aws-sdk）でCognitoと直接やり取りする。
#
# UserLambdaは別スタック（MeetFlowComputeStack）に存在するため、Post
# Confirmationトリガーは、実際のクロススタックconstruct参照ではなく
# *予測した*Lambda ARNを使って`add_post_confirmation_trigger()`経由で
# 配線している。これはスタック間の循環依存を避けるためであり、理由の詳細は
# 同メソッドのdocstringを参照。


class MeetFlowAuthStack(Stack):
    """MeetFlowのCognito User Pool（メールアドレス／パスワード認証）用CDKスタック。"""

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

        # F-001: メールアドレス＋パスワードでの登録。ニックネームはCognito
        # の属性ではない（Lambda設計書v1.1 §3.1）-- Post Confirmation後に
        # UserLambdaがDynamoDBに作成するため、ここではカスタム属性を宣言
        # しない。
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
            # MVPでは確認コードの送信にCognito組み込みのメール送信機能を
            # 使う。SES連携（カスタムFROMアドレス、SPF/DKIM）が必要になる
            # のはPhase2の通知メールチャネル（AWSシステム構成設計書v1.2
            # §11）のみであり、Cognito自体の確認メールとは別の関心事。
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

        # 公開SPAクライアント（画面設計書v1.2：モバイルファーストのReact
        # SPA）。クライアントシークレットは無し -- ブラウザクライアントは
        # シークレットを機密に保てないため。SRPは、（Hosted UIではない）
        # 独自ログイン画面における標準的な安全なフロー。S-01はCognito
        # Hosted UIではなく独自のメール／パスワードフォームのため、OAuth
        # フローは設定しない。
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
        """UserLambdaのPost ConfirmationトリガーをこのUser Poolに配線する。

        UserLambda自体は別スタックであるMeetFlowComputeStackで構築される。
        そのスタックの実際のLambda constructをここで`add_trigger()`に渡す
        と、CDKがsynth時に拒否する*双方向*のクロススタック依存を強制する
        ことになる：
          - このUser PoolのLambdaConfigは、compute stackからUserLambdaの
            ARNをインポートする必要があり、かつ
          - `add_trigger()`は、Lambdaを呼び出すためのCognito許可も付与
            しようとするが、これはLambdaリソース自体（つまりcompute
            stack側）に、*この*User PoolのARNをスコープとしてアタッチ
            する必要がある。
        各スタックが互いから値をインポートする必要が生じ -- 循環になる。

        代わりに、対象のARNは共有の命名規則（`naming.
        user_lambda_function_name`）からここで*予測*しており、このスタック
        自身のaccount/regionトークンのみから構築している -- compute
        stackへの参照は一切無いため、配線のこちら側にはクロススタック依存
        が全く生じない。`add_trigger()`は、この予測／インポートした
        function参照に対しても呼び出し許可の付与を試みるが、これは無害な
        no-opになる（CDKは、ここで所有していないfunctionに許可をアタッチ
        できないため）-- 実際の許可は代わりにMeetFlowComputeStack側から
        付与され、そちらが実際のLambdaを所有し、このUser PoolのARNを
        一方向にインポートするだけで済む（そのスタックの
        `_grant_cognito_invoke`を参照）。

        サインアップがエンドツーエンドで動作するには、この命名規則に一致
        するfunction名でMeetFlowComputeStackが実際にデプロイされている
        必要がある -- このメソッド単体ではUser Pool側の設定しか行わない。
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

        # CDKは、この予測ARNへの`add_trigger`による自動`addPermission()`
        # 呼び出しが「効果を持たない」と警告する。未解決のトークンから
        # 構築したARNでは同一account/regionであることを証明できないため。
        # これは想定通りであり、この呼び出しで許可が作成されることは
        # 意図的に望んでいない（上記docstring参照）-- 実際の許可は、実
        # リソースを所有するMeetFlowComputeStackから付与される。
        Annotations.of(predicted_user_lambda).acknowledge_warning(
            "UnclearLambdaEnvironment"
        )
