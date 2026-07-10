# MeetFlow AWSシステム構成設計書 v1.2

> 要件定義書v1.1・機能要件書v1.1・API設計書v1.1・DynamoDB物理設計書v1.1・Lambda設計書v1.0を踏まえて更新。
> v1.0からの変更点は **[v1.1修正]** として明記。変更点サマリは末尾参照。

---

## 1. システム概要

MeetFlowは、趣味コミュニティ向けイベントマッチングサービスである。AWSマネージドサービスを中心としたサーバーレス構成を採用し、運用負荷を最小化する。

---

## 2. 全体構成

```
                  User
                   |
              HTTPS通信
                   v
              CloudFront
                   |
        +----------+----------+
        |                     |
        v                     v
   S3 Hosting             API Gateway
   (React App)          (Cognito Authorizer)
                                |
                                v
                      +---------+---------+---------+---------+---------+---------+
                      |         |         |         |         |         |         |
                      v         v         v         v         v         v         v
                  UserLambda CommunityLambda AvailabilityLambda MatchingLambda EventLambda ResultLambda NotificationLambda
                      |         |         |         |         |         |         ^
                      +---------+---------+----+----+---------+---------+         |
                                              |                                    |
                                              v                                    |
                                          DynamoDB                                 |
                                     (単一テーブル + GSI1/GSI2)                     |
                                              |                                    |
                                              v                                    |
                                         EventBridge  ------------------------------+
                                     (EventConfirmed / EventCancelled / CancelApproved)
```

> **[v1.1修正]** Lambda一覧をLambda設計書v1.0のドメイン単位7個（UserLambda, CommunityLambda, AvailabilityLambda, MatchingLambda, EventLambda, ResultLambda, NotificationLambda）に統一。DynamoDBは「管理対象を列挙」ではなく「単一テーブル＋GSI1/GSI2」という物理設計書v1.1の構成を明記。

---

## 3. フロントエンド

### Amazon S3

用途：Reactアプリケーション配信。保存物：HTML, CSS, JavaScript/TypeScriptビルド成果物

### CloudFront

用途：CDN配信。役割：HTTPS対応、キャッシュ、高速配信

---

## 4. ドメイン・HTTPS

### Route53

用途：DNS管理（例：meetflow.jp → CloudFront）

### ACM

用途：SSL/TLS証明書管理（User ↔ CloudFront間のHTTPS化）

---

## 5. 認証

### Amazon Cognito

用途：ユーザー認証。管理：メール認証、パスワード、JWTトークン発行

### 認証フロー **[v1.1修正]**

```
User
  ↓
Cognito Login
  ↓
JWT Token
  ↓
API Gateway（Cognito Authorizerでトークン検証）
  ↓
Lambda（検証済みクレームをeventから受け取るのみ）
```

> **[v1.1修正]** v1.0では「Lambda認可」と曖昧に書かれていたが、JWT検証自体は**API GatewayのCognito Authorizer機能**で完結させる方針を明記（Lambda設計書v1.0 1章に準拠）。独自のAuthLambdaは持たない。Lambda側は検証済みの`userId`等をevent経由で受け取り、コミュニティ所属・操作権限チェック（Lambda Layer共通関数）のみを行う。

### ユーザー登録フロー **[v1.1修正]**

> ユーザー登録（F-001）は公開APIエンドポイントを持たず、**Cognito Post Confirmationトリガー**としてUserLambdaを起動し、DynamoDBにプロフィールを作成する方式に統一（Lambda設計書v1.0 3章に準拠）。

---

## 6. API層

### API Gateway

用途：REST API公開。役割：HTTPSエンドポイント、Cognito Authorizerによる認証、Lambda連携、スロットリング

### API例（ドメイン単位ルーティング）**[v1.1修正]**

| パスプレフィックス | 統合先Lambda |
|---|---|
| `/users/*` | UserLambda |
| `/communities/*`, `/invites/*` | CommunityLambda |
| `/communities/{id}/availability/*`, `/availability/*` | AvailabilityLambda |
| `/communities/{id}/event-templates/*`, `/communities/{id}/matching/*`, `/matching/*` | MatchingLambda |
| `/events/*` | EventLambda |
| `/events/{id}/sessions`, `/users/{id}/results` | ResultLambda |
| `/notifications/*` | NotificationLambda |

