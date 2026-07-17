# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 参照すべき設計書

実装前に必ず docs/ 内の以下を読むこと:

- 要件定義書v1.8（29章「相互非公開型マッチング」はMeetFlowのコア設計原則）
- 機能要件書v1.10
- DynamoDB物理設計書v1.12（特に単一テーブル設計のPK/SK/GSI1/GSI2）
- Lambda設計書v1.7（8ドメイン構成、IAM権限は「案C」を採用）
- API設計書v1.17
- 画面設計書v1.13
- エラーコード一覧v1.9
- AWSシステム構成設計書v1.3

## 技術スタック

- IaC: AWS CDK (Python)
- Lambda: Python 3.13
- フロント: React + Tailwind CSS + shadcn/ui
- リポジトリ: モノレポ

## 実装方針

- DynamoDB物理設計書のキー設計(PK/SK/GSI)から絶対に逸脱しない
- IAM権限はLambda設計書5.3の「案C」に従う
- 各ドメインLambdaは1ファイルにハンドラーをまとめず、ルーター+ハンドラー関数に分割する
- コードコメント・docstringは日本語で書く（英語のコメントは書かない）。ユーザーは日本語話者であり、コードの主読者・保守者も日本語話者である前提のため
- アプリがユーザーに返す文字列（エラーメッセージ、レスポンスメッセージ、UI表示文言等）はすべて日本語で書く。エラーコード自体（例：`PARTICIPANT_SCHEDULE_CONFLICT`）や識別子・ログ出力は英語のままでよいが、`message`フィールドやフロントエンドの表示文言は日本語にする

## Git運用方針

- 意味のある単位(1機能・1修正)ごとにローカルcommitする
- commitメッセージは Conventional Commits形式(feat:, fix:, docs: 等)で書く
- git pushは明示的に指示されるまで実行しない
- developブランチへの直接pushはしない。作業用ブランチ(feature/xxx)を切ってそこにpushする
- **[MVP期間中の暫定運用]** mainへの反映はPR経由が基本だが、MVP開発期間中はレビュー負荷を下げるため、featureブランチをPRを介さずローカルでmainに直接マージ・pushしてよい（指示があった場合のみ、上記のpush規約は変わらない）。プロダクトが安定しチーム開発体制になったらPRベースの運用に戻す。
- **バグ修正・機能追加はGitHub Issueで管理する**：着手前に`gh issue create`でIssueを作成してから作業を始め、修正が完了したら`gh issue close`でそのIssueを解決済みにする。1つのユーザー報告が複数の独立した修正・追加に分かれる場合は、それぞれ別Issueにする。

## プロジェクトの状態

MeetFlowは設計フェーズを終え、バックエンドの実装に着手している。`docs/`配下の日本語設計ドキュメント群は実装対象の仕様書として引き続き最優先で参照すること（背景資料ではない）。

