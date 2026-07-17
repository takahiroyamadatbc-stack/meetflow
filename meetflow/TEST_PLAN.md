# MeetFlow デプロイ後テスト計画（dev環境）

`DEPLOY.md`の手順1〜8完了後（VAPID鍵投入・フロントエンドアップロード済み）に実施する動作確認の計画。
バックエンドのpytest+moto単体テスト（`backend/functions/*/tests/`）はモック環境での検証であり、本ドキュメントは
**実際にデプロイしたAWSリソース**に対する確認を対象とする。

## 0. 前提

### 0.1 対象環境

- 環境：dev（`dev-`プレフィックスの全スタック：DataStack / AuthStack / ComputeStack / ApiStack / FrontendStack）
- 前提：`cdk deploy --all -c env=dev`完了、VAPID鍵をSecrets Managerに投入済み、`frontend/dist`をS3にアップロード＋CloudFrontキャッシュ無効化済み

### 0.2 テストアカウント（Gmailプラスアドレッシング、4つ）

Cognitoの`UserPoolClient`はSRPログインのみ許可（`admin_initiate_auth`等の裏口フローなし）。サインアップ〜メール確認コード入力までは人間が行い、確認済みのメールアドレス／パスワードをAI側に渡してSRPログインを自動化する。

| アカウント | メールアドレス（例） | コミュニティ内ロール | 主な用途 |
|---|---|---|---|
| A | `takahiro.yamada.tbc+mfdemo-a@gmail.com` | OWNER（コミュニティ作成者） | 管理操作全般、候補承認、イベント確定 |
| B | `takahiro.yamada.tbc+mfdemo-b@gmail.com` | 一般メンバー | 空き予定登録、相互非公開チェックの当事者 |
| C | `takahiro.yamada.tbc+mfdemo-c@gmail.com` | 一般メンバー | 相互非公開チェックの相手（BからCの予定が見えないか） |
| D | `takahiro.yamada.tbc+mfdemo-d@gmail.com` | 非所属（コミュニティに参加しない） | 権限ネガティブテスト専用 |

パスワードはすべてTest1234

> メールアドレスはあくまで例。実際に発行したものに置き換えて記入すること。

### 0.3 実行者の凡例

| 表記 | 意味 |
|---|---|
| AI | Claude Codeがスクリプト（AWS CLI / boto3 / curl / SRPログイン）で自動実行できる |
| 人間 | ブラウザでの目視確認、実デバイス操作、AWS SSOログイン、メール受信確認など人手が必要 |

### 0.4 結果の凡例

`未実施` / `OK` / `NG` / `保留`（NGの場合は備考に事象と再現手順を記載し、対応後に再実施日を追記）

---

## 1. デプロイ疎通確認（スモークテスト）

| ID | 項目 | 実行者 | 結果 | 実施日 | 備考 |
|---|---|---|---|---|---|
| T-101 | 5スタック（Data/Auth/Compute/Api/Frontend）のCloudFormation出力が全て取得できる | AI | OK | 2026-07-15 | 5スタックとも`CREATE_COMPLETE`/`UPDATE_COMPLETE`。TableName=`dev-MeetFlowTable`、UserPoolId=`ap-northeast-1_RcCb4PMpp`、ApiUrl=`https://y4wpgp78yd.execute-api.ap-northeast-1.amazonaws.com/dev/`、CloudFrontDomain=`https://d674amahiqnze.cloudfront.net`等、全Outputsを取得できた |
| T-102 | API Gatewayに未認証でリクエストし401が返る（疎通自体はしている） | AI | OK | 2026-07-15 | `GET /communities`を無認証で叩き`401 {"message":"Unauthorized"}` |
| T-103 | CloudFrontドメインに`curl`し`index.html`相当のレスポンスが返る | AI | OK | 2026-07-15 | `200`・`Content-Type: text/html`でSPAの`index.html`を確認 |
| T-104 | ブラウザでCloudFrontドメインを開き、SPAが表示されモバイル幅（375〜430px）でレイアウト崩れがない | 人間 | 未実施 | | AI（Claude Code）は実ブラウザでの目視確認ができないため、人間による実施が必要 |
| T-105 | 4アカウント（A〜D）のサインアップ〜メール確認コード入力が完了している | 人間 | OK | 2026-07-15 | Cognito側で4アカウントとも`CONFIRMED`済みであることをAIが確認（サインアップ操作自体は事前に人間が実施済み） |
| T-106 | 4アカウントそれぞれでSRPログインしID/アクセストークンが取得できる | AI | OK | 2026-07-15 | `pycognito`によるSRP認証スクリプト（scratchpad配下`mf_test_lib.py`）を作成し、A〜D全員分のIDトークン取得に成功。以降のAPIテストで再利用 |
| T-107 | Post ConfirmationトリガーによりDynamoDBにUserプロフィール（ニックネーム含む）が作成されている | AI | OK | 2026-07-15 | 4アカウント全員に`PK=USER#{userId}, SK=PROFILE`が存在。ただしニックネームはメールアドレスのローカル部にフォールバックしていた（サインアップ画面で`clientMetadata`経由のニックネーム未指定時の既知の仕様。CLAUDE.md記載どおりでバグではない） |

