from pathlib import Path

from aws_cdk import (
    Annotations,
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_apigateway as apigateway,
    aws_cognito as cognito,
    aws_dynamodb as dynamodb,
    aws_lambda as lambda_,
    aws_logs as logs,
)
from constructs import Construct

# Mリーグドラフト企画（docs/draft/DESIGN.md）のスタック。
#
# §4.11「配置（完全分離）」の通り、この企画に必要なリソースはすべてこの
# 1スタックに閉じ込める。既存5スタック（data / auth / compute / api /
# frontend）のコードは一切変更しない。撤退するときは
# `cdk destroy {env}-MeetFlowDraftStack` でテーブルごと消える。
#
# 分離している理由（§4.11）:
#   1. 撤退可能性 -- gitのブランチはコードしか戻さない。デプロイ済みの
#      インフラを消すにはスタックごと落とす必要がある
#   2. 本体の設計の純度 -- READMEで押している単一テーブル設計・事前に
#      洗い出したアクセスパターンを守る。ドラフトはアクセスパターンの
#      性質が全く違う（短命・イベント的・数秒間隔で状態が変わる）
#
# 例外は2つだけで、どちらも「参照するだけ」:
#   - Cognito User Pool（本体と同じログインを使う。§4.13）
#   - 本体テーブルの**読み取り**（Membership確認と表示名解決。§4.13）
#     書き込みは一切しない。DraftLambdaが書くのはDraftTableだけ。
#
# 共通Layerは本体（MeetFlowComputeStack）のLayerVersionを参照せず、同じ
# ソースから自前でもう1つ作る。参照するとcomputeスタックへの依存が生まれ、
# 撤退時に効いてくるため -- 数MBの重複はその対価として安い。
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "backend"