- `infra/`：AWS CDK（Python）。`MeetFlowDataStack`（DynamoDB単一テーブル）、`MeetFlowAuthStack`（Cognito）、`MeetFlowComputeStack`（共有Lambda Layer + 7ドメインLambda）、`MeetFlowApiStack`（API Gateway REST API + Cognito Authorizer、7ドメイン×全49エンドポイントのルーティング（Issue #25で`POST /communities/{communityId}/members/me/leave`を追加）。`GET /communities/{communityId}`はAPI設計書には無いがフロントエンド実装時に追加）、**`MeetFlowFrontendStack`（S3 + CloudFront、フロントエンド配信。AWSシステム構成設計書v1.3 §3-4）**を実装済み。`MeetFlowFrontendStack`は独自ドメイン未取得のためRoute53/ACMは含めず、CloudFront既定ドメインで配信する（MVP検証目的の暫定判断。独自ドメイン取得後にACM証明書＋Route53 Aliasを追加する想定）。SPA(React Router)のクライアントサイドルーティングに対応するため403/404を`index.html`にフォールバックし、S3バケットはCloudFront OAC経由のみアクセス可能（パブリックアクセスなし）。**あえてCDKの`BucketDeployment`は使っていない**：`frontend/.env.development`はバックエンド4スタックのCfnOutputを転記して作る値を含むため、frontend/distのビルドは必然的にバックエンドデプロイ後になる。`BucketDeployment`はsynth時にfrontend/distの実在を要求し、`.github/workflows/ci.yml`の`infra-synth`ジョブ（frontend/dist抜きのクリーンチェックアウトで`cdk synth --all`を実行）を壊してしまうため、`aws s3 sync`＋`aws cloudfront create-invalidation`による手動アップロードとした（手順はDEPLOY.md参照）。他スタックへの参照は持たないため、デプロイ順に制約はない。`GET /communities/{communityId}/logs`・`GET /users/{userId}/logs`（OperationLog閲覧API、API設計書v1.7 §12）と`POST /invites/{token}/revoke`（招待URL無効化、API設計書v1.8 §4.3b・新規追加）はCommunityLambda（`community_lambda/handlers/logs.py`・`invites.py`）に実装・接続済み。`GET /users/{userId}/logs`はURLパスこそ`/users/`始まりだがCommunityLambda担当（権限判定がMembership/roleに依存するため、`GET /users/{userId}/results`がResultLambda担当なのと同種の判断）。これで7ドメインLambdaが実際にHTTP経由で呼び出し可能になった（以前は`MeetFlowComputeStack`までしか無く、Lambdaへの到達経路が存在しなかった）。AvailabilityLambdaの`events:PutEvents`権限（F-205用）、NotificationLambdaの`dynamodb:DeleteItem`（PushSubscription解除用）・EventBridge Rule拡張・VAPID鍵用Secrets Managerシークレットは反映済み。**Web Push送信処理（Lambda設計書v1.2 §9.3b）も実装済み**：`pywebpush`（→`cryptography`等ネイティブ拡張）はNotificationLambda専用の第2 Lambda Layer（`backend/layers/webpush/`）に分離し、`aws_cdk.ILocalBundling`によるローカルバンドリング（`infra/meetflow_infra/webpush_layer_bundling.py`）で、Docker無しで`pip install --platform manylinux2014_x86_64 --only-binary=:all:`によりmanylinuxホイールを直接取得する方式を採用（`cdk synth`で実機検証済み。同梱`.so`がLinux/x86-64向けであることも確認済み）。VAPID鍵ペアの実際の生成・投入（`aws secretsmanager put-secret-value`等、値は`{"vapidPrivateKey": "<base64url>", "vapidPublicKey": "<base64url>"}`形式のJSON）は開発者がデプロイ後に手動で行う運用（未決事項7は鍵生成・ローテーション方式のみ未解消）。全Lambdaのランタイムは`lambda_.Runtime.PYTHON_3_13`（本ファイル冒頭の技術スタック記載と一致）に統一済み。webpush Layerのローカルバンドリング（`webpush_layer_bundling.py`の`_PYTHON_VERSION`）もPython 3.13向けのmanylinuxホイール解決で実機検証済み。**デプロイ前レビューで洗い出した運用面の懸念のうち4点も反映済み**：(1) 全7ドメインLambdaのCloudWatch Logsに1ヶ月保持のロググループを明示（`_build_function`が`logs.LogGroup`を作成し`log_group=`で渡す。非推奨の`log_retention`propは使わない）、(2) EventBridge Rule 2本（MatchingLambdaの`EventConfirmed`購読、NotificationLambdaの通知処理）にそれぞれSQS DLQを追加（処理失敗がEventBridgeの既定リトライ後にサイレントに消えるのを防止）、(3) API Gatewayにアクセスログを追加（`RestApi`の`cloud_watch_role`はデフォルトTrueで、CloudWatch書き込みロールと`AWS::ApiGateway::Account`はCDKが自動管理するため手動では作らない。X-Rayトレーシングは規模に対して旨味が薄いため見送り）、(4) `MeetFlowDataStack`にAWS Budgets（月$10しきい値、`AccountCostBudget`）を追加し課金アラートをメール通知。Cognito MFA・CORS絞り込み・CloudTrailは今回は意図的に見送り（判断の理由はDEPLOY.mdの「費用について」節および会話履歴を参照）
- `backend/`：7ドメインLambda（User/Community/Availability/Matching/Event/Result/Notification）+ 共通Layer（`meetflow_common`：DynamoDB/認証/ルーティング/EventBridge/エラーレスポンス等の共通処理）を実装済み。AvailabilityLambdaには要件定義書v1.3 §28（F-205/F-206、空き予定提出リクエスト）、NotificationLambdaには同§27（F-701〜F-704、プッシュ通知購読登録・解除＋実際のWeb Push送信）のハンドラーを追加済み。`AvailabilityRequestCreated`イベントはAvailabilityLambdaがpublishし、NotificationLambda側（`event_subscriber.py`→`push_sender.py`）が購読して通知レコード作成とWeb Push送信の両方を行うところまで配線済み。**pytest+moto(mock_aws)による単体テストは7ドメイン全て整備済み**（`functions/{domain}_lambda/tests/`、計286件）。メンバー自主退会（`POST /communities/{communityId}/members/me/leave`、F-104d）と、それを流用した強制退会（`update_member`のremove分岐）の未来の確定参加チェックは、`meetflow_common.participation.has_upcoming_reserved_participation`に共通ロジックとして実装済み（Issue #25/#26。Participant自体はcommunityIdを持たないためGSI1でユーザーの参加行を取得後、該当EventのGSI1PKからコミュニティを判定する）。UserLambdaのみ`handlers/`パッケージを持たない単一ファイル構成（`handler.py`が直接ロジックを実装）で、テストは`import handler`して`handler._get_profile(...)`のように呼ぶ。
  - **注意（sys.modules衝突）**：各ドメインの`tests/conftest.py`は、同名の`handlers`パッケージ・`handler`モジュール（UserLambda）・`_factories`モジュールが複数ドメイン間で衝突しないよう、自分のテストがimportされる前に`sys.modules`から該当名を退避させている。新しいテストファイルを書く際もこのパターンを踏襲すること。踏襲しないと、そのドメイン単体では通るのに`pytest`をbackend全体に対して実行した時だけ`ImportError`になる（先に収集された他ドメインの同名モジュールがsys.modulesにキャッシュされ、後続ドメインのimportを壊すため）。
  - **注意（文字列ベースmock.patchの罠）**：`unittest.mock.patch("handlers.xxx.yyy")`のような**文字列**ターゲットは、pytestの「全ドメイン収集→まとめて実行」という2段階モデルの下では、テスト**実行**時点（＝全ドメインの収集がとうに終わり、`sys.modules['handlers']`が最後に収集されたドメインのものに上書きされた後）に`importlib`で再解決される。conftest.pyの退避は収集フェーズにしか効かないため、これだけでは救えない。必ず`patch.object(既にimport済みのモジュールオブジェクト, "属性名")`の形で、実オブジェクト参照を経由してパッチすること（`notification_lambda/tests/test_event_subscriber.py`が実例）。
  - **注意（DynamoDBのDecimal型）**：boto3のTable resourceはNumber属性を常に`decimal.Decimal`で返す（int/floatにはならない）。`meetflow_common.errors`の`success_response`/`error_response`はDecimalを自動でint/floatに変換してJSON化するが、ハンドラー内でDynamoDBから読んだ数値をfloatの算術式に混ぜる（`scoring.py`で実際にTypeErrorを起こした）、または`isinstance(x, int)`で検証する（`event_templates.py`の部分更新で実際に常時失敗していた）際は、明示的に`int()`/`float()`でキャストすること。