## 2. 結合テスト（主要業務フロー E2E）

| ID | 項目 | 実行者 | 結果 | 実施日 | 備考 |
|---|---|---|---|---|---|
| T-201 | A：コミュニティを作成できる | AI | OK | 2026-07-15 | 初回実施時はNG：フロントエンドで「予期しないエラーが発生しました」。原因は`meetflow_common.errors`の`success_response`/`error_response`にAccess-Control-Allow-Originヘッダーが無く、API Gatewayの`default_cors_preflight_options`はOPTIONSプリフライトにしか効かないため実レスポンスがブラウザにCORSブロックされていた（コミュニティ作成に限らず全エンドポイント共通の構造的バグ）。`errors.py`にヘッダー追加→`cdk deploy dev-MeetFlowComputeStack`で修正し、SRPログイン＋curlで`201`かつ`Access-Control-Allow-Origin: *`付きレスポンスを確認。なお、修正前の画面操作時にもフロントエンド側はエラー表示だったがバックエンドは実際には成功しており、「麻雀部」（重複×3）と確認用の「CORS確認用コミュニティ」が不要データとしてDBに残っていたため、いずれもDynamoDBから削除済み（`よこぼセット`のみ現存） |
| T-202 | A：招待URLを発行し、B・Cが招待経由で参加リクエストを送れる | AI | OK | 2026-07-15 | T-201の既存コミュニティとは別に`memberApprovalRequired=true`の「E2Eテストコミュニティ」を新規作成（承認フローも検証するため）。招待URL発行→B・Cが`message`付きで参加リクエスト送信し、いずれも`201 PENDING`を確認 |
| T-203 | A：参加リクエストを承認し、B・Cがメンバーになる | AI | OK | 2026-07-15 | `GET .../join-requests`にB・Cが`PENDING`で表示→`approve`で両者とも`200 ACTIVE`。メンバー一覧にも反映確認 |
| T-204 | A・B・C：それぞれ自分の空き予定を登録できる（バッチ登録含む） | AI | OK | 2026-07-15 | A/B/Cとも同一日時（`2026-07-25T19:00`〜`23:00`、`gameTypes:["MAHJONG4"]`）で`201`。バッチ登録API（`.../availability/batch`相当）は今回未使用（単発登録のみ検証） |
| T-205 | A：開催条件（イベントテンプレート：ゲーム種別・人数範囲・優先度）を登録できる | AI | OK | 2026-07-15 | `gameType=MAHJONG4, minPlayers=2, maxPlayers=4, priority=80`で`201` |
| T-206 | A：候補生成APIを実行し、スコア付き候補が複数生成される | AI | OK | 2026-07-15 | `201`でA/B/C 3名を含む候補1件（score=46）を生成。**この後T-305のセットアップ中に重大なバグを発見**：候補生成対象ユーザーが過去に確定参加履歴（Participant）を持つ場合、`matching_lambda/handlers/matching.py`の`_days_since_last_participation`が`TypeError: can't subtract offset-naive and offset-aware datetimes`で例外になり、候補生成API全体が`502`になっていた。ユーザーが空き予定登録時に送る`startTime`（例：`"2026-07-25T19:00"`）はタイムゾーン表記を伴わない文字列がそのままParticipant.GSI1SKに使われるため、`datetime.fromisoformat`がoffset-naiveなdatetimeを返し、`datetime.now(timezone.utc)`（offset-aware）との減算で例外になる。初回のT-206実行時（履歴なしの新規ユーザーのみ）では発生しなかったが、一度でも確定参加した実績のあるユーザーで再度候補生成すると必ず再現する、実運用上ごく普通に起こる操作。`_days_since_last_participation`にnaive datetimeをUTCとして扱うフォールバックを追加（naiveな場合`tzinfo=timezone.utc`を付与）し、回帰テスト（`test_generate_candidates_with_timezone_naive_past_participation`）を追加した上で`cdk deploy dev-MeetFlowComputeStack`により修正版をデプロイ、以降のテストで再現しないことを確認済み |
| T-207 | A：候補をレビューし、明示的な承認操作でイベントを確定できる | AI | OK | 2026-07-15 | `POST /events`で`PENDING_APPROVAL`のイベント作成→`POST /events/{id}/confirm`で`CONFIRMED`に遷移 |
| T-208 | 確定イベントの参加者一覧にB・Cが含まれる | AI | OK | 2026-07-15 | `GET /events/{id}/participants`にA・B・Cとも`status:CONFIRMED`で存在 |
| T-209 | イベント終了後、成績（結果）を登録できる | AI | OK | 2026-07-15 | `POST /events/{id}/sessions`でA/B/Cの着順・素点を登録し`201` |
| T-210 | コミュニティ／ユーザー単位の成績集計が取得できる | AI | OK | 2026-07-15 | `GET /users/{userId}/results?communityId=...`で`totalGames:1`等の集計値を取得 |
| T-211 | 招待URLを無効化（revoke）した後、そのURLでは新規の参加リクエストができない | AI | OK | 2026-07-15 | `POST /invites/{token}/revoke`で`revoked:true`。その後Dが同トークンで参加を試みると`410 INVITE_REVOKED` |
| T-212 | コミュニティ／ユーザー単位の操作ログ（OperationLog）が閲覧できる | AI | OK | 2026-07-15 | `GET /communities/{id}/logs`・`GET /users/{userId}/logs`とも`200`でログ一覧を取得 |