> v1.0では`POST /communities`, `GET /events`, `POST /availability`, `POST /matchings`という個別例のみだったが、Lambda設計書との対応が分かるようドメイン単位のルーティング表に修正。

---

## 7. ビジネスロジック **[v1.1修正]**

### AWS Lambda

MeetFlowのメイン処理。**ドメイン単位（7個）＋マッチング処理の分離**という設計方針を採用（Lambda設計書v1.0参照）。

| Lambda | 役割 |
|---|---|
| UserLambda | ユーザー登録（Cognitoトリガー）・プロフィール管理 |
| CommunityLambda | コミュニティ・メンバー・招待・参加リクエスト承認・会場（Place）管理 |
| AvailabilityLambda | 空き予定管理（バッチ登録含む） |
| MatchingLambda | 開催条件管理・マッチング候補生成（重い処理のため独立） |
| EventLambda | イベントライフサイクル・参加者管理・個人キャンセル申請/承認・イベント全体中止 |
| ResultLambda | 成績管理・集計 |
| NotificationLambda | 通知レコード作成・一覧・既読管理 |

> v1.0の7つのLambda名（UserLambda等）はそのまま踏襲されているが、v1.0時点では役割の詳細（キャンセル承認、会場管理、参加リクエスト承認等）が定義されていなかった。Lambda設計書v1.0で詳細化された内容をこちらに反映。

---

## 8. データベース

### DynamoDB **[v1.1修正]**

用途：アプリケーションデータ保存。

> **[v1.1修正]** v1.0では「管理対象：User, Community, Availability, Event, MatchCandidate, GameResult, OperationLog」と論理的な列挙のみだったが、実際は**単一テーブル設計**（テーブル名：`MeetFlowTable`）を採用しており、以下のエンティティをPK/SKのプレフィックスで区別して同一テーブルに格納する（詳細はDynamoDB物理設計書v1.1参照）。

**格納エンティティ**：User, Community, Membership, Invite, JoinRequest, Availability, EventTemplate, MatchCandidate, Place, Event, Participant, CancelRequest, GameSession, GameResult, Notification, OperationLog, EventStatusHistory

**キー構造**
- プライマリ：PK / SK
- GSI1（ByUser）：ユーザー起点の横断検索（所属コミュニティ、自分の空き予定、参加イベント、成績、操作ログ等）
- GSI2（ByAltId）：コミュニティIDを介さない直接ID検索（マッチング候補詳細等）

**特徴**：自動スケール、高可用性、サーバーレス、オンデマンドキャパシティモード（個人開発規模のため）

**TTL**：OperationLogに設定し、一定期間経過後のログを自動削除（コスト最適化。長期保存が必要なデータはS3エクスポート＋Athenaで分析する構成に接続）

---

## 9. 非同期処理

### Amazon EventBridge **[v1.1修正]**

用途：イベント駆動処理。

> **[v1.1修正]** v1.0の例は「候補生成→NotificationLambda」のように管理者承認ステップが省略された図になっていたため、実際のイベントフロー（Lambda設計書v1.0 7.3準拠）に修正する。

**イベント確定フロー（2段階の通知＋ダブルブッキング防止を含む）** **[v1.2修正]**

```
① 管理者が候補を確認しイベント作成（EventLambda: POST /events）
    ↓
② 管理者が承認（EventLambda: POST /events/{id}/confirm）
    ↓
【v1.2追加】候補メンバー全員のダブルブッキング事前チェック（Participant GSI1を時間範囲でQuery）
    ↓ 重複なし
EventBridge: EventConfirmed 発行
    ↓                          ↓
NotificationLambda          MatchingLambda【v1.2追加】
（参加者へ確定通知）          （他コミュニティのPENDING候補との衝突を検知）
                               ↓ 衝突あり
                            EventBridge: CandidateConflictDetected 発行
                               ↓
                            NotificationLambda（該当コミュニティの管理者へ通知）
```

> **[v1.2追加]** 複数コミュニティ横断のダブルブッキング対策として2段構え：①確定処理直前の同期的ハードチェック（実害防止）、②確定後の非同期的な衝突検知（他コミュニティのPENDING候補への気づき通知）。詳細はLambda設計書v1.1 6.7/7.2b参照。

