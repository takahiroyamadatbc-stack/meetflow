# MeetFlow 手動デプロイ手順（dev環境）

MVP検証のための手動デプロイ手順。CD（GitHub Actionsからの自動デプロイ）は現時点ではスコープ外で、`cdk deploy`をローカルから手動実行する運用（詳細はCLAUDE.mdの「CI/CD」節を参照）。

## 前提

- AWS CLI 2.x、CDK CLI 2.xがインストール済み
- SSOプロファイル`personal`が`~/.aws/config`に設定済み（account `569239323423`、region `ap-northeast-1`、`AdministratorAccess`ロール）
- `infra/.venv`（`infra/requirements.txt`）、`backend/.venv`（`backend/requirements-dev.txt`）が構築済み

以降のコマンドはGit Bashを想定。作業ディレクトリはリポジトリルート（`meetflow/`）から相対で示す。

> Windows PowerShellの既定の実行ポリシー（`Restricted`）では`cdk.ps1`等の`.ps1`スクリプトが読み込めずエラーになることがある。Git Bashは`cdk`（拡張子無しのシェルスクリプト）を直接呼び出すため、この制限を受けない。

## 費用について

AWS公式Price List API（`pricing.us-east-1.amazonaws.com`、認証不要）から東京リージョンの実料金を取得して試算した結果、**月額は約$1.5〜2程度**（数百円）に収まる見込み。

- **固定費（利用量に関わらず毎月発生。ここが支配的）**
  - KMSカスタマー管理キー（DynamoDB暗号化用）：$1.00/月
  - Secrets Manager（VAPID鍵ペア保管）：$0.40/月
- **変動費**：Lambda・DynamoDB・API Gateway・CloudFront・S3・Cognitoはいずれも、動作確認〜30人規模のコミュニティが散発的に使う程度の利用量では無料枠内〜数十セント未満に収まる（CloudFrontの無料枠は月1TB転送＋1000万リクエストと大きく、全アカウント恒久のため到達しにくい）
- **新規アカウント向け12ヶ月無料枠が使えない場合の影響**：Lambda・KMS・CloudFront・Cognitoの無料枠は元々「全アカウント恒久」なので影響なし。影響があるのはS3の無料枠（新規アカウント限定）のみで、実際のストレージ量が数MB程度のため影響額は$0.01/月未満。**結論として上記の試算は変わらない**
- **VPC/NAT Gatewayは不使用**（Lambdaはいずれも非VPC）のため、この構成で最も高額になりがちなNAT Gateway費用（月$30〜45）は発生しない
- **`cdk deploy`を繰り返すこと自体に追加費用はほぼ無い**（CloudFormationのスタック更新・Lambdaコード更新は無料）。ただし`cdk destroy`してから作り直す場合は要注意：DataStackのKMSキー・DynamoDBテーブルは共にdev環境では`RemovalPolicy.DESTROY`のため、`cdk destroy`すると（1）KMSキーは削除予約後も7〜30日間課金が続くため、その間に再デプロイすると新旧キーが一時的に二重課金される、（2）DynamoDBのデータは完全に失われる。通常の開発中は`cdk deploy`で更新し続ける分にはどちらも発生しない
- 上記の想定外の課金急増に気づけるよう、**AWS Budgetsで月$10のアラート**を設定済み（`MeetFlowDataStack`の`AccountCostBudget`、実費用が閾値を超えるとメール通知）

## 1. AWS認証

```bash
aws sso login --profile personal
aws sts get-caller-identity --profile personal   # 認証確認
```

以降、`--profile personal`を都度付けるか、`export AWS_PROFILE=personal`で省略可能。

## 2. cdk bootstrap（対象アカウント/リージョンに対して初回のみ）

```bash
cd infra
export PATH="$(pwd)/.venv/Scripts:$PATH"
cdk bootstrap aws://569239323423/ap-northeast-1 --profile personal
```

CDKデプロイに必要なS3バケット・IAMロール等（`CDKToolkit`スタック）が作成される。アカウント/リージョンごとに一度だけでよい。

## 3. バックエンド4スタック＋FrontendStackのデプロイ

