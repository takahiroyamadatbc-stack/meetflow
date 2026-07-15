from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_s3 as s3,
)
from constructs import Construct

# このスタックはAWSシステム構成設計書v1.3 §3-4を実装する:
# `User → CloudFront → S3 (React SPA)` の配信経路。
#
# MVP検証時点では独自ドメインを持たないため、Route53/ACMは意図的に
# 含めていない(CloudFrontの既定ドメイン `*.cloudfront.net` をそのまま
# 使う)。独自ドメインを取得したら、このスタックにACM証明書(us-east-1
# 必須)とRoute53のAレコード(Alias)を追加する形で拡張する想定。
#
# ビルド成果物(frontend/dist)のアップロードは、あえてCDKの
# BucketDeploymentを使わずスタック定義から外している。理由は2つ:
#   1. frontend/.env.development はMeetFlowAuthStack/MeetFlowApiStackの
#      CfnOutputを転記して作る値を含むため、frontend/distの生成は
#      必然的にバックエンド4スタックのデプロイ後になる。BucketDeployment
#      はCDKアセットとしてsynth時にfrontend/distの実在を要求するため、
#      これを使うとバックエンドと同じ`cdk deploy --all`実行に
#      frontend/distの事前ビルドが暗黙の前提になってしまう。
#   2. .github/workflows/ci.yml の infra-synth ジョブは
#      `cdk synth --all` をfrontend/dist抜きのクリーンチェックアウトで
#      実行しており、BucketDeploymentを入れるとそこが壊れる。
#   アップロードは `aws s3 sync` + `aws cloudfront create-invalidation`
#   による手動デプロイ手順(DEPLOY.md)側の責務とする。


class MeetFlowFrontendStack(Stack):
    """フロントエンド配信(S3 + CloudFront)のCDKスタック。"""

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

        # バケットへの直接アクセスは許可せず、CloudFront(OAC経由)からの
        # みアクセス可能にする。静的サイトホスティング機能(website
        # hosting)は使わず、通常のプライベートバケット+OACとする方が
        # パブリックアクセスの経路が生まれず安全。
        self.bucket = s3.Bucket(
            self,
            "FrontendBucket",
            bucket_name=f"{env_name}-meetflow-frontend",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY,
            auto_delete_objects=not is_prod,
        )

        # SPA(React Router)のクライアントサイドルーティングに対応する
        # ため、S3が返す403/404を index.html + 200 に読み替える。
        # 未知パスへの直接アクセス(例: リロード時の /communities/xxx)を
        # 素通しでルーターに処理させるための設定。
        distribution = cloudfront.Distribution(
            self,
            "FrontendDistribution",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(
                    self.bucket
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.seconds(0),
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.seconds(0),
                ),
            ],
            # MVP規模・日本国内ユーザー想定のため、コストが最も低い
            # PRICE_CLASS_100(北米・欧州のみ)で十分。将来的にユーザー
            # 層が広がれば見直す。
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,
        )
        self.distribution = distribution

        CfnOutput(
            self,
            "FrontendBucketName",
            value=self.bucket.bucket_name,
            description="フロントエンドビルド成果物をアップロードするS3バケット名(aws s3 sync先)",
        )
        CfnOutput(
            self,
            "CloudFrontDomainName",
            value=f"https://{distribution.domain_name}",
            description="MeetFlowフロントエンドのURL(CloudFront既定ドメイン)",
        )
        CfnOutput(
            self,
            "CloudFrontDistributionId",
            value=distribution.distribution_id,
            description="デプロイ後のキャッシュ無効化(aws cloudfront create-invalidation)に使うDistribution ID",
        )
