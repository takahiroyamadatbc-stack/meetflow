from aws_cdk import (
    CfnOutput,
    RemovalPolicy,
    Stack,
    aws_budgets as budgets,
    aws_dynamodb as dynamodb,
    aws_kms as kms,
)
from constructs import Construct

# このスタックはDynamoDB物理設計書v1.3 §1-§3を実装する: システム内の
# 全エンティティが共有する単一のDynamoDBテーブル("MeetFlowTable")で、
# PK/SKプレフィックスによってエンティティ種別を区別し、加えて同様に
# エンティティ間で共有される2本のオーバーロードGSI(GSI1 "ByUser"、
# GSI2 "ByAltId")を持つ。
#
# ここに物理的なdynamodb.Tableが意図的に1つしか無いのは、設計書§1に
# 従い、このコミュニティ規模(10-30人)ではRDB的なjoinを避けるために
# 単一テーブル設計を選んだためである。以下のコメントブロックは§3の
# 全エンティティと、それぞれが使う正確なキー属性を列挙しており、この
# テーブル定義を設計書とエンティティごとに漏れなく突き合わせられるように
# している。
#
# エンティティ -> キー構造(全属性一覧はDynamoDB物理設計書v1.3 §3を参照):
#
#   3.1  User              PK=USER#{userId}                SK=PROFILE
#   3.2  Community          PK=COMMUNITY#{communityId}       SK=METADATA
#   3.3  Membership         PK=COMMUNITY#{communityId}       SK=MEMBER#{userId}
#                           GSI1PK=USER#{userId}             GSI1SK=COMMUNITY#{communityId}
#   3.4  Invite             PK=INVITE#{token}                SK=METADATA
#   3.5  JoinRequest        PK=COMMUNITY#{communityId}       SK=JOINREQ#{userId}
#                           GSI1PK=USER#{userId}             GSI1SK=JOINREQ#{communityId}
#   3.6  Availability       PK=COMMUNITY#{communityId}       SK=AVAIL#{startTime}#{availabilityId}
#                           GSI1PK=USER#{userId}             GSI1SK=AVAIL#{startTime}
#   3.7  EventTemplate      PK=COMMUNITY#{communityId}       SK=TEMPLATE#{templateId}
#   3.8  MatchCandidate     PK=COMMUNITY#{communityId}       SK=CANDIDATE#{createdAt}#{candidateId}
#                           GSI2PK=CANDIDATE#{candidateId}   GSI2SK=METADATA
#   3.9  Place              PK=PLACE#{placeId}               SK=METADATA
#                           GSI1PK=COMMUNITY#{communityId}   GSI1SK=PLACE#{placeId}  (ownerType=COMMUNITYの場合のみ)
#   3.10 Event              PK=EVENT#{eventId}               SK=METADATA
#                           GSI1PK=COMMUNITY#{communityId}   GSI1SK=EVENT#{startTime}#{eventId}
#   3.11 Participant        PK=EVENT#{eventId}               SK=PARTICIPANT#{userId}
#                           GSI1PK=USER#{userId}             GSI1SK=PARTICIPANT#{startTime}#{eventId}
#   3.11b CandidateMember   PK=COMMUNITY#{communityId}       SK=CANDIDATE#{candidateId}#MEMBER#{userId}
#                           GSI1PK=USER#{userId}             GSI1SK=CANDIDATE#{startTime}#{candidateId}
#   3.12 CancelRequest      PK=EVENT#{eventId}               SK=CANCELREQ#{userId}
#   3.13 GameSession        PK=EVENT#{eventId}               SK=SESSION#{sessionNo}
#        GameResult         PK=EVENT#{eventId}               SK=SESSION#{sessionNo}#RESULT#{userId}
#                           GSI1PK=USER#{userId}             GSI1SK=COMMUNITY#{communityId}#{playedAt}
#   3.14 Notification       PK=USER#{userId}                 SK=NOTIF#{createdAt}#{notificationId}
#   3.15 OperationLog       PK=LOG#{communityId}              SK={createdAt}#{logId}
#                           GSI1PK=USER#{userId}             GSI1SK=LOG#{createdAt}#{logId}
#                           ttl={unix timestamp}  (TTL属性を実際に持つのはこのエンティティのみ)
#   3.16 EventStatusHistory PK=EVENT#{eventId}               SK=STATUS#{createdAt}
#
# 上記は全て同じ物理属性(PK, SK, GSI1PK, GSI1SK, GSI2PK, GSI2SK, ttl)を
# 共有する。キースキーマ自体にはエンティティ固有の属性は一切現れない
# (それらは単なるアイテム属性である)ため、このキースキーマと2本のGSIを
# 持つ単一のdynamodb.Tableで、§3の全エンティティをカバーできる。


