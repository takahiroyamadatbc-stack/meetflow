from pathlib import Path

from aws_cdk import (
    Annotations,
    BundlingOptions,
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_cognito as cognito,
    aws_dynamodb as dynamodb,
    aws_events as events,
    aws_events_targets as events_targets,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_secretsmanager as secretsmanager,
    aws_sqs as sqs,
)
from constructs import Construct

from .naming import user_lambda_function_name
from .webpush_layer_bundling import WebpushLayerLocalBundling

_BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"


class MeetFlowComputeStack(Stack):
    """MeetFlowのドメインLambda群のCDKスタック(Lambda設計書v1.1)。

    7ドメインLambda全て: 共有Layer(§12.1) + UserLambda(§3) +
    CommunityLambda(§4) + AvailabilityLambda(§5) + MatchingLambda(§6) +
    EventLambda(§7) + ResultLambda(§8) + NotificationLambda(§9)。
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        table: dynamodb.ITable,
        user_pool: cognito.IUserPool,
        invite_base_url: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # このスタックはMeetFlowDataStack(`table`)とMeetFlowAuthStack
        # (`user_pool`)の両方をクロススタック参照するため、CDKがデフォルトの
        # "strong"クロススタック参照エクスポート挙動について警告を出す。
        # cdk.jsonで`@aws-cdk/core:crossStackReferencesDefaultStrong`
        # contextフラグを設定するだけでは実際には抑止できなかったため、
        # CDK自身が出力した警告のidを使ってここで明示的にacknowledgeする --
        # そもそも"strong"(現在のデフォルト)はこのプロジェクトにとって
        # 正しい選択である: producer側のスタック(data/auth)が、この
        # consumerスタックを壊すような形で更新されることから守られる。
        Annotations.of(self).acknowledge_warning(
            "@aws-cdk/core:crossStackReferencesDefaultStrong"
        )

        self.env_name = env_name
        self.table = table
        self.invite_base_url = invite_base_url

        # Lambda設計書v1.1 §12.1: DynamoDBクライアント/クエリヘルパー、
        # メンバーシップ・権限チェック、OperationLogライター、共通エラー
        # レスポンスを、全ドメインLambdaで共有する。
        self.common_layer = lambda_.LayerVersion(
            self,
            "MeetFlowCommonLayer",
            layer_version_name=f"{env_name}-meetflow-common",
            code=lambda_.Code.from_asset(str(_BACKEND_DIR / "layers" / "common")),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_13],
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
        extra_layers: list = None,
        extra_environment: dict = None,
    ) -> lambda_.Function:
        """全ドメインLambdaに共通する組み立て処理: 同一ランタイム、
        `handler.handler`というエントリポイント規約、共通Layerのアタッチ、
        TABLE_NAME環境変数。個々の`_build_*_lambda`メソッドはこの上に
        自分自身のIAM grantを追加するだけでよい。`extra_layers`/
        `extra_environment`は、他の全ドメインの呼び出し箇所を変更せずに
        まれなドメイン固有Layer(例: NotificationLambdaのwebpush Layer)を
        扱うために存在する。
        """
        environment = {"TABLE_NAME": self.table.table_name}
        environment.update(extra_environment or {})
        # ロググループを明示的に作成し保持期間を設定する: 何も指定しないと
        # Lambdaが自動生成するロググループは無期限保持になり、地味にログが
        # 溜まり続ける(`log_retention`propは非推奨のためlog_groupを使う)。
        log_group = logs.LogGroup(
            self,
            f"{construct_id}LogGroup",
            log_group_name=f"/aws/lambda/{function_name}",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )
        return lambda_.Function(
            self,
            construct_id,
            function_name=function_name,
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="handler.handler",
            code=lambda_.Code.from_asset(str(_BACKEND_DIR / "functions" / code_subdir)),
            layers=[self.common_layer, *(extra_layers or [])],
            timeout=timeout or Duration.seconds(10),
            memory_size=memory_size,
            environment=environment,
            log_group=log_group,
        )

    def _build_user_lambda(self) -> lambda_.Function:
        fn = self._build_function(
            "UserLambda",
            # 明示的で予測可能な名前にする: MeetFlowAuthStackのPost
            # Confirmationトリガーは、循環クロススタック依存を避けるため
            # このスタックのconstructをimportせずに、この正確な名前を
            # (naming.py経由で)参照する(MeetFlowAuthStack.
            # add_post_confirmation_triggerを参照)。
            function_name=user_lambda_function_name(self.env_name),
            code_subdir="user_lambda",
        )

        # Lambda設計書v1.1 §3.3: PutItem(プロフィール作成のみ)、GetItem、
        # UpdateItemを、このテーブルに対するactionとしてスコープする。
        # 注意: DynamoDBの`dynamodb:LeadingKeys`というIAM条件は、
        # パーティションキーの完全一致のみをサポートする(典型的には
        # フェデレーテッド/Cognito Identity Pool認証情報によるID単位の
        # アクセスに使われる) -- Lambda実行ロールに対して"PK begins_with
        # USER#"という条件を表現することはできない。そのため、ここで
        # 強制可能なIAM境界はaction単位(DeleteItem/Query/Scanは許可しない)
        # に留まり、設計書が記述するPKプレフィックスによる分離は、IAMでは
        # なくこのLambda自身のコードによって強制される。
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
        # 招待URL(招待発行ハンドラーが返す文字列)のベースURL。独自ドメイン
        # (MVP時点では未取得)を前提にコード側でハードコードされている
        # フォールバック値の代わりに、実際にデプロイ済みのCloudFront
        # ドメイン(MeetFlowFrontendStackのCloudFrontDomainName出力)を
        # 使えるようにする。FrontendStackとは意図的にクロススタック参照を
        # 持たない設計(meetflow_frontend_stack.py参照)のため、値はCDK
        # contextで受け渡す(DEPLOY.md手順4bでCloudFrontドメイン確定後に
        # 再デプロイする運用)。未指定時はLambda側のハードコードされた
        # デフォルトにフォールバックする(cdk synth --allが認証情報無しで
        # 動くinfra-synth CIジョブの挙動は変えない)。
        community_extra_environment = (
            {"INVITE_BASE_URL": self.invite_base_url} if self.invite_base_url else None
        )
        fn = self._build_function(
            "CommunityLambda",
            function_name=f"{self.env_name}-meetflow-community-lambda",
            code_subdir="community_lambda",
            extra_environment=community_extra_environment,
        )

        # Lambda設計書v1.1 §4.3: Community, Membership, Invite, JoinRequest,
        # Place -- PutItem/GetItem/UpdateItem/Query、加えて参加リクエスト
        # 承認とOWNER移譲のためのTransactWriteItems(DynamoDB物理設計書
        # v1.3 §5)。Lambda設計書のこのLambdaに対するaction一覧には明示的に
        # 挙げられていないが、強制メンバー除名(F-104、要件定義書v1.2
        # §10.3)にはDeleteItemが必要。UserLambdaと同様、`dynamodb:
        # LeadingKeys`はLambda実行ロールに対して"PK begins_with
        # COMMUNITY#"を表現できないため、エンティティプレフィックスによる
        # 分離はIAMではなくこのLambda自身のコードによって強制される。
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

        # Lambda設計書v1.1 §5.3: AvailabilityのPK/SK + GSI1に対する
        # PutItem/BatchWriteItem/GetItem/UpdateItem/Query。TransactWriteItems
        # も必要(この実装判断より前に書かれた§5.3には列挙されていない):
        # 空き予定のstartTimeを編集するとSK/GSI1SKが変わり、DynamoDBの
        # アイテムキーはその場で更新できないため、このケースはatomicな
        # delete+recreateになる。
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

        # Lambda設計書v1.2 §5.3 [v1.2追加]: `events:PutEvents`
        # (`AvailabilityRequestCreated`発行用)。AvailabilityRequest自体は
        # Availabilityと同じテーブルの別PK/SKプレフィックスなので、上記の
        # DynamoDB権限に追加のgrantは不要。
        events.EventBus.grant_all_put_events(fn)

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
            # F-401の候補生成は、このLambdaが分離された理由である"重い"
            # 処理パス(Lambda設計書v1.1 §1, §6.4)なので、CRUD系の
            # ドメインLambdaよりタイムアウトを長く、メモリを多くしている。
            timeout=Duration.seconds(30),
            memory_size=512,
        )

        # Lambda設計書v1.1 §6.5: Query(Availability, EventTemplate)、
        # PutItem/GetItem/Query(MatchCandidate、GSI2含む)、
        # PutItem/UpdateItem/Query(CandidateMember、GSI1含む)。§6.5の
        # action一覧には挙げられていないが(CommunityLambdaのDeleteItemと
        # 同種のギャップ)、F-303/F-304(編集/削除)にはEventTemplateへの
        # UpdateItem/DeleteItemが必要。
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

        # §6.5: `CandidateConflictDetected`用の`events:PutEvents`。
        events.EventBus.grant_all_put_events(fn)

        # §6.1/§6.7: 事後的なダブルブッキング検知のため、(後でEventLambdaが
        # publishする)`EventConfirmed`を購読する。このruleはEventLambdaが
        # 存在する前に作成してもよい -- まだマッチする対象が無いだけである。
        # source/detail-type文字列はbackend/layers/common/python/
        # meetflow_common/events_bus.py(EVENT_SOURCE, EVENT_CONFIRMED)と
        # 一致していなければならない -- CDK(このファイル)とLambdaの
        # ランタイムコードは別のPython環境なので、このモジュールを直接
        # importすることはできない。
        # 処理が失敗し続けた場合にEventBridgeの既定リトライ(最大24時間)後
        # イベントがサイレントに消えるのを防ぐため、DLQに退避させる。この
        # ルールが担う事後的なダブルブッキング検知が黙って機能しなくなる
        # 事態を避けるための保険。
        matching_event_confirmed_dlq = sqs.Queue(
            self,
            "MatchingEventConfirmedDLQ",
            queue_name=f"{self.env_name}-meetflow-matching-event-confirmed-dlq",
            retention_period=Duration.days(14),
        )
        events.Rule(
            self,
            "MatchingEventConfirmedRule",
            rule_name=f"{self.env_name}-meetflow-matching-event-confirmed",
            event_pattern=events.EventPattern(
                source=["meetflow.events"], detail_type=["EventConfirmed"]
            ),
            targets=[
                events_targets.LambdaFunction(
                    fn, dead_letter_queue=matching_event_confirmed_dlq
                )
            ],
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

        # Lambda設計書v1.1 §7.4: Event, Participant(ダブルブッキング
        # チェック用のGSI1含む)、CancelRequest, EventStatusHistory --
        # PutItem/GetItem/UpdateItem/Query、TransactWriteItems(イベント
        # 確定用)。加えて、作成/確定時にcandidateIdを解決し使用済みとして
        # マークするためのMatchCandidate + CandidateMember(GSI2含む)への
        # 読み取り/更新アクセス、イベント詳細/一覧レスポンス用の
        # Place/Userへの読み取りアクセスも必要 -- 全て同一テーブルなので、
        # 他のドメインLambdaと同様、テーブルレベルのaction群としてまとめて
        # grantしている。
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

        # §7.4: EventConfirmed/EventCancelled/CancelApproved用の
        # `events:PutEvents`。
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

        # Lambda設計書v1.1 §8.4: PutItem/Query(GameSession, GameResult、
        # GSI1含む)。権限チェック用にEvent/Membershipのコンテキストを
        # 参照するため、GetItemも必要(§8.4には挙げられていない)。
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
        is_prod = self.env_name == "prod"
        vapid_secret_name = f"{self.env_name}-meetflow-vapid-keys"

        # Lambda設計書v1.2 §9.3b: Web Push送信には`pywebpush`(→`cryptography`
        # 等ネイティブ拡張)が必要。meetflow_common Layerはソースをそのまま
        # コピーするだけ(bundlingなし)なので、これらは専用の第2 Layerに
        # 分離し、Dockerを使わずmanylinuxホイールを直接pip installする
        # ローカルバンドリング(webpush_layer_bundling.py参照)で組み立てる。
        # image/commandはDocker環境向けの形だけのフォールバック(local側が
        # 常に成功するため実際には使われない)。
        webpush_layer = lambda_.LayerVersion(
            self,
            "MeetFlowWebpushLayer",
            layer_version_name=f"{self.env_name}-meetflow-webpush",
            code=lambda_.Code.from_asset(
                str(_BACKEND_DIR / "layers" / "webpush"),
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_13.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install -r requirements.txt -t /asset-output/python",
                    ],
                    local=WebpushLayerLocalBundling(
                        _BACKEND_DIR / "layers" / "webpush" / "requirements.txt"
                    ),
                ),
            ),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_13],
            description="pywebpush + cryptography for Web Push send (Lambda設計書v1.2 §9.3b)",
        )

        fn = self._build_function(
            "NotificationLambda",
            function_name=f"{self.env_name}-meetflow-notification-lambda",
            code_subdir="notification_lambda",
            extra_layers=[webpush_layer],
            extra_environment={
                "VAPID_SECRET_NAME": vapid_secret_name,
                # 実際の連絡先に差し替えること。VAPID仕様上必須(RFC8292)。
                "VAPID_SUBJECT": "mailto:admin@meetflow.jp",
            },
        )

        # Lambda設計書v1.2 §9.4: PutItem/Query/UpdateItem/DeleteItem
        # (Notification, PushSubscription [v1.2追加])。CandidateConflict
        # DetectedとAvailabilityRequestCreated向けにコミュニティの
        # member/OWNER/ADMINのuser idを解決するため、Membershipへの
        # Query(プライマリキー経由。新たなgrantは不要)も必要 -- 同一
        # テーブル・同一action群。
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

        # §9.1: 通知にファンアウトする全てのドメインイベントを購読する。
        # source/detail-type文字列はbackend/layers/common/python/
        # meetflow_common/events_bus.pyと一致していなければならない。
        # 同上の理由。こちらは通知そのものが飛ばなくなるため特に見過ごされ
        # やすい失敗モード -- DLQに退避させて可視化する。
        notification_domain_events_dlq = sqs.Queue(
            self,
            "NotificationDomainEventsDLQ",
            queue_name=f"{self.env_name}-meetflow-notification-domain-events-dlq",
            retention_period=Duration.days(14),
        )
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
                    "AvailabilityRequestCreated",
                ],
            ),
            targets=[
                events_targets.LambdaFunction(
                    fn, dead_letter_queue=notification_domain_events_dlq
                )
            ],
        )

        # Lambda設計書v1.2 §9.3b/9.4, 未決事項7: Web PushのVAPID鍵ペア置き場。
        # 鍵の実際の生成・投入(aws secretsmanager put-secret-value等)は
        # 開発者がデプロイ後に別途行う運用とし、ここではSecretリソースと
        # NotificationLambdaへの読み取り権限のみを用意する。値は
        # {"vapidPrivateKey": "<base64url>", "vapidPublicKey": "<base64url>"}
        # 形式のJSON(生の鍵文字列。PEMそのものではなくbase64url表現。
        # push_sender.py参照)を投入する前提のプレースホルダー。
        vapid_keys_secret = secretsmanager.Secret(
            self,
            "VapidKeysSecret",
            secret_name=vapid_secret_name,
            description=(
                "Web Push用VAPID鍵ペア(公開鍵/秘密鍵)。デプロイ後に手動で"
                "生成・投入するプレースホルダー。"
            ),
            removal_policy=RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY,
        )
        vapid_keys_secret.grant_read(fn)

        CfnOutput(
            self,
            "NotificationLambdaArn",
            value=fn.function_arn,
            description="NotificationLambda function ARN",
        )
        CfnOutput(
            self,
            "VapidKeysSecretName",
            value=vapid_keys_secret.secret_name,
            description="Web Push VAPID鍵ペアを投入するSecrets Managerシークレット名",
        )
        return fn

    def _grant_cognito_invoke(self, user_pool: cognito.IUserPool) -> None:
        """Post ConfirmationトリガーとしてUserLambdaを起動する権限をCognitoに
        付与する。

        これはMeetFlowAuthStack.add_post_confirmation_triggerで説明されている
        配線のもう半分にあたる: このスタックが実際のLambdaリソースを
        所有しているため、AWS::Lambda::Permissionはここで作成しなければ
        ならない。必要なのはUser PoolのARNの一方向のimportのみ(このスタックは
        `user_pool`コンストラクタ引数経由で、既にUser Poolオブジェクト
        自体についてMeetFlowAuthStackに依存している)なので、循環は
        発生しない。
        """
        self.user_lambda.add_permission(
            "AllowCognitoInvokePostConfirmation",
            principal=iam.ServicePrincipal("cognito-idp.amazonaws.com"),
            action="lambda:InvokeFunction",
            source_arn=user_pool.user_pool_arn,
        )