- `frontend/`：React SPA（Vite + TypeScript + Tailwind CSS v4 + shadcn/ui）の**Phase1・Phase2実装が完了**。27画面・45エンドポイント規模のため段階的に実装する方針とし、Phase1で土台（ビルド環境・認証・タブバー/スタック遷移のシェル・共通APIクライアント）とUser/Community/Availabilityドメインの画面（S-01〜S-10, S-24〜S-27相当）を実装、Phase2でMatching/Event/Result/Notificationドメインの画面（開催条件・マッチング候補一覧/詳細、イベント一覧/詳細・キャンセル申請、成績登録/表示、通知一覧）とPWA化・Webプッシュ購読UIを追加した（コミット`20eeeb2`、2026-07-14）。PWAは`public/manifest.json`＋手書きの`public/service-worker.js`（`main.tsx`で`navigator.serviceWorker.register`により登録）、Webプッシュ購読は`src/features/notification/pushSubscription.ts`がマイページ（`user/MyPage.tsx`）に統合される形で実装済み。全画面は`src/routes/router.tsx`にルートとして登録済みで、実際に画面遷移可能な状態。メンバー一覧画面(S-08)にOWNER自身から他メンバーへの「オーナーを譲渡する」導線（Issue #24）、コミュニティ詳細画面(S-05)に「このコミュニティを退会する」導線（Issue #25、OWNER以外の全メンバーに表示）も実装済み。
  - **認証**：AWS Amplify Auth (v6)を採用（`src/lib/amplify.ts`）。CognitoのUserPoolClientがHosted UI未設定・SRP認証のみ許可（`infra/meetflow_infra/meetflow_auth_stack.py`）のため、独自のメール/パスワードフォーム（`src/features/auth/`）からAmplifyのSRPフローで直接Cognitoと通信する。サインアップ時はニックネームを`clientMetadata`経由でCognito Post Confirmationトリガー（UserLambda）に渡す必要がある（渡し忘れるとメールのローカル部がニックネームになる）。
  - **APIクライアント**：`src/api/client.ts`が薄いfetchラッパーで、`aws-amplify/auth`の`fetchAuthSession()`から取得したIDトークンを`Authorization`ヘッダーに付与する。データフェッチ/キャッシュ管理にはTanStack Queryを採用。エラー表示はエラーコード一覧v1.2 §10の4分類（インライン/トースト/モーダル/空状態）に沿って`src/api/errors.ts`の`getErrorDisplay()`が振り分ける。
  - **画面設計書・API設計書と実装の食い違い**：実装時に以下が判明し、いずれもフロント側の回避策で対応済み（詳細はコード中のコメント参照）。(1) ~~`GET /communities/{communityId}`（単体取得）が未実装~~：**解消済み**。`community_lambda/handlers/communities.py`の`get_community()`として追加し、API設計書v1.6 §4.2bにも正式反映済み。`GET /communities`一覧キャッシュから検索する回避策（`CommunityDetailPage`・`AvailabilityRequestListPage`）は廃止した。(2) `GET /communities`のレスポンスに`memberApprovalRequired`・メンバー数・`communityType`が含まれない（一覧はそのままで、詳細取得は(1)のAPIで解決可能）。(3) ~~招待URLの無効化（revoke）APIが未実装のため、招待画面は発行・コピーのみ対応~~：**解消済み**。`POST /invites/{token}/revoke`を追加し（API設計書v1.8 §4.3b新規）、`InvitePage`に無効化ボタンを実装した（画面設計書v1.4 S-06が元々定義していた「URL無効化ボタン」要素に対応）。
  - ディレクトリ構成はfeature-based（`src/features/{auth,user,community,availability,home}/`）。過剰な抽象化（状態管理ライブラリ、API生成パイプライン等）は導入していない。lintはESLintではなく、Viteテンプレートに同梱の`oxlint`をそのまま使用（`npm run lint`）。