```bash
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

```bash
aws cloudformation describe-stacks --stack-name dev-MeetFlowAuthStack --profile personal --query "Stacks[0].Outputs"
aws cloudformation describe-stacks --stack-name dev-MeetFlowApiStack --profile personal --query "Stacks[0].Outputs"
aws cloudformation describe-stacks --stack-name dev-MeetFlowFrontendStack --profile personal --query "Stacks[0].Outputs"
```

## 5. VAPID鍵ペアの生成・投入

`backend/.venv`には`pywebpush`の依存として`py-vapid`が入っており、そのCLI（`vapid`）で鍵ペアを生成できる。

```bash
cd backend
.venv/Scripts/vapid --gen --json --applicationServerKey
```

`private_key.pem`・`public_key.pem`がカレントディレクトリに生成され、`vapidPublicKey`にあたるbase64url値（`Application Server Key`）がターミナルに表示される。

`vapidPrivateKey`（base64url・raw形式。pywebpushが`Vapid.from_string`で読める形式）は、生成された`private_key.pem`から以下で変換する：

```bash
.venv/Scripts/python -c "import base64; from py_vapid import Vapid01; v = Vapid01.from_file('private_key.pem'); raw = v.private_key.private_numbers().private_value.to_bytes(32, 'big'); print(base64.urlsafe_b64encode(raw).rstrip(b'=').decode())"
```

得られた2つの値を、CDKが作成済みのSecrets Managerシークレット（名前固定：`dev-meetflow-vapid-keys`）に投入する：

```bash
aws secretsmanager put-secret-value --secret-id dev-meetflow-vapid-keys --profile personal --secret-string '{"vapidPrivateKey":"<上で得たprivate値>","vapidPublicKey":"<Application Server Keyの値>"}'
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

```bash
cd frontend
npm run build -- --mode development
```

`vite build`は`--mode`省略時デフォルトで`production`となり、`.env.production`系のファイルしか読み込まない。`.env.development`に転記した値をビルドに反映させるには`--mode development`の指定が必須（省略するとCognitoの環境変数がビルド成果物に埋め込まれず、サインイン画面で`Auth UserPool not Configured`エラーになる）。ここでの`development`はViteのビルドモードであり、dev/staging/prodというAWS環境の呼称と対応している（staging/prod環境を構築する際は`.env.staging`/`.env.production`を用意し、それぞれ`--mode staging`/`--mode production`でビルドする）。

## 7. FrontendStackのデプロイ（手順3で`--all`済みなら不要）

```bash
cd infra
cdk deploy dev-MeetFlowFrontendStack -c env=dev --profile personal
```

S3バケットとCloudFrontディストリビューションが作成される（`infra/meetflow_infra/meetflow_frontend_stack.py`参照）。独自ドメインは未取得のため、CloudFrontの既定ドメイン（`*.cloudfront.net`）で配信する暫定構成（取得後はACM証明書＋Route53 Aliasを追加する想定）。

## 8. フロントエンドのアップロード

手順6でビルドした`frontend/dist/`をS3に同期し、CloudFrontのキャッシュを無効化する。CDKの`BucketDeployment`はあえて使っていない（`frontend/.env.development`がバックエンドのCfnOutputに依存するため、frontend/distのビルドは必然的にバックエンドデプロイ後になり、synth時にdistの実在を要求する`BucketDeployment`とは相性が悪い。また`.github/workflows/ci.yml`の`infra-synth`ジョブはdist抜きで`cdk synth --all`を実行するため、それも壊れてしまう。詳細は`meetflow_frontend_stack.py`のコメント参照）。

```bash
cd frontend
aws s3 sync dist/ s3://<手順4のFrontendBucketName>/ --delete --profile personal
aws cloudfront create-invalidation --distribution-id <手順4のCloudFrontDistributionId> --paths "/*" --profile personal
```

`CloudFrontDomainName`（`https://xxxxxxxxxxxxxx.cloudfront.net`）をブラウザで開いて動作確認する。

## 手順7・8を待たずに手順6までで可能な動作確認

API自体の疎通は、Cognitoでテストユーザーを作成しJWTを取得した上で、`curl`等で`ApiUrl`に直接リクエストすることでも確認できる。