**イベント中止フロー**

```
EventLambda: POST /events/{id}/cancel（イベント全体の中止）
    ↓
EventBridge: EventCancelled 発行
    ↓
NotificationLambda（全参加者へ中止通知）
```

**個人キャンセル承認フロー（MVP：欠員補充は含まない）**

```
EventLambda: キャンセル申請 → 管理者承認（ConditionExpressionで二重承認防止）
    ↓
EventBridge: CancelApproved 発行
    ↓
NotificationLambda（本人へ受理通知のみ。欠員補充はPhase2のため後続処理は発火しない）
```

> **[v1.1修正]** v1.0では「空き予定登録→EventBridge→MatchingLambda→候補生成」という自動連鎖が例示されていたが、前回決定「MVPのマッチング実行は管理者による手動実行のみ」と矛盾するため削除。マッチング処理はAPI Gateway経由の手動呼び出しのみとし、EventBridgeは候補生成後の非同期処理（通知等）にのみ使用する。

---

## 10. Step Functions（将来）

MVPでは未使用。

**利用予定**：複雑なワークフロー管理

例：
```
候補生成 → 24時間待機 → 承認確認 → 未承認なら再提案 → 期限切れ処理
```

> **[v1.1補足]** 管理者承認待ちのタイムアウト・リマインドや、Phase2の欠員補充（検索→通知→確定の多段処理）で候補が見つからない場合の分岐など、複数ステップにまたがる処理が複雑化した場合の選択肢として維持する。実装方式（EventBridgeイベント連鎖 vs Step Functions）は実装段階で決定（Lambda設計書v1.0 14章の未決事項と同一）。

---

## 11. 通知 **[v1.1修正：矛盾を解消]**

> **[v1.1修正]** v1.0では「MVP：メール通知（SES）」となっていたが、要件定義書v1.1 16章・機能要件書v1.1 12章では「MVP：アプリ内通知のみ」と定義されており、ドキュメント間で矛盾していた。Lambda設計書v1.0 9.3での指摘を受け、**要件定義書・機能要件書を正とし、本書を以下のとおり修正する。**

**MVP**：アプリ内通知のみ（NotificationLambdaがDynamoDBにレコード作成、フロントエンドがポーリングまたは`GET /notifications`で取得）

**Phase2以降**
- メール通知：Amazon SES（利用時はRoute53で管理しているドメインのSPF/DKIM認証設定が必要）
- Push通知：Amazon SNS または Firebase Cloud Messaging
- LINE通知：検討中（要件定義書16章）

---

## 12. ログ・監視

### CloudWatch

用途：Lambdaログ、APIログ、エラー監視、メトリクス

### CloudTrail

用途：AWS操作監査（対象：IAM変更、AWS設定変更）

> アプリケーション操作ログ（誰がイベントを承認したか等）はCloudTrailの対象外であり、DynamoDBのOperationLogテーブルで別途管理する（DynamoDB物理設計書v1.1 3.15参照、機能要件書v1.1 F-1301に対応）。

---

## 13. セキュリティ構成

### 通信

```
User → HTTPS → CloudFront → API Gateway → Lambda
```

### 認可 **[v1.1修正]**

> API GatewayでCognito Authorizerによる認証を行い、各ドメインLambdaは検証済みクレームをもとにコミュニティ所属・操作権限チェック（共通Lambda Layer）を実施する（5章参照）。

### 暗号化

利用：DynamoDB暗号化（KMS）、S3暗号化、KMS

### Secrets管理

AWS Secrets Manager 用途：外部APIキー、DB認証情報

---

## 14. CI/CD構成 **[v1.1修正]**

GitHub（ソース管理）→ GitHub Actions（自動化）

**処理フロー**：`git push → test → build → deploy → S3更新 → Lambda更新`

**ブランチ・環境対応** [v1.1追加]

| ブランチ | デプロイ先環境 |
|---|---|
| `develop` | Development |
| `staging` | Staging |
| `main` | Production |

> **[v1.1追加]** v1.0では処理フローのみでブランチと環境の対応関係が未定義だったため追加。`main`へのマージをProduction自動デプロイのトリガーとする最低限のルールを明記。