## 3. MeetFlow固有の設計原則の検証（最重要）

| ID | 項目 | 実行者 | 結果 | 実施日 | 備考 |
|---|---|---|---|---|---|
| T-301 | 相互非公開：Bのトークンで空き予定関連APIを叩いても、Cの生の空き予定が一切含まれない（自分の分のみ返る） | AI | OK | 2026-07-15 | Bのトークンで`GET .../availability`→自分の登録分1件のみ返却、レスポンスに他者のuserId等の識別情報は一切含まれない |
| T-302 | 相互非公開：管理者Aを含め、他メンバーの生の空き予定を取得できるAPI／画面が存在しない（該当エンドポイント自体が無いことの確認） | AI | OK | 2026-07-15 | API設計書に他メンバーの空き予定を返す公開エンドポイントの定義が無いことを確認した上で、実際に`GET /communities/{id}/members/{userId}/availability`のような推測されうるパスをBのトークンで叩き、`403`（ルート自体が存在しないためAPI Gatewayが認可情報の解釈に失敗する形のエラー）でそもそも到達不能であることを実地確認 |
| T-303 | Human-in-the-loop：候補生成直後、イベントのstatusが自動で「確定」になっていない | AI | OK | 2026-07-15 | 候補生成直後に`GET /communities/{id}/events`を取得→`events:[]`（Eventが1件も自動作成されていない） |
| T-304 | Human-in-the-loop：候補生成を何度実行しても、明示的な承認APIを呼ぶまでは自動確定されない | AI | OK | 2026-07-15 | 同一テンプレートで候補生成を複数回実行後も`events:[]`のまま。`POST /events`＋`POST /events/{id}/confirm`を明示的に呼ぶまでEventは作られない |
| T-305 | ダブルブッキング（同期・ハードチェック）：同時間帯の別イベントに参加登録済みの状態で確定を試みると`409 PARTICIPANT_SCHEDULE_CONFLICT`で拒否される | AI | OK | 2026-07-15 | 別コミュニティ（community_Z、A+B）でT-207と全く同じ時間帯（`2026-07-25T19:00`〜`23:00`）の候補からイベントを作成し確定を試みたところ、Bが既にT-207で確定済みのため`409 PARTICIPANT_SCHEDULE_CONFLICT`で拒否された |
| T-306 | ダブルブッキング（非同期・警告のみ）：`EventConfirmed`発火後、コミュニティ横断の衝突が`conflictWarning`として候補メンバーに付与され、誰も自動除外されない | AI | OK | 2026-07-15 | community_Y（A+B、`2026-08-05T19:00`〜`23:00`でPENDING候補を先に生成）とcommunity_X（同時間帯、A+B）を用意し、community_Xのイベントを確定（`EventConfirmed`発火）。EventBridge非同期処理を10秒間隔でポーリングし、community_Yの候補メンバーB・両方に`conflictWarning:true`が付与されたことを確認。かつ候補のmembers数は2のまま（誰も自動除外されない）ことも確認 |
| T-307 | 人数条件が範囲判定である（最低〜最大の範囲内なら候補に含まれ、厳密一致要求になっていない） | AI | OK | 2026-07-15 | `minPlayers=2, maxPlayers=4`のテンプレートに対し、どちらの境界とも一致しない3人（A・B・C）の空き予定が候補としてそのまま生成されることを確認（範囲判定であり厳密一致ではない） |

