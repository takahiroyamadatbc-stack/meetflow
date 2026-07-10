from aws_cdk import (
    CfnOutput,
    RemovalPolicy,
    Stack,
    aws_dynamodb as dynamodb,
    aws_kms as kms,
)
from constructs import Construct

# This stack implements DynamoDB物理設計書v1.3 §1-§3: a single DynamoDB table
# ("MeetFlowTable") shared by every entity in the system, using PK/SK prefixes
# to distinguish entity types, plus two overloaded GSIs (GSI1 "ByUser",
# GSI2 "ByAltId") that are likewise shared across entities.
#
# There is intentionally only ONE physical dynamodb.Table here — per §1 of the
# design doc, single-table design was chosen specifically to avoid RDB-style
# joins at this community scale (10-30 members). The comment block below
# enumerates every entity from §3 and the exact key attributes it uses, so
# that this table definition can be checked against the design doc entity by
# entity without missing one.
#
# Entity -> key structure (see DynamoDB物理設計書v1.3 §3 for full attribute
# lists):
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
#                           GSI1PK=COMMUNITY#{communityId}   GSI1SK=PLACE#{placeId}  (ownerType=COMMUNITY only)
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
#                           ttl={unix timestamp}  (only entity that populates the TTL attribute)
#   3.16 EventStatusHistory PK=EVENT#{eventId}               SK=STATUS#{createdAt}
#
# All of the above share the same physical attributes: PK, SK, GSI1PK, GSI1SK,
# GSI2PK, GSI2SK, ttl. No entity-specific attributes appear in the key
# schema itself (they are plain item attributes), so a single dynamodb.Table
# with this key schema and these two GSIs covers every entity in §3.


class MeetFlowDataStack(Stack):
    """CDK stack for MeetFlow's single-table DynamoDB design (v1.3)."""

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

        # DynamoDB物理設計書v1.3 §1: "暗号化：AWS所有キーではなくKMS". A
        # customer-managed key (rather than the AWS_MANAGED "aws/dynamodb"
        # key) is used so that key policy / IAM grants can be scoped per
        # domain Lambda later, matching the least-privilege IAM direction in
        # Lambda設計書v1.1 §12.2.
        self.table_key = kms.Key(
            self,
            "MeetFlowTableKey",
            alias=f"alias/{env_name}-meetflow-table",
            description="Customer-managed KMS key for MeetFlowTable encryption at rest",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY,
        )

        # DynamoDB物理設計書v1.3 §1: single table, on-demand capacity, PITR,
        # KMS encryption. AWSシステム構成設計書v1.2 §15: dev-/staging-/prod-
        # resource-name prefixing for environment separation.
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
            # Only OperationLog (§3.15) populates this attribute; DynamoDB
            # TTL only expires items that actually carry the attribute, so
            # every other entity is unaffected by declaring it table-wide.
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY,
            deletion_protection=is_prod,
        )

        # GSI1 "ByUser": overloaded across Membership, JoinRequest,
        # Availability, Place, Event, Participant, CandidateMember,
        # GameResult, Notification (PK-only, no GSI needed) and OperationLog.
        # ALL projection because the entities sharing this index need
        # different attribute sets returned (e.g. candidate score/members vs.
        # notification message), and community scale (10-30 members) makes
        # the extra storage/throughput cost of ALL negligible versus keeping
        # a second lookup per query.
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

        # GSI2 "ByAltId": direct ID lookup that bypasses the community
        # partition. Only MatchCandidate (§3.8) uses this today (candidate
        # detail lookup by candidateId alone), but it is defined at the table
        # level per the design doc's key-design overview (§2).
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