class MeetFlowDraftStack(Stack):
    """Mリーグドラフト企画のCDKスタック（DESIGN.md §4.11）。"""

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

        # MeetFlowComputeStackと同じ理由でacknowledgeする（data/authスタックを
        # クロススタック参照するため）。"strong"参照のままで問題ない --
        # 壊れて困るのはproducer側の更新であって、このconsumerを単体で
        # destroyする分には妨げにならない。
        Annotations.of(self).acknowledge_warning(
            "@aws-cdk/core:crossStackReferencesDefaultStrong"
        )

        self.env_name = env_name
        is_prod = env_name == "prod"

        # DESIGN.md §5のキー設計。本体とは別テーブルなので単一テーブル設計の
        # 制約には縛られないが、エンティティの持ち方は本体と揃えておく。
        #
        #   Draft            PK=DRAFT#{draftId}   SK=METADATA
        #                    GSI1PK=COMMUNITY#{communityId}
        #   DraftParticipant PK=DRAFT#{draftId}   SK=PARTICIPANT#{userId}
        #                    GSI1PK=USER#{userId}
        #   DraftPlayer      PK=DRAFT#{draftId}   SK=PLAYER#{playerId}
        #   DraftPick        PK=DRAFT#{draftId}   SK=PICK#{round}#{wave}#{userId}
        #   DraftRoster      PK=DRAFT#{draftId}   SK=ROSTER#{userId}#{playerId}
        #   PlayerLock       PK=DRAFT#{draftId}   SK=LOCK#{playerId}
        #   LotteryLog       PK=DRAFT#{draftId}   SK=LOTTERY#{round}#{wave}#{seq}
        #   MLPlayer         PK=MLPLAYER#{season} SK=PLAYER#{playerId}
        #
        # 暗号化は本体テーブルのようなカスタマー管理キーではなくAWS管理キーに
        # した。本体でCMKを選んだ理由は「key policy / IAM grantをドメイン
        # Lambdaごとにスコープできるようにする」ことだったが、このテーブルの
        # 利用者はDraftLambda 1つだけで、スコープを分ける相手がいない。
        self.table = dynamodb.Table(
            self,
            "MeetFlowDraftTable",
            table_name=f"{env_name}-MeetFlowDraftTable",
            partition_key=dynamodb.Attribute(
                name="PK", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(name="SK", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=is_prod
            ),
            removal_policy=RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY,
            deletion_protection=is_prod,
        )
        # GSI1: コミュニティのドラフト一覧（COMMUNITY#）と、ユーザーが参加して
        # いるドラフト（USER#）の2用途でオーバーロードする。
        self.table.add_global_secondary_index(
            index_name="GSI1",
            partition_key=dynamodb.Attribute(
                name="GSI1PK", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="GSI1SK", type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        self.draft_lambda = self._build_draft_lambda(table)
        self.api = self._build_api(user_pool)

        CfnOutput(
            self,
            "DraftTableName",
            value=self.table.table_name,
            description="MeetFlowDraftTable name",
        )
        CfnOutput(
            self,
            "DraftApiUrl",
            value=self.api.url,
            description="Draft API endpoint (frontend VITE_DRAFT_API_BASE_URL)",
        )

    def _build_draft_lambda(self, main_table: dynamodb.ITable) -> lambda_.Function:
        common_layer = lambda_.LayerVersion(
            self,
            "DraftCommonLayer",
            layer_version_name=f"{self.env_name}-meetflow-draft-common",
            code=lambda_.Code.from_asset(str(_BACKEND_DIR / "layers" / "common")),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_13],
            description="Copy of the shared MeetFlow helpers, owned by the draft stack",
        )
        function_name = f"{self.env_name}-meetflow-draft-lambda"
        log_group = logs.LogGroup(
            self,
            "DraftLambdaLogGroup",
            log_group_name=f"/aws/lambda/{function_name}",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )
        draft_lambda = lambda_.Function(
            self,
            "DraftLambda",
            function_name=function_name,
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="handler.handler",
            code=lambda_.Code.from_asset(str(_BACKEND_DIR / "functions" / "draft_lambda")),
            layers=[common_layer],
            timeout=Duration.seconds(10),
            memory_size=512,
            environment={
                # 本体テーブル。meetflow_common.get_table()が読む。
                "TABLE_NAME": main_table.table_name,
                # ドラフト専用テーブル。draft_table.get_draft_table()が読む。
                "DRAFT_TABLE_NAME": self.table.table_name,
            },
            log_group=log_group,
        )
        self.table.grant_read_write_data(draft_lambda)
        # DESIGN.md §4.13: 本体テーブルは読むだけ。Membershipの確認と表示名の
        # 解決にしか使わないため、書き込み権限は与えない。
        main_table.grant_read_data(draft_lambda)
        return draft_lambda

    def _build_api(self, user_pool: cognito.IUserPool) -> apigateway.RestApi:
        """ドラフト専用のAPI Gateway（DESIGN.md §4.11）。

        本体のMeetFlowApiStackにルートを足すと、撤退時にそちらを触ることに
        なるため専用に立てる。Authorizerは本体と同じUser Poolを参照するだけ
        なので、フロントエンドは同じトークンをそのまま使える。
        """
        access_log_group = logs.LogGroup(
            self,
            "DraftApiAccessLogGroup",
            log_group_name=f"/aws/apigateway/{self.env_name}-meetflow-draft-api-access",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )
        api = apigateway.RestApi(
            self,
            "MeetFlowDraftApi",
            rest_api_name=f"{self.env_name}-meetflow-draft-api",
            endpoint_types=[apigateway.EndpointType.REGIONAL],
            # `AWS::ApiGateway::Account`（アクセスログ用のCloudWatch書き込み
            # ロール）はアカウント×リージョンに1つしか存在できないシングル
            # トンで、本体のMeetFlowApiStackが既に作っている。ここでも作ると
            # 2スタックが同じアカウント設定を取り合い、先にデプロイした方の
            # ロールを後から上書きしたり、片方をdestroyしたときにもう片方の
            # アクセスログが止まったりする。既存のものに相乗りする。
            cloud_watch_role=False,
            deploy_options=apigateway.StageOptions(
                stage_name=self.env_name,
                # ドラフト中は参加者全員が数秒間隔でGET /drafts/{id}を叩く
                # （DESIGN.md §4.12のポーリング）。10人×2秒間隔でも5rps程度
                # だが、本体APIと同じ水準の余裕を持たせておく。
                throttling_rate_limit=50,
                throttling_burst_limit=100,
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
                allow_origins=apigateway.Cors.ALL_ORIGINS,
                allow_methods=apigateway.Cors.ALL_METHODS,
                allow_headers=["Content-Type", "Authorization"],
            ),
        )
        authorizer = apigateway.CognitoUserPoolsAuthorizer(
            self, "DraftCognitoAuthorizer", cognito_user_pools=[user_pool]
        )
        # 本体APIスタックと同じく、(method, path)は
        # backend/functions/draft_lambda/handler.py の _ROUTES から一字一句
        # そのまま取っている。
        routes = [
            ("POST", "/communities/{communityId}/drafts"),
            ("GET", "/communities/{communityId}/drafts"),
            ("GET", "/drafts/{draftId}"),
            ("GET", "/drafts/{draftId}/rosters"),
            ("GET", "/drafts/{draftId}/players"),
            ("GET", "/drafts/{draftId}/lotteries"),
            ("POST", "/drafts/{draftId}/start"),
            ("POST", "/drafts/{draftId}/picks"),
            ("POST", "/drafts/{draftId}/picks/proxy"),
            ("POST", "/drafts/{draftId}/reveal"),
            ("POST", "/drafts/{draftId}/lottery"),
            ("POST", "/drafts/{draftId}/advance"),
        ]
        # allow_test_invoke=False: 本体APIスタックと同じ理由。メソッドごとに
        # Lambda::Permissionが倍増してリソースポリシーの上限に近づくのを避ける。
        integration = apigateway.LambdaIntegration(
            self.draft_lambda, allow_test_invoke=False
        )
        resource_cache: dict[str, apigateway.IResource] = {"": api.root}

        def _resource_for_path(path: str) -> apigateway.IResource:
            if path in resource_cache:
                return resource_cache[path]
            parent_path, _, part = path.rpartition("/")
            parent = _resource_for_path(parent_path)
            existing = parent.get_resource(part)
            resource = existing if existing is not None else parent.add_resource(part)
            resource_cache[path] = resource
            return resource

        for method, path in routes:
            _resource_for_path(path).add_method(
                method,
                integration,
                authorization_type=apigateway.AuthorizationType.COGNITO,
                authorizer=authorizer,
            )
        return api