- `.github/workflows/`：CI検証ワークフロー（`ci.yml`）を実装済み。PRおよびmainへのpush時に3ジョブを並列実行する：`backend-test`（pytest、Lambdaランタイムに合わせてPython 3.13）、`frontend-ci`（oxlint→tsc typecheck→vitest→vite build、Node 24。フロントはPhase1時点でテストファイルが未整備のため`vitest`に`--passWithNoTests`を付与しており、テストが追加され次第自動的に実行対象になる）、`infra-synth`（`cdk synth --all`。`app.py`がaccount/region未指定の環境非依存スタックとして定義されているため、AWS認証情報無しで実行可能なことをローカルで確認済み）。デプロイ（CD）は未実装（詳細は本ファイル末尾の「CI/CD」節を参照）。

この開発環境にはPython 3.14（miniconda3）、Node.js v24、AWS CDK CLI 2.xがグローバルに導入済みで、Claude側でもコード実行・テスト実行ができる。プロジェクト依存関係は用途ごとに分離したvenvにインストールしてある：

- `infra/.venv` — `infra/requirements.txt`（aws-cdk-lib, constructs）。`cdk synth`はこのvenvのpythonをPATH優先にして実行する（例：`PATH="$(pwd)/.venv/Scripts:$PATH" cdk synth`）。cdk.jsonの`"app": "python app.py"`はPATH上のpythonをそのまま使うため、venvを有効化しない状態で実行するとaws-cdk-libが見つからずに失敗する。
- `backend/.venv` — `backend/requirements-dev.txt`（boto3, pytest, moto）。共通Layer（`meetflow_common`）やドメインLambdaのハンドラーをimport・テストする際は`PYTHONPATH=layers/common/python`を通す必要がある（`community_lambda/tests/conftest.py`が実例）。依存関係を追加した場合はこのファイルとvenvの両方を更新すること。

