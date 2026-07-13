# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 参照すべき設計書

実装前に必ず docs/ 内の以下を読むこと:

- 要件定義書v1.3
- 機能要件書v1.3
- DynamoDB物理設計書v1.4（特に単一テーブル設計のPK/SK/GSI1/GSI2）
- Lambda設計書v1.2（7ドメイン構成、IAM権限は「案C」を採用）
- API設計書v1.5
- 画面設計書v1.3
- エラーコード一覧v1.2
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

## Git運用方針

- 意味のある単位(1機能・1修正)ごとにローカルcommitする
- commitメッセージは Conventional Commits形式(feat:, fix:, docs: 等)で書く
- git pushは明示的に指示されるまで実行しない
- developブランチへの直接pushはしない。作業用ブランチ(feature/xxx)を切ってそこにpushする

## プロジェクトの状態

MeetFlowは設計フェーズを終え、バックエンドの実装に着手している。`docs/`配下の日本語設計ドキュメント群は実装対象の仕様書として引き続き最優先で参照すること（背景資料ではない）。

- `infra/`：AWS CDK（Python）。`MeetFlowDataStack`（DynamoDB単一テーブル）、`MeetFlowAuthStack`（Cognito）、`MeetFlowComputeStack`（共有Lambda Layer + 7ドメインLambda）を実装済み。AvailabilityLambdaの`events:PutEvents`権限（F-205用）は反映済み。PushSubscriptionまわりの新規Lambda処理・IAM権限（Lambda設計書v1.2 §9.2-9.4、NotificationLambda）は未反映
- `backend/`：7ドメインLambda（User/Community/Availability/Matching/Event/Result/Notification）+ 共通Layer（`meetflow_common`：DynamoDB/認証/ルーティング/EventBridge/エラーレスポンス等の共通処理）を実装済み。AvailabilityLambdaには要件定義書v1.3 §28（F-205/F-206、空き予定提出リクエスト）のハンドラーを追加済み。`AvailabilityRequestCreated`イベントはpublishのみで、NotificationLambda側の購読・通知作成は未実装（別タスク）。pytest+moto(mock_aws)による単体テストは`community_lambda`・`availability_lambda`が整備済み（`functions/{domain}_lambda/tests/`）。他5ドメインは同じパターンを横展開すればよい状態で、**未着手**
  - **注意**：各ドメインの`tests/conftest.py`は、同名の`handlers`パッケージ・`_factories`モジュールが複数ドメイン間で衝突しないよう、自分のテストがimportされる前に`sys.modules`から該当名を退避させている（`community_lambda`/`availability_lambda`のconftest.py参照）。新しいドメインにテストを追加する際もこのパターンを踏襲すること。踏襲しないと、そのドメイン単体では通るのに`pytest`をbackend全体に対して実行した時だけ`ImportError`になる（先に収集された他ドメインの同名モジュールがsys.modulesにキャッシュされ、後続ドメインのimportを壊すため）。
- `frontend/`：未着手（空のプレースホルダー）
- `.github/workflows/`：未着手

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
  - 各エンティティはPK/SKのプレフィックス（`USER#`、`COMMUNITY#`、`INVITE#`、`EVENT#`、`PLACE#`、`LOG#`等）でテーブルを共有する。全エンティティ・キー一覧は`docs/MeetFlow_DynamoDB物理設計書_v1.4.md` §3、集約されたアクセスパターン一覧は§4を参照。新しいクエリを追加する前に必ず読むこと。このスキーマ全体は場当たり的なクエリではなく、事前に洗い出されたアクセスパターン集合の上に構築されている。
  - 部分適用してはいけない処理（参加リクエスト承認、OWNER変更、イベント承認）には`TransactWriteItems`を使用し、二重書き込みのレース（キャンセル申請の二重承認等）には`ConditionExpression`でガードする。
- **ダブルブッキング防止**は、ユーザーが複数コミュニティに所属しうるという前提から、意図的に二層・非対称な設計になっている：（1）イベント確定時に`Participant`のGSI1を時間範囲でクエリする同期的なハードチェックで、重複があれば確定を**ブロック**する（`409 PARTICIPANT_SCHEDULE_CONFLICT`）。対して（2）非同期の事後チェック（`CandidateMember`エンティティ＋`EventConfirmed`購読）は、管理者向けに`conflictWarning`フラグを立てるだけで、誰かを自動的に除外することは無い。マッチング/イベント確定まわりのコードを触る際は、この2つの仕組みを混同しないこと。
- **公平性指標**（`CandidateMember`の`fairnessCount`）と**衝突警告**は、あくまで管理者向けの表示専用シグナルであり、スコアリングや自動除外ロジックに組み込んではならない。これは上記の「システムが提案し、人間が判断する」という中核原則を反映したものである。

## API規約

- REST over HTTPS、JSON、`Authorization: Bearer {JWT}`。
- 統一されたレスポンス形式：`{"success": true, "data": {...}}` または `{"success": false, "error": {"code": "...", "message": "..."}}`。
- エラーコードは`docs/MeetFlow_エラーコード一覧_v1.2.md`にドメインごとに一元管理されており、それぞれHTTPステータスと、4種類のフロントエンド表示方式（インラインのフォームエラー / トースト / モーダル / 空状態画面）のいずれかに対応付けられている。新しいコードを作るのではなく既存のものを再利用し、既存のドメインエラーの命名パターン（例：`PARTICIPANT_SCHEDULE_CONFLICT`、`CANCEL_REQUEST_ALREADY_PROCESSED`）に従うこと。
- 人数条件は常に**範囲判定**（最低〜最大）であり、厳密一致では決してない。これは以前のバージョンからの意図的な修正なので、厳密一致に「単純化」して戻さないこと。
- フロントエンドはモバイルファースト（幅375〜430px）のReact SPAで、Tailwind CSS + shadcn/ui、画面下部のタブバーナビゲーション（ホーム / コミュニティ / 予定 / 通知 / マイページ）を採用する（`docs/MeetFlow_画面設計書_v1.3.md`参照）。PWA化（Service Worker + Webアプリマニフェスト）とWebプッシュ通知（VAPID鍵、Amazon SNS等は使わない）がMVPスコープに含まれる（要件定義書v1.3 27章）。

## CI/CD（計画中）

GitHub → GitHub Actions → `test → build → deploy`、ブランチと環境の対応は以下の通り：`develop` → Development、`staging` → Staging、`main` → Production（mainマージ時に自動デプロイ）。ワークフローファイルはまだ存在しない。
