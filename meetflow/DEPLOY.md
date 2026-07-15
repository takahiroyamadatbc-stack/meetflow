# MeetFlow 手動デプロイ手順（dev環境）

MVP検証のための手動デプロイ手順。CD（GitHub Actionsからの自動デプロイ）は現時点ではスコープ外で、`cdk deploy`をローカルから手動実行する運用（詳細はCLAUDE.mdの「CI/CD」節を参照）。

## 前提

- AWS CLI 2.x、CDK CLI 2.xがインストール済み
- SSOプロファイル`personal`が`~/.aws/config`に設定済み（account `569239323423`、region `ap-northeast-1`、`AdministratorAccess`ロール）
- `infra/.venv`（`infra/requirements.txt`）、`backend/.venv`（`backend/requirements-dev.txt`）が構築済み

以降のコマンドはPowerShellを想定。作業ディレクトリはリポジトリルート（`meetflow/`）から相対で示す。

## 1. AWS認証

```powershell
aws sso login --profile personal
aws sts get-caller-identity --profile personal   # 認証確認
```

以降、`--profile personal`を都度付けるか、`$env:AWS_PROFILE = "personal"`で省略可能。

## 2. cdk bootstrap（対象アカウント/リージョンに対して初回のみ）

```powershell
cd infra
$env:PATH = "$(Resolve-Path .venv\Scripts);" + $env:PATH
cdk bootstrap aws://569239323423/ap-northeast-1 --profile personal
```

CDKデプロイに必要なS3バケット・IAMロール等（`CDKToolkit`スタック）が作成される。アカウント/リージョンごとに一度だけでよい。

## 3. バックエンド4スタック＋FrontendStackのデプロイ

```powershell
cdk deploy --all -c env=dev --profile personal
```

`DataStack → AuthStack → ComputeStack → ApiStack`はスタック間参照（DynamoDB Table / Cognito UserPool）に基づきCDKが自動で依存順にデプロイする。`FrontendStack`（S3 + CloudFront）は他スタックへの参照を持たないため、デプロイ順に制約はない。

IAMロール変更を伴うため、途中で `Do wish to deploy these changes (y/n)?` と確認を求められる。**初回は内容を確認してから`y`とすること**（`--require-approval never`は使わない）。

`FrontendStack`だけを個別にデプロイしたい場合は `cdk deploy dev-MeetFlowFrontendStack -c env=dev --profile personal` でも良い（手順7参照）。

## 4. デプロイ結果を控える

以下を後続手順で使用する。

| 値 | 取得元（スタック名 / 出力キー） |
|---|---|
| API Gateway URL | `dev-MeetFlowApiStack` / `ApiUrl` |
| Cognito User Pool ID | `dev-MeetFlowAuthStack` / `UserPoolId` |
| Cognito User Pool Client ID | `dev-MeetFlowAuthStack` / `UserPoolClientId` |
| フロントエンドS3バケット名 | `dev-MeetFlowFrontendStack` / `FrontendBucketName` |
| CloudFront Distribution ID | `dev-MeetFlowFrontendStack` / `CloudFrontDistributionId` |
| フロントエンドURL | `dev-MeetFlowFrontendStack` / `CloudFrontDomainName` |

`cdk deploy`実行時のターミナル出力にも表示されるが、後から確認する場合：

```powershell
aws cloudformation describe-stacks --stack-name dev-MeetFlowAuthStack --profile personal --query "Stacks[0].Outputs"
aws cloudformation describe-stacks --stack-name dev-MeetFlowApiStack --profile personal --query "Stacks[0].Outputs"
aws cloudformation describe-stacks --stack-name dev-MeetFlowFrontendStack --profile personal --query "Stacks[0].Outputs"
```

## 5. VAPID鍵ペアの生成・投入

`backend/.venv`には`pywebpush`の依存として`py-vapid`が入っており、そのCLI（`vapid`）で鍵ペアを生成できる。

```powershell
cd backend
.venv\Scripts\vapid --gen --json --applicationServerKey
```

`private_key.pem`・`public_key.pem`がカレントディレクトリに生成され、`vapidPublicKey`にあたるbase64url値（`Application Server Key`）がターミナルに表示される。

`vapidPrivateKey`（base64url・raw形式。pywebpushが`Vapid.from_string`で読める形式）は、生成された`private_key.pem`から以下で変換する：

```powershell
.venv\Scripts\python -c "import base64; from py_vapid import Vapid01; v = Vapid01.from_file('private_key.pem'); raw = v.private_key.private_numbers().private_value.to_bytes(32, 'big'); print(base64.urlsafe_b64encode(raw).rstrip(b'=').decode())"
```

得られた2つの値を、CDKが作成済みのSecrets Managerシークレット（名前固定：`dev-meetflow-vapid-keys`）に投入する：

```powershell
aws secretsmanager put-secret-value --secret-id dev-meetflow-vapid-keys --profile personal --secret-string '{\"vapidPrivateKey\":\"<上で得たprivate値>\",\"vapidPublicKey\":\"<Application Server Keyの値>\"}'
```

投入後、`private_key.pem`・`public_key.pem`はローカルに残さず削除すること（秘密鍵はSecrets Managerにのみ保管する）。

## 6. フロントエンドの環境変数設定・ビルド

[frontend/.env.example](frontend/.env.example)をコピーして`frontend/.env.development`を作成し、手順4で得た値を転記する：

```
VITE_API_BASE_URL=<手順4のApiUrl>
VITE_COGNITO_USER_POOL_ID=<手順4のUserPoolId>
VITE_COGNITO_USER_POOL_CLIENT_ID=<手順4のUserPoolClientId>
VITE_COGNITO_REGION=ap-northeast-1
VITE_VAPID_PUBLIC_KEY=<手順5のApplication Server Keyの値>
```

```powershell
cd frontend
npm run build
```

## 7. FrontendStackのデプロイ（手順3で`--all`済みなら不要）

```powershell
cd infra
cdk deploy dev-MeetFlowFrontendStack -c env=dev --profile personal
```

S3バケットとCloudFrontディストリビューションが作成される（`infra/meetflow_infra/meetflow_frontend_stack.py`参照）。独自ドメインは未取得のため、CloudFrontの既定ドメイン（`*.cloudfront.net`）で配信する暫定構成（取得後はACM証明書＋Route53 Aliasを追加する想定）。

## 8. フロントエンドのアップロード

手順6でビルドした`frontend/dist/`をS3に同期し、CloudFrontのキャッシュを無効化する。CDKの`BucketDeployment`はあえて使っていない（`frontend/.env.development`がバックエンドのCfnOutputに依存するため、frontend/distのビルドは必然的にバックエンドデプロイ後になり、synth時にdistの実在を要求する`BucketDeployment`とは相性が悪い。また`.github/workflows/ci.yml`の`infra-synth`ジョブはdist抜きで`cdk synth --all`を実行するため、それも壊れてしまう。詳細は`meetflow_frontend_stack.py`のコメント参照）。

```powershell
cd frontend
aws s3 sync dist/ s3://<手順4のFrontendBucketName>/ --delete --profile personal
aws cloudfront create-invalidation --distribution-id <手順4のCloudFrontDistributionId> --paths "/*" --profile personal
```

`CloudFrontDomainName`（`https://xxxxxxxxxxxxxx.cloudfront.net`）をブラウザで開いて動作確認する。

## 手順7・8を待たずに手順6までで可能な動作確認

API自体の疎通は、Cognitoでテストユーザーを作成しJWTを取得した上で、`curl`等で`ApiUrl`に直接リクエストすることでも確認できる。