Bashツールは呼び出しごとにシェル状態がリセットされるため、venvの有効化（activate）は次のコマンド実行時には引き継がれない。各コマンドでvenv内の`python.exe`/`pip.exe`を直接パス指定するか、PATHをそのコマンド内で明示的に前置すること。

## ドキュメントの読み方

`docs/`ディレクトリには、互いを上書きしていくバージョン管理されたドキュメントが格納されている（`要件定義書` = requirements、`機能要件書` = functional spec、`API設計書` = API design、`AWSシステム構成設計書` = AWS architecture、`DynamoDB物理設計書` = DynamoDB schema、`Lambda設計書` = Lambda design、`エラーコード一覧` = error codes、`画面設計書` = screen design）。それぞれファイル名にバージョン番号が付いており（例：`_v1.2`）、常に最新版を読むこと。旧バージョンはリポジトリ内に残っていないが、各ドキュメント末尾の変更履歴セクション（`v1.0 → v1.1`等）に変更内容と理由が記されており、ドキュメント間で矛盾する記述を突き合わせる際にはここが判断材料になる。機能ID（F-xxx）と章番号はドキュメント間で相互参照されているため、ある機能を実装する際は、要件定義書・機能要件書・API設計書・DynamoDB設計書・Lambda設計書の該当箇所をまとめて確認すること。

このドキュメント群で特に注意すべき点：

- バージョンを跨いで決定が覆されている箇所がある（例：MVP時点の通知チャネルは一時的にSESメール送信と記載されていたが、他のドキュメントに合わせてアプリ内通知のみに修正された）。ドキュメント間で矛盾があった場合は、各ファイル末尾の変更履歴表がタイブレーカーになる。
- 複数の節で「未決事項」として実装時に決定すべき事項が明示的にマークされている。実装時にドキュメントが未確定のまま残している判断を下す前に、これらを確認すること。

## プロダクトコンセプト（前提として重要）

MeetFlowは、従来の「募集メッセージを投稿して返信を待つ」方式ではなく、**登録済みの空き予定と主催者が定義した開催条件のマッチング**によってイベントを成立させる。ユーザーは空き時間を登録し、コミュニティ管理者はイベントテンプレート（ゲーム種別・人数範囲・優先度）を登録する。システムはそれらを突き合わせてスコア付きの候補を生成する。システムは**イベントを自動確定することは決してなく**、すべての候補は管理者のレビュー・承認を経る。このヒューマン・イン・ザ・ループの原則（要件定義書 §17, §19）は最も重要な設計上の制約であり、新しい自動化を実装する場合も必ず明示的な管理者承認ステップで終わるようにすること。「システムが決定する」ような挙動は、設計に対するバグとして扱うべきである。

もう一つの中核的な設計思想が**「相互非公開型マッチング」**（要件定義書 §19, §29）である：個人の入力（空き予定）は幹事・管理者を含む他の誰にも一切公開せず、システムが導き出した出力（候補）のみを関係者全員に同時提示する。この非対称性のない構造により、「調整さん」型（全員の回答が公開される）やCalendly型（自分の予定を一方的に公開する）で生じがちな駆け引き・後出しジャンケンを構造的に排除する。実装上の具体的な制約として、**他メンバーの生の空き予定（Availability）を返す公開APIやUIを新規に追加してはならない**（`GET /communities/{id}/availability`は呼び出し元自身の分のみを返す。コミュニティ横断の空き予定取得はマッチング処理F-401の内部専用であり、DynamoDB物理設計書 §3.6, §4でもその非対称性を維持する設計になっている）。関係者に見えてよいのは、あくまでマッチング後の候補のみ。