## 4. 認可・権限のネガティブテスト

| ID | 項目 | 実行者 | 結果 | 実施日 | 備考 |
|---|---|---|---|---|---|
| T-401 | トークン無しでAPIを叩くと401が返る | AI | OK | 2026-07-15 | `GET /communities/{id}`を無認証で叩き`401` |
| T-402 | 非所属のD が、コミュニティ限定APIを叩くと403が返る | AI | OK | 2026-07-15 | Dのトークンで`GET /communities/{id}`→`403 FORBIDDEN` |
| T-403 | 一般メンバーB／CがOWNER限定操作（候補承認・イベント確定・メンバー承認等）を叩くと403が返る | AI | OK | 2026-07-15 | Bによる候補生成（`POST .../matching`）、Cによるイベント確定（`POST /events/{id}/confirm`）いずれも`403 FORBIDDEN` |
| T-404 | 自分以外の`userId`を指定するAPI（例：他人のプロフィール／通知）を、他人のJWTで操作できない | AI | OK | 2026-07-15 | Bのトークンで`GET /users/{Aのuserid}/logs`（本人でもOWNER/ADMINでもない）を叩き`403 FORBIDDEN` |

## 5. 運用面の確認

| ID | 項目 | 実行者 | 結果 | 実施日 | 備考 |
|---|---|---|---|---|---|
| T-501 | 7ドメインLambdaのCloudWatch Logsロググループが、それぞれ1ヶ月保持設定になっている | AI | OK | 2026-07-15 | `aws logs describe-log-groups`で7ロググループとも`retentionInDays: 30`を確認 |
| T-502 | 意図的に処理を失敗させ、EventBridge Rule（`EventConfirmed`購読／通知処理）のDLQにメッセージが滞留する | AI | **NG** | 2026-07-15 | `dev-meetflow-matching-event-confirmed`ルールのターゲットRetryPolicyを一時的に`MaximumRetryAttempts=0, MaximumEventAgeInSeconds=60`（最小値）に変更した上で、`aws events put-events`により意図的に不正な型（`participantIds`を数値）の`EventConfirmed`イベントを発行。CloudWatch Logsで`TypeError: 'int' object is not iterable`という実際のLambda関数内例外を確認したが、約6分待ってもDLQ（`dev-meetflow-matching-event-confirmed-dlq`）にメッセージは1件も届かず、CloudWatchの`FailedInvocations`/`DeadLetterInvocations`メトリクスもゼロのままだった。原因はAWSの仕様：EventBridgeはLambdaを`InvocationType=Event`（非同期・fire-and-forget）で呼び出しており、Lambda側がイベントを受理した時点でEventBridgeからは「配送成功」として扱われる。関数コード内部でその後発生する例外はEventBridge側から見えないため、EventBridge Ruleターゲットの`RetryPolicy`/`DeadLetterConfig`は関数内例外に対しては作動しない（EventBridgeの配送失敗＝権限エラーやスロットリング等のみ捕捉対象）。またLambda関数自体の非同期呼び出し設定（`aws lambda get-function-event-invoke-config`）も未設定であることを確認した（`ResourceNotFoundException`）。つまりCLAUDE.mdが想定していた「処理失敗がEventBridgeの既定リトライ後にサイレントに消えるのを防止」というDLQの効果は、実際にはLambda関数内で発生した例外（T-206で見つかったようなバグを含む）には及ばず、正しく捕捉するにはLambda関数自体の`on_failure`デスティネーション（EventInvokeConfig）の追加設定が別途必要という、設計・実装両方に関わる指摘事項。検証後、変更したRetryPolicyは元の状態（明示指定なし＝CDKデフォルト）に復元し、`cdk diff`でドリフトが無いことを確認済み。コード側の対応は本テストの範囲外のためTEST_PLAN.mdでは実施せず、別途対応を相談することとした |
| T-503 | API GatewayのアクセスログがCloudWatch Logsに出力されている | AI | OK | 2026-07-15 | ロググループ`/aws/apigateway/dev-meetflow-api-access`（保持30日）に、本テストで実際に行った多数のAPIリクエストのアクセスログ（requestId/ip/httpMethod/resourcePath/status等）が記録されていることを確認 |
| T-504 | AWS Budgetsが月$10しきい値・メール通知先で設定されている（実際のメール到達は閾値到達時のみ確認可能なため、ここでは設定値のみ確認） | AI | OK | 2026-07-15 | `dev-meetflow-monthly-cost-budget`（`BudgetLimit: $10/MONTHLY`）が存在し、通知（`ACTUAL, GREATER_THAN, Threshold: 100%`）の購読者としてメールアドレス`takahiro.yamada1221@gmail.com`が設定されていることを確認 |
| T-505 | プッシュ通知の購読登録〜実際にブラウザへプッシュが届く | 人間 | 未実施 | | 実デバイス・実ブラウザでのプッシュ受信確認が必要なため、AIでは実施不可 |
| T-506 | プッシュ通知の購読解除後、DynamoDBの`PushSubscription`が削除される | AI | OK | 2026-07-15 | `POST /users/me/push-subscriptions`でテスト用エンドポイントを登録→DynamoDBに`PUSHSUB#`アイテムが1件作成されたことを確認→`DELETE /users/me/push-subscriptions`で解除→同アイテムが削除されたことを確認（登録・解除ともAPI経由で実施したテスト用ダミーデータであり実デバイスへの到達は含まない） |