class MeetFlowDataStack(Stack):
    """MeetFlowの単一テーブルDynamoDB設計(v1.3)のCDKスタック。"""

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

        # DynamoDB物理設計書v1.3 §1: "暗号化：AWS所有キーではなくKMS"。
        # (AWS_MANAGEDの"aws/dynamodb"キーではなく)カスタマー管理キーを
        # 使うことで、後からkey policy / IAM grantをドメインLambdaごとに
        # スコープできるようにし、Lambda設計書v1.1 §12.2の最小権限方針に
        # 合わせている。
        self.table_key = kms.Key(
            self,
            "MeetFlowTableKey",
            alias=f"alias/{env_name}-meetflow-table",
            description="Customer-managed KMS key for MeetFlowTable encryption at rest",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY,
        )

        # DynamoDB物理設計書v1.3 §1: 単一テーブル、オンデマンドキャパシティ、
        # PITR、KMS暗号化。AWSシステム構成設計書v1.2 §15: 環境分離のための
        # dev-/staging-/prod-リソース名プレフィックス。
        self.table = dynamodb.Table(
            self,
            "MeetFlowTable",
            table_name=f"{env_name}-MeetFlowTable",
            partition_key=dynamodb.Attribute(
                name="PK", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="SK", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=self.table_key,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            ),
            # この属性を実際に持つのはOperationLog(§3.15)のみ。DynamoDBの
            # TTLはその属性を実際に持つアイテムしか失効させないため、
            # テーブル全体でこれを宣言しても他のエンティティには影響しない。
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY,
            deletion_protection=is_prod,
        )

        # GSI1「ByUser」: Membership, JoinRequest, Availability, Place,
        # Event, Participant, CandidateMember, GameResult, Notification
        # (PKのみでGSI不要)、OperationLogにまたがってオーバーロードされる。
        # このインデックスを共有するエンティティはそれぞれ異なる属性集合
        # (例: 候補のスコア/メンバー vs. 通知メッセージ)を返す必要があり、
        # かつコミュニティ規模(10-30人)ではALLプロジェクションの追加の
        # ストレージ/スループットコストは、クエリごとに2回目のlookupを
        # 行うコストに比べて無視できるため、ALLプロジェクションとする。
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

        # GSI2 "ByAltId": コミュニティのパーティションを介さない直接ID
        # lookup。現時点で使っているのはMatchCandidate(§3.8)のみ
        # (candidateId単独での候補詳細lookup)だが、設計書のキー設計
        # 概要(§2)に従い、テーブルレベルで定義している。
        self.table.add_global_secondary_index(
            index_name="GSI2",
            partition_key=dynamodb.Attribute(
                name="GSI2PK", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="GSI2SK", type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        CfnOutput(
            self,
            "TableName",
            value=self.table.table_name,
            description="MeetFlowTable name",
        )
        CfnOutput(
            self,
            "TableArn",
            value=self.table.table_arn,
            description="MeetFlowTable ARN",
        )
        CfnOutput(
            self,
            "TableKeyArn",
            value=self.table_key.key_arn,
            description="KMS key ARN used for MeetFlowTable encryption",
        )

        # AWS Budgetsによる課金アラート(アカウント単位、月次)。誤操作や
        # バグ由来の課金急増(例: EventBridgeの無限リトライ等)に気づく
        # 仕組みがそれまで無かったための保険。予算自体はスタック固有の
        # 概念ではなくアカウント全体の実費用を見るものだが、他に専用の
        # 置き場が無いため一番手前にデプロイされるこのスタックに置く。
        # 複数環境(dev/staging/prod)を同一アカウントに同時デプロイする
        # 場合、それぞれが同名でない限り重複した予算が並立するだけで
        # 衝突はしない(`budget_name`をenv_nameで一意にしているため)。
        budgets.CfnBudget(
            self,
            "AccountCostBudget",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_name=f"{env_name}-meetflow-monthly-cost-budget",
                budget_type="COST",
                time_unit="MONTHLY",
                budget_limit=budgets.CfnBudget.SpendProperty(
                    amount=10, unit="USD"
                ),
            ),
            notifications_with_subscribers=[
                budgets.CfnBudget.NotificationWithSubscribersProperty(
                    notification=budgets.CfnBudget.NotificationProperty(
                        notification_type="ACTUAL",
                        comparison_operator="GREATER_THAN",
                        threshold=100,
                        threshold_type="PERCENTAGE",
                    ),
                    subscribers=[
                        budgets.CfnBudget.SubscriberProperty(
                            subscription_type="EMAIL",
                            address="takahiro.yamada1221@gmail.com",
                        )
                    ],
                )
            ],
        )