初期ドメインは麻雀コミュニティ（四人麻雀・三人麻雀）だが、データモデルは意図的にゲーム非依存に保たれている（`communityType`、`Place`、ゲーム結果をJSONで柔軟に持たせる設計など）。これは将来的なポーカー、ボードゲーム、TRPG、スポーツ等への展開を見据えたものである。

MVPスコープとPhase2/3の切り分けは各ドキュメントに明示的に列挙されている（要件定義書 §22–23、機能要件書 §12, §21）。特に**MVP対象外**なのは：チャット、コミュニティ横断のグローバルマッチング、信頼スコア、相性分析、NG（組み合わせ回避）設定、Push/LINE通知、キャンセル後の欠員補充・繰り上げである。指示がない限りこれらに向けた実装は行わないこと。

## アーキテクチャ（設計ドキュメント上のターゲット）

サーバーレスAWS構成。単一AWSアカウント内で`dev-`/`staging-`/`prod-`のリソース名プレフィックスによって環境を分離する（MVPではアカウント分離は行わない）。

```text
User → CloudFront → S3 (React SPA) / API Gateway (Cognito Authorizer) → 7 domain Lambdas → DynamoDB (single table)
```

- **認証**：Amazon Cognito。JWT検証はすべてAPI GatewayのCognito Authorizerで完結し、独自の認証Lambdaは存在しない。各ドメインLambdaは検証済みのクレーム（`userId`等）をeventから受け取るのみで、認可（コミュニティ所属・権限）チェックのみを共有Lambda Layer経由で行う。
- **ユーザー登録**には公開RESTエンドポイントが無い。Cognito Post Confirmationトリガー経由で`UserLambda`が起動し、DynamoDBのプロフィールを作成する。
- **Lambdaはエンドポイント単位ではなくドメイン単位（7個）で分割**されている。各ドメインLambdaは内部でHTTPメソッド＋パスに応じてルーティングする：
  - `UserLambda` — プロフィール（Cognitoトリガー ＋ `/users/me`）
  - `CommunityLambda` — コミュニティ、メンバーシップ、招待、参加リクエスト、会場（`Place`）マスタ
  - `AvailabilityLambda` — 空き予定（バッチ登録含む）
  - `MatchingLambda` — 開催条件＋候補生成（重い/遅い処理のため他から分離。`EventConfirmed`を購読しコミュニティ横断の衝突検知も行う）
  - `EventLambda` — イベントライフサイクル、参加者、キャンセル申請、イベント全体の中止（最も複雑なステートマシン）
  - `ResultLambda` — 成績と集計
  - `NotificationLambda` — アプリ内通知レコード（MVPにはメール/Push/LINEチャネルは無い）
  - 操作ログ（`OperationLog`）専用のLambdaは無く、各ドメインLambdaが共有Layer関数経由で書き込む。
- **非同期/イベントフロー**：EventBridgeは後続処理のファンアウト（通知、コミュニティ横断の衝突検知）にのみ使用し、マッチングを自動起動するためには使わない。主なイベント：`EventConfirmed`、`EventCancelled`、`CancelApproved`、`CandidateConflictDetected`、`EventStatusChanged`。候補生成（F-401）は**MVPでは手動実行のみ**（管理者がAPIを呼ぶ）。内部ロジックは将来の定期実行/自動トリガーが新しいAPIを追加せずに同一関数を呼び出せるよう分離されている。
- **DynamoDB**：単一テーブル（`MeetFlowTable`）、オンデマンドキャパシティ、PITR有効、KMS暗号化。GSIは2本のみで、オーバーロードGSIパターンを採用：
  - GSI1（`ByUser`）— 「あるユーザーの○○」系の横断取得（所属コミュニティ、空き予定、参加イベント、成績、操作ログ）に加え、時間範囲をキーにした複数の衝突検知/公平性クエリにも使う。
  - GSI2（`ByAltId`）— コミュニティのパーティションを介さない直接IDルックアップ（例：`candidateId`のみで候補詳細を取得）。
  - 各エンティティはPK/SKのプレフィックス（`USER#`、`COMMUNITY#`、`INVITE#`、`EVENT#`、`PLACE#`、`LOG#`等）でテーブルを共有する。全エンティティ・キー一覧は`docs/MeetFlow_DynamoDB物理設計書_v1.8.md` §3、集約されたアクセスパターン一覧は§4を参照。新しいクエリを追加する前に必ず読むこと。このスキーマ全体は場当たり的なクエリではなく、事前に洗い出されたアクセスパターン集合の上に構築されている。
  - 部分適用してはいけない処理（参加リクエスト承認、OWNER変更、イベント承認）には`TransactWriteItems`を使用し、二重書き込みのレース（キャンセル申請の二重承認等）には`ConditionExpression`でガードする。