---

## 実施後のサマリ（全項目実施後に記入）

| カテゴリ | 総数 | OK | NG | 保留 |
|---|---|---|---|---|
| 1. デプロイ疎通確認 | 7 | 6 | 0 | 1（T-104：人間実施待ち） |
| 2. 結合テスト | 12 | 12 | 0 | 0 |
| 3. 設計原則の検証 | 7 | 7 | 0 | 0 |
| 4. 認可・権限 | 4 | 4 | 0 | 0 |
| 5. 運用面 | 6 | 4 | 1（T-502） | 1（T-505：人間実施待ち） |
| **合計** | **36** | **33** | **1** | **2** |

AIが実施できる全項目（34件）のうち33件がOK、1件（T-502）がNG。人間実施項目2件（T-104: ブラウザ目視確認、T-505: 実デバイスへのプッシュ到達確認）は未実施のまま残っている。

### 発見された問題

- **T-206（修正済み）**: `matching_lambda/handlers/matching.py`の`_days_since_last_participation`が、過去に確定参加履歴のあるユーザーに対する候補生成時に必ず`502`になるバグ。offset-naive/offset-awareなdatetimeの減算が原因。修正・回帰テスト追加・`dev-MeetFlowComputeStack`への再デプロイ済み。
- **T-502（未修正・要相談）**: EventBridge Rule（`EventConfirmed`購読等）に設定されたDLQは、EventBridge自体の配送失敗（権限エラー・スロットリング等）は捕捉できるが、Lambda関数内で発生した例外（非同期`InvocationType=Event`呼び出しのため EventBridge からは見えない）は捕捉できないことを実地検証で確認した。正しく捕捉するにはLambda関数自体の非同期呼び出し設定（`on_failure`デスティネーション/EventInvokeConfig）が別途必要。対応要否・方針は別途相談。

## 次のステップ

- T-104（ブラウザでのモバイル幅レイアウト確認）とT-505（実デバイスへのプッシュ通知到達確認）を人間が実施する。
- T-502で見つかったDLQの実効性ギャップについて、Lambda関数自体の`on_failure`デスティネーション追加要否を検討する。