---

## 15. 開発環境 **[v1.1修正]**

環境分離：Development → Staging → Production

> **[v1.1修正]** v1.0では「AWSアカウント分離推奨」とだけ記載されていたが、個人開発＋学習目的の段階ではアカウント分離の管理コスト（IAMロール、クロスアカウントアクセス等）が重い。**MVPでは単一AWSアカウント＋リソース名プレフィックス（`dev-`, `staging-`, `prod-`）による環境分離**を採用し、運用が安定してから本格的なAWS Organizationsによるアカウント分離へ移行する方針とする。

---

## 16. MVP時AWSサービス一覧

| サービス | 用途 |
|---|---|
| CloudFront | 配信 |
| S3 | フロントホスティング |
| Route53 | DNS |
| ACM | SSL |
| Cognito | 認証（Authorizer含む） |
| API Gateway | API |
| Lambda | 処理（7ドメイン構成） |
| DynamoDB | DB（単一テーブル＋GSI×2） |
| EventBridge | イベント処理（通知連携のみ、マッチング自動起動には未使用） |
| CloudWatch | 監視 |
| CloudTrail | 監査 |

---

## 17. 将来拡張

### AIマッチング

追加候補：SageMaker, Bedrock

用途：相性分析、開催成功率予測、推薦エンジン

> フルスクラッチのML基盤（SageMaker）よりも、既存LLMをAPI経由で使うBedrockの方が個人開発の運用コストは低い。「同時参加履歴から自然言語で傾向を要約する」程度の用途であればBedrock＋プロンプト設計で十分実現できるため、優先的にBedrockを検討する。

### 分析基盤

追加候補：S3 Data Lake, Athena, QuickSight

用途：コミュニティ分析、利用傾向分析。DynamoDBのOperationLog等をTTLで削除する前にS3へエクスポートし、Athenaで分析する構成を想定（8章参照）。

---

## 18. 設計方針

MeetFlowは、「小規模コミュニティで低コスト運用できる」ことを優先しつつ、「利用データが蓄積されるほど価値が高まる」サービス設計とする。そのためAWSマネージドサービス中心のサーバーレス構成を採用する。

---

## v1.0 → v1.1 変更点サマリ

| No | 変更内容 | 理由 |
|---|---|---|
| 1 | Lambda一覧をドメイン単位7個（Lambda設計書v1.0準拠）に統一し、役割を詳細化 | Lambda設計書との整合 |
| 2 | 認証フローで「Lambda認可」を「API Gateway Cognito Authorizer」に修正、独自AuthLambdaを廃止 | ベストプラクティスへの準拠 |
| 3 | ユーザー登録をCognito Post Confirmationトリガー方式に修正 | 公開APIとして`POST /users`は存在しないため |
| 4 | DynamoDBを「単一テーブル＋GSI1/GSI2」構成として明記 | DynamoDB物理設計書v1.1との整合 |
| 5 | EventBridgeのイベント確定フローを2段階（イベント作成→承認）に修正、イベント名（EventConfirmed等）を明記 | v1.0の図が承認ステップを省略していたため |
| 6 | 空き予定登録時のマッチング自動起動フローを削除 | MVPは手動実行のみという決定と矛盾していたため |
| 7 | 個人キャンセル承認フローを追加（欠員補充を含まない） | MVPスコープとの整合 |
| 8 | 通知のMVPをメール（SES）からアプリ内通知のみに修正 | 要件定義書・機能要件書との矛盾を解消 |
| 9 | CI/CDのブランチ・環境対応表を追加 | v1.0で未定義だったため |
| 10 | AWSアカウント分離を「推奨」から「MVPは単一アカウント＋プレフィックス分離」に変更 | 個人開発の運用コストとのバランス |
| 11 | API Gatewayのルーティング例をドメイン単位の表に変更 | Lambda設計書との対応を明確化 |

---

## v1.1 → v1.2 変更点サマリ

| No | 変更内容 | 理由 |
|---|---|---|
| 1 | イベント確定フローにダブルブッキング事前チェックと`CandidateConflictDetected`イベントを追加 | 複数コミュニティ横断のダブルブッキング防止（確定時ハードチェック＋事後検知の2段構え） |