- **ダブルブッキング防止**は、ユーザーが複数コミュニティに所属しうるという前提から、意図的に二層・非対称な設計になっている：（1）イベント確定時に`Participant`のGSI1を時間範囲でクエリする同期的なハードチェックで、重複があれば確定を**ブロック**する（`409 PARTICIPANT_SCHEDULE_CONFLICT`）。対して（2）非同期の事後チェック（`CandidateMember`エンティティ＋`EventConfirmed`購読）は、管理者向けに`conflictWarning`フラグを立てるだけで、誰かを自動的に除外することは無い。マッチング/イベント確定まわりのコードを触る際は、この2つの仕組みを混同しないこと。
- **公平性指標**（`CandidateMember`の`fairnessCount`）と**衝突警告**は、あくまで管理者向けの表示専用シグナルであり、スコアリングや自動除外ロジックに組み込んではならない。これは上記の「システムが提案し、人間が判断する」という中核原則を反映したものである。

## API規約

- REST over HTTPS、JSON、`Authorization: Bearer {JWT}`。
- 統一されたレスポンス形式：`{"success": true, "data": {...}}` または `{"success": false, "error": {"code": "...", "message": "..."}}`。
- エラーコードは`docs/MeetFlow_エラーコード一覧_v1.2.md`にドメインごとに一元管理されており、それぞれHTTPステータスと、4種類のフロントエンド表示方式（インラインのフォームエラー / トースト / モーダル / 空状態画面）のいずれかに対応付けられている。新しいコードを作るのではなく既存のものを再利用し、既存のドメインエラーの命名パターン（例：`PARTICIPANT_SCHEDULE_CONFLICT`、`CANCEL_REQUEST_ALREADY_PROCESSED`）に従うこと。
- 人数条件は常に**範囲判定**（最低〜最大）であり、厳密一致では決してない。これは以前のバージョンからの意図的な修正なので、厳密一致に「単純化」して戻さないこと。
- フロントエンドはモバイルファースト（幅375〜430px）のReact SPAで、Tailwind CSS + shadcn/ui、画面下部のタブバーナビゲーション（ホーム / コミュニティ / 予定 / 通知 / マイページ）を採用する（`docs/MeetFlow_画面設計書_v1.6.md`参照）。PWA化（Service Worker + Webアプリマニフェスト）とWebプッシュ通知（VAPID鍵、Amazon SNS等は使わない）がMVPスコープに含まれる（要件定義書v1.3 27章）。

## CI/CD

GitHub → GitHub Actions → `test → build → deploy`、ブランチと環境の対応は以下の通り：`develop` → Development、`staging` → Staging、`main` → Production（mainマージ時に自動デプロイ）。

- `test`（CI）：`.github/workflows/ci.yml`として実装済み（詳細は上記「プロジェクトの状態」の`.github/workflows/`項目を参照）。AWS認証情報を必要としない検証のみのワークフロー。
- `build`/`deploy`（CD）：**計画中・未着手**。AWS側にGitHub Actions用のOIDC IAMロール、CDKブートストラップ済み環境（dev/staging/prod）が必要で、いずれも未準備。`develop`/`staging`ブランチ自体もまだ作成されていない（現状mainのみ運用）。MVP検証段階の現時点では、リポジトリルートの`DEPLOY.md`に従った手動`cdk deploy`＋手動フロントエンドアップロードのみで運用する。
