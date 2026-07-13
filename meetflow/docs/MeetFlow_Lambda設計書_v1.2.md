# MeetFlow Lambda設計書 v1.2

> 要件定義書v1.1・機能要件書v1.1・API設計書v1.1・DynamoDB物理設計書v1.1を踏まえて設計。v1.1→v1.2は要件定義書v1.3・機能要件書v1.3・API設計書v1.5・DynamoDB物理設計書v1.4を踏まえて更新。
> **設計方針決定：ドメイン単位（7個）+ マッチング処理の分離**

---
次はご提示いただいた選択肢2番目の「Lambda共通Layer + UserLambda」に進み、このメソッドを使ってPost Confirmationトリガーを実際に接続する流れになります。進めてよければお知らせください。
## 1. 設計方針

- Lambdaは**ドメイン単位**で分離する（エンドポイント単位の細分化はしない）
- 1つのドメインLambda内では、API Gatewayからのルーティング情報（HTTPメソッド＋パス）に応じて内部でハンドラー関数を振り分ける（ルーター的な構成）
- **重い処理（マッチング候補生成）は独立したLambdaに分離する**。理由：処理時間・メモリ使用量が他のCRUD処理と性質が異なり、タイムアウト設定やメモリ割当を個別最適化したいため
- Lambda間は直接呼び出さず、非同期処理はEventBridge経由で連携する
- ユーザー登録はAPI Gateway経由の公開エンドポイントを持たず、**Cognito Post Confirmationトリガー**として実装する
- 認証（JWT検証）は独自Lambdaを作らず、**API GatewayのCognito Authorizer**に任せる。各ドメインLambdaはAPI Gatewayが検証済みのクレーム（userId等）をevent経由で受け取るだけでよい

---

## 2. Lambda一覧（7ドメイン + 補助）

| Lambda名 | ドメイン | 対応API領域 |
|---|---|---|
| UserLambda | ユーザー・プロフィール | 3章 |
| CommunityLambda | コミュニティ・メンバー・招待・会場 | 4章, 8.5, 8.6 |
| AvailabilityLambda | 空き予定 | 5章 |
| **MatchingLambda**（分離） | 開催条件・マッチング候補生成 | 6章, 7章 |
| EventLambda | イベント・参加者・キャンセル | 8章（8.5/8.6除く）, 9章 |
| ResultLambda | 成績管理 | 10章 |
| NotificationLambda | 通知 | 11章 |

> 操作ログ（OperationLog）は専用Lambdaを持たず、各ドメインLambda内の共通関数（Lambda Layerとして共有）から書き込む。

---

## 3. UserLambda

### 3.1 トリガー

| トリガー | 用途 |
|---|---|
| Cognito Post Confirmationトリガー | ユーザー登録確定時にDynamoDB Userプロフィールを作成（F-001） |
| API Gateway | プロフィール取得・更新 |

### 3.2 ハンドラー

| メソッド/パス | 対応機能 |
|---|---|
| （Cognitoトリガー、パスなし） | F-001 ユーザー登録 |
| `GET /users/me` | F-003 プロフィール取得（API 3.1） |
| `PUT /users/me` | F-003 プロフィール更新（API 3.2） |

### 3.3 IAM最小権限

- DynamoDB: `PutItem`（Userプロフィール作成時のみ）, `GetItem`, `UpdateItem`（`PK=USER#*, SK=PROFILE`に限定したリソースポリシー）
- Cognitoトリガー用の実行権限

---

## 4. CommunityLambda

### 4.1 トリガー

API Gatewayのみ。

### 4.2 ハンドラー

| メソッド/パス | 対応機能 |
|---|---|
| `POST /communities` | F-101 コミュニティ作成（`communityType=PERSONAL`固定で保存） |
| `GET /communities` | 所属コミュニティ一覧（GSI1経由） |
| `PUT /communities/{communityId}` | コミュニティ情報更新 |
| `POST /communities/{communityId}/invite` | F-102 招待URL発行 |
| `POST /invites/{token}/join` | F-103 招待参加。`memberApprovalRequired`で処理分岐 |
| `GET /communities/{communityId}/members` | F-104 メンバー一覧 |
| `PUT /communities/{communityId}/members/{userId}` | F-104 権限変更・一時停止・退出処理 |
| `POST /communities/{communityId}/join-requests/{requestId}/approve` | F-104b 参加リクエスト承認（`TransactWriteItems`でJoinRequest更新＋Membership作成） |
| `POST /communities/{communityId}/join-requests/{requestId}/reject` | F-104c 参加リクエスト却下 |
| `POST /communities/{communityId}/owner-transfer` | F-106 管理者変更（`TransactWriteItems`で新OWNER付与＋元OWNERをMEMBERに更新） |
| `GET /communities/{communityId}/locations` | F-107 会場一覧（Place、GSI1経由） |
| `POST /communities/{communityId}/locations` | F-107 会場登録（Place、`ownerType=COMMUNITY`固定） |

### 4.3 IAM最小権限

- DynamoDB: `PutItem`/`GetItem`/`UpdateItem`/`Query`（Community, Membership, Invite, JoinRequest, Place の各PKプレフィックスに限定）
- `TransactWriteItems`（参加リクエスト承認、OWNER変更のみ）

### 4.4 補足

> **[整合確認]** `communityType`・Placeの`ownerType`はDynamoDB物理設計書v1.1で定義済み。CommunityLambdaはこれらを意識するが、STORE/OFFICIAL向けの分岐処理はPhase3以降で実装する（MVPでは常にPERSONAL/COMMUNITY固定）。

---

## 5. AvailabilityLambda **[v1.2修正]**

### 5.1 トリガー

API Gatewayのみ。

### 5.2 ハンドラー **[v1.2修正]**

| メソッド/パス | 対応機能 |
|---|---|
| `POST /communities/{communityId}/availability` | F-201 空き予定登録 |
| `POST /communities/{communityId}/availability/batch` | 複数日カレンダー登録用バッチ登録（25件超は内部でチャンク分割し`BatchWriteItem`を複数回実行） |
| `GET /communities/{communityId}/availability` | F-204 空き予定一覧 |
| `PUT /availability/{availabilityId}` | F-202 空き予定編集 |
| `DELETE /availability/{availabilityId}` | F-203 空き予定削除 |
| `POST /communities/{communityId}/availability-requests` | **F-205 空き予定提出リクエスト作成（API設計書v1.5 5.5）[v1.2新規]** |
| `GET /communities/{communityId}/availability-requests` | **提出リクエスト一覧（API設計書v1.5 5.6）[v1.2新規]** |
| `GET /communities/{communityId}/availability-requests/{requestId}/pending-members` | **F-206 未提出メンバー確認（API設計書v1.5 5.7）[v1.2新規]** |

> **[MVP方針確認]** 空き予定登録後にEventBridgeへイベントを自動発行する処理は**入れない**。前回決定「F-401マッチング実行はMVPでは管理者による手動実行のみ」のため、登録時の自動マッチングトリガーは行わない。
>
> **[v1.2新規]** 空き予定提出リクエスト作成時のみ、対象メンバーへの通知のために`AvailabilityRequestCreated`イベントをEventBridgeへ発行する（7.3参照）。マッチング実行とは無関係の通知専用フローであり、上記のMVP方針とは矛盾しない。未提出メンバー確認（F-206）はDynamoDB物理設計書v1.4 3.18の通り、対象メンバーごとにAvailabilityの既存GSI1を対象期間でQueryする軽量な実装とする（新規GSIなし）。

### 5.3 IAM最小権限 **[v1.2修正]**

- DynamoDB: `PutItem`/`BatchWriteItem`/`GetItem`/`UpdateItem`/`DeleteItem`/`Query`（Availability, **AvailabilityRequest** [v1.2追加] 関連のPK/SKプレフィックスに限定）
- **`events:PutEvents`（`AvailabilityRequestCreated`発行用）[v1.2追加]**

---

## 6. MatchingLambda（分離）

重い処理のため独立させる。開催条件（EventTemplate）とマッチング候補生成の両方をこのLambdaが担当する。

### 6.1 トリガー **[v1.1修正]**

| トリガー | 用途 |
|---|---|
| API Gateway | 開催条件CRUD、候補生成の手動実行、候補一覧・詳細取得 |
| EventBridge Scheduler（将来） | 定期実行（MVPでは未設定） |
| **EventBridge（`EventConfirmed`購読）** | **他コミュニティでイベントが確定した際、自コミュニティのPENDING候補に衝突警告を立てる（衝突検知、6.6参照）[v1.1新規]** |

### 6.2 ハンドラー

| メソッド/パス | 対応機能 |
|---|---|
| `POST /communities/{communityId}/event-templates` | F-301 開催条件作成 |
| `GET /communities/{communityId}/event-templates` | F-302 開催条件一覧 |
| `PUT /event-templates/{templateId}` | F-303 開催条件編集 |
| `DELETE /event-templates/{templateId}` | F-304 開催条件削除 |
| `POST /communities/{communityId}/matching` | F-401 マッチング候補生成（**MVPでは管理者の手動実行のみ**） |
| `GET /communities/{communityId}/matching/candidates` | F-404 候補一覧。**[v1.1追加]** 各候補・各メンバーについて`conflictWarning`と「候補止まり」回数（公平性指標）を付与して返却 |
| `GET /matching/candidates/{candidateId}` | F-404 候補詳細（GSI2経由） |
| （EventBridgeイベント受信、パスなし） | **[v1.1新規]** 6.6参照 |

### 6.3 処理フロー（F-401）**[v1.1修正]**

```
開催条件取得
  ↓
コミュニティの空き予定を期間指定でQuery（AvailabilityテーブルPK=COMMUNITY#{id}, SK between AVAIL#{from}~{to}）
  ↓
条件照合（F-402: 人数は範囲内判定）
  ↓
スコア計算（F-403: 信頼度は対象外＝Phase2。加点要素関数は将来の信頼度/NG設定追加を見据えて分離した関数として実装）
  ↓
MatchCandidate保存
  ↓
候補メンバー1人ごとにCandidateMemberレコードを書き込み [v1.1新規]（DynamoDB物理設計書v1.3 3.11b）
```

### 6.4 設定

- タイムアウト：デフォルト3秒→**30秒に拡張**（性能目標「候補生成10秒以内」に対し余裕を持たせる）
- メモリ：512MB〜（コミュニティ規模拡大時に見直し）
- 将来、信頼度・相性分析・NG設定（Phase2/3）が加わってもこのLambda内の関数分割で対応できるよう、スコア計算部分は独立関数として実装しておく

### 6.5 IAM最小権限 **[v1.1修正]**

- DynamoDB: `Query`（Availability, EventTemplate）, `PutItem`/`GetItem`/`Query`（MatchCandidate、GSI2含む）, **`PutItem`/`UpdateItem`/`Query`（CandidateMember、GSI1含む）[v1.1追加]**
- **`events:PutEvents`（`CandidateConflictDetected`発行用）[v1.1追加]**
- EventBridgeルール（`EventConfirmed`）のターゲットとして呼び出されるための実行権限

### 6.6 実行契機についての補足

> **[前回決定の反映]** MVPでは「管理者による手動実行（API呼び出し）」のみ有効。ただし内部処理は「開催条件（テンプレート）ID単位の実行」として関数化しておき、将来のEventBridge Scheduler定期実行や空き予定登録時の自動トリガーからも同一関数を呼び出せる構成とする。API自体の追加は不要（呼び出し元が増えるだけ）。

### 6.7 ダブルブッキング事後検知（衝突検知）**[v1.1新規]**

EventLambdaが発行する`EventConfirmed`イベントをMatchingLambdaが購読し、以下を実行する。

```
EventConfirmed受信（確定イベントの参加者userId一覧・時間帯を含む）
  ↓
各参加者について、CandidateMemberのGSI1（USER#{userId}, GSI1SK between CANDIDATE#{startTime}~{endTime}）をQuery
  ↓
時間帯が重なるPENDING状態の候補が見つかった場合、該当CandidateMemberに conflictWarning=true を設定
  ↓
該当コミュニティへ CandidateConflictDetected イベントをEventBridgeへ発行
  ↓
NotificationLambdaが該当コミュニティの管理者へ通知
```

> 前回会話の「候補3：確定時ハードチェック」と役割が異なる点に注意。**7.2のハードチェックは"自分のイベント確定時に他の確定済みイベントと衝突しないか"を防止する処理、本節は"他コミュニティで確定した結果、自分のPENDING候補が矛盾していないか"を事後的に検知して知らせるだけの処理**。システムは除外・自動キャンセルを行わず、あくまで管理者への気づき情報として`conflictWarning`フラグを立てるだけに留める（要件定義書17章の設計思想準拠）。

### 6.8 公平性指標（候補止まり回数）の算出 **[v1.1新規]**

`GET /communities/{communityId}/matching/candidates`のレスポンス生成時、候補メンバーごとに以下を算出し付与する。

```
CandidateMemberのGSI1（USER#{userId}）を直近30〜60日の範囲でQuery
  ↓
status != CONFIRMED の件数をカウント
  ↓
候補一覧レスポンスの該当メンバーに fairnessCount として付与
```

> スコアリング（F-403）には組み込まない。候補一覧画面（画面設計書v1.2 S-12）でバッジ表示するだけの、管理者向け参考情報として位置づける。

---

## 7. EventLambda

イベントのライフサイクル管理・参加者管理・個人キャンセル・イベント全体の中止を担当する、最も状態遷移が複雑なドメイン。

### 7.1 トリガー

| トリガー | 用途 |
|---|---|
| API Gateway | イベント作成・承認・詳細取得・参加者管理・キャンセル系 |
| EventBridge | イベント状態変化を検知した他ドメイン（Notification等）への通知発行元 |

### 7.2 ハンドラー

| メソッド/パス | 対応機能 |
|---|---|
| `POST /events` | F-501 イベント作成（`locationId`/`locationNote`を含む。候補選択 or 手動作成） |
| `GET /events/{eventId}` | F-504 イベント詳細（会場情報を含めて返却） |
| `POST /events/{eventId}/confirm` | F-502 イベント承認。**[v1.1修正]** `TransactWriteItems`実行前に、候補メンバー全員分についてダブルブッキング事前チェック（7.2b参照）を行う。問題なければEvent状態更新＋Participant一括作成 → EventBridgeへ`EventConfirmed`発行 |
| `POST /events/{eventId}/cancel` | F-605 **イベント全体の中止**（管理者のみ）→ EventBridgeへ`EventCancelled`発行（全参加者への通知トリガー） |
| `GET /events/{eventId}/participants` | 9.1 参加者一覧 |
| `POST /events/{eventId}/cancel-request` | F-601 **個人キャンセル申請**（MVP対象。自動では確定しない） |
| `POST /events/{eventId}/cancel-requests/{userId}/approve` | F-602 **キャンセル申請承認**（管理者のみ。`ConditionExpression: status=PENDING`で二重承認防止）→ EventBridgeへ`CancelApproved`発行 |

> **[v1.1整合]** `EventLambda`は8.4（v1.0 API設計書での旧称）を「イベント中止」、9.2/9.3を「個人キャンセル申請・承認」として明確に役割分離している。

### 7.2b イベント承認時のダブルブッキング事前チェック **[v1.1新規]**

```
承認リクエスト受信
  ↓
候補メンバー全員について、Participant GSI1（USER#{userId}, GSI1SK between PARTICIPANT#{eventStartTime}~{eventEndTime}）をQuery
  ↓
status=CONFIRMEDの既存Participantが1件でも見つかった場合
  ↓
TransactWriteItemsを実行せず、409 PARTICIPANT_SCHEDULE_CONFLICT エラーを返却して中断
  ↓
（問題なければ）TransactWriteItemsでEvent状態更新＋Participant一括作成 → EventConfirmed発行
```

> 前回会話の「候補3」に対応。実害（二重予定の確定）を防ぐ最後の砦として、承認処理の中で同期的に実行する。DynamoDB物理設計書v1.3 5章のトランザクション設計方針に準拠。

### 7.3 EventBridge発行イベント一覧

| イベント名 | 発行タイミング | 主なターゲット |
|---|---|---|
| `EventConfirmed` | 承認処理完了時 | NotificationLambda（参加者へ確定通知）、**MatchingLambda（衝突検知、6.7参照）[v1.1追加]** |
| `EventCancelled` | イベント中止時 | NotificationLambda（全参加者へ中止通知） |
| `CancelApproved` | キャンセル承認完了時 | NotificationLambda（本人へ受理通知）※欠員補充（F-603）はPhase2のため、MVPでは通知のみで完結し後続処理は発火しない |
| `EventStatusChanged` | 状態遷移のたび | EventStatusHistoryへの追記（EventLambda内の共通関数で直接書き込みでも可。将来ここだけ切り出す可能性あり） |
| **`CandidateConflictDetected`** [v1.1新規] | MatchingLambdaが衝突を検知した時 | NotificationLambda（該当コミュニティの管理者へ通知） |
| **`AvailabilityRequestCreated`** [v1.2新規] | AvailabilityLambdaが空き予定提出リクエストを作成した時（5.2参照） | NotificationLambda（対象メンバーへ通知） |

### 7.4 IAM最小権限 **[v1.1修正]**

- DynamoDB: `PutItem`/`GetItem`/`UpdateItem`/`Query`（Event, Participant, CancelRequest, EventStatusHistory。**ParticipantはGSI1も含む[v1.1追加]（ダブルブッキングチェック用）**）
- `TransactWriteItems`（承認処理）
- `events:PutEvents`（EventBridgeへの発行権限）

### 7.5 Phase2への拡張ポイント（現時点では未実装）

- 欠員補充（F-603）：`CancelApproved`イベントを受けて起動する別Lambda（`SubstituteLambda`等）を追加する想定。EventBridgeイベント連鎖で組むかStep Functionsを使うかは実装段階で決定（前回の保留事項どおり）
- イベント状態変化と管理者承認待ちのタイムアウト・リマインド：EventBridge Schedulerで「PENDING_APPROVAL状態のまま24時間経過したらリマインド」を追加する余地を残す

---

## 8. ResultLambda

### 8.1 トリガー

API Gatewayのみ。

### 8.2 ハンドラー

| メソッド/パス | 対応機能 |
|---|---|
| `POST /events/{eventId}/sessions` | F-801〜F-803 ゲームセッション・結果登録 |
| `GET /users/{userId}/results` | F-804 成績取得。**権限チェック：閲覧者と対象ユーザーが同一コミュニティに所属している場合のみ返却**（DynamoDB物理設計書v1.1のGSI1SK設計＝`COMMUNITY#{communityId}#{playedAt}`で担保） |

### 8.3 集計処理について

- 通算対局数・平均順位・1位率・ラス率・累計ポイントは、結果登録時にその場で加算更新する方式（`UpdateStatistics`的な別Lambdaは設けず、ResultLambda内の関数として実装）
- 将来データ量が増えて都度集計がボトルネックになった場合は、集計専用の非同期処理（EventBridge経由）への切り出しを検討

### 8.4 IAM最小権限

- DynamoDB: `PutItem`/`Query`（GameSession, GameResult。GSI1含む）

---

## 9. NotificationLambda **[v1.2修正]**

### 9.1 トリガー **[v1.2修正]**

| トリガー | 用途 |
|---|---|
| EventBridge | 各ドメインLambdaが発行するイベント（`EventConfirmed`, `EventCancelled`, `CancelApproved`, `CandidateConflictDetected`[v1.1追加], **`AvailabilityRequestCreated`[v1.2追加]**等）を受けて通知レコードを作成 |
| API Gateway | 通知一覧取得・既読更新、**プッシュ通知購読登録・解除[v1.2追加]** |

### 9.2 ハンドラー **[v1.2修正]**

| メソッド/パス | 対応機能 |
|---|---|
| （EventBridgeイベント受信） | F-701 通知レコード作成（アプリ内通知 + Webプッシュ送信、9.3b参照） |
| `GET /notifications` | F-702 通知一覧 |
| `PUT /notifications/{notificationId}/read` | F-702 既読更新 |
| `POST /users/me/push-subscriptions` | **F-703 プッシュ通知購読登録（API設計書v1.5 11.3）[v1.2新規]** |
| `DELETE /users/me/push-subscriptions` | **F-704 プッシュ通知購読解除（API設計書v1.5 11.4）[v1.2新規]** |

### 9.3 MVPでの通知チャネルについて **[v1.2修正：要確認・矛盾解消]**

> AWSシステム構成設計書11章では「MVP:メール通知（SES）」となっていたが、要件定義書16章・機能要件書12章では「MVP:アプリ内通知のみ」となっており、既存ドキュメント間で矛盾があった。本設計書では要件定義書・機能要件書を正とし、MVPはアプリ内通知のみ実装する方針としていた（メール送信・SES連携はPhase2）。
>
> **[v1.2修正]** 要件定義書v1.3 27章の通り、MVPにWebプッシュ通知（PWA経由）を追加する。メール（SES）ではなく、Amazon SNS等の配信基盤も使わないVAPID鍵によるWeb Push APIの直接利用のため、上記「メール送信・SES連携はPhase2」という結論とは矛盾しない。メール・LINE連携は引き続きPhase2とする。

### 9.3b Webプッシュ通知の送信処理 **[v1.2新規]**

通知レコード作成（F-701）のたびに、対象ユーザーのPushSubscription（DynamoDB物理設計書v1.4 3.17）を全件取得し、それぞれにWeb Push APIでメッセージを送信する。

```
EventBridgeイベント受信
  ↓
Notificationレコード作成（従来通り）
  ↓
PK=USER#{userId}, SK begins_with PUSHSUB# をQuery
  ↓
各PushSubscriptionについてWeb Push送信（VAPID鍵で署名、ペイロードを暗号化）
  ↓
送信失敗（410 Gone等、購読が失効している）の場合は該当PushSubscriptionを削除
```

> **[v1.2新規]** Web Pushプロトコル（VAPID認証・ペイロード暗号化）の実装には`pywebpush`ライブラリ（内部で`cryptography`に依存）を用いる想定。共通Layer（12.1参照）はゼロサードパーティ依存を方針としているため、この依存はNotificationLambda専用のLayerとして別途切り出す（デプロイパッケージのサイズ最適化のため）。
>
> VAPID鍵ペア（公開鍵・秘密鍵）はAWS Secrets Managerに保管し、NotificationLambdaの実行時に取得する（要件定義書24章のSecrets Manager方針に準拠）。鍵の生成・ローテーション方式は実装段階で決定する。
>
> 送信失敗時にPushSubscriptionを即時削除するかリトライするかの具体的な閾値は実装段階で決定する（410 Goneは即削除が一般的なWeb Pushのベストプラクティス）。

### 9.4 IAM最小権限 **[v1.2修正]**

- DynamoDB: `PutItem`/`Query`/`UpdateItem`/`DeleteItem`（Notification, **PushSubscription** [v1.2追加]）
- EventBridgeルールのターゲットとして呼び出されるための実行権限（`lambda:InvokeFunction`をEventBridge側に許可）
- **`secretsmanager:GetSecretValue`（VAPID鍵の取得用）[v1.2追加]**

---

## 10. Lambda起動フロー（全体像）

### 10.1 ユーザー登録

```
Cognito確認完了
  ↓
UserLambda（Post Confirmationトリガー）
  ↓
DynamoDB Userプロフィール作成
```

### 10.2 コミュニティ参加（承認制の場合）

```
CommunityLambda（招待参加）
  ↓
memberApprovalRequired = true
  ↓
JoinRequest作成（PENDING）
  ↓
（管理者が確認・承認操作）
  ↓
CommunityLambda（承認処理、TransactWriteItems）
  ↓
Membership作成
```

### 10.3 マッチング〜イベント確定（MVP、手動実行前提）

```
（管理者がAPIで手動実行）
  ↓
MatchingLambda（候補生成）
  ↓
（管理者が候補確認・イベント作成）
  ↓
EventLambda（イベント作成）
  ↓
（管理者が承認）
  ↓
EventLambda（承認処理、TransactWriteItems）
  ↓
EventBridge: EventConfirmed
  ↓
NotificationLambda（参加者へ確定通知）
```

### 10.4 個人キャンセル（MVP：申請・承認まで）

```
EventLambda（キャンセル申請）
  ↓
（管理者が確認・承認操作）
  ↓
EventLambda（承認処理、ConditionExpressionで二重承認防止）
  ↓
EventBridge: CancelApproved
  ↓
NotificationLambda（本人へ受理通知）

※ 欠員補充（補欠検索・繰り上げ）はPhase2のためMVPフローには含まない
```

### 10.5 イベント全体の中止（MVP）

```
EventLambda（中止処理）
  ↓
EventBridge: EventCancelled
  ↓
NotificationLambda（全参加者へ中止通知）
```

### 10.6 結果登録

```
ResultLambda（セッション・結果登録、集計更新を同一Lambda内で実施）
```

---

## 11. MVP実装対象Lambda一覧 **[7ドメイン+マッチング分離の範囲で確定]**

| Lambda | MVP実装 |
|---|---|
| UserLambda | ✅ |
| CommunityLambda | ✅（参加リクエスト承認・会場管理含む） |
| AvailabilityLambda | ✅（バッチ登録含む） |
| MatchingLambda | ✅（手動実行のみ。定期実行はPhase2） |
| EventLambda | ✅（個人キャンセル申請・承認、イベント中止含む。欠員補充は含まない） |
| ResultLambda | ✅ |
| NotificationLambda | ✅（アプリ内通知のみ。メール・Push・LINEはPhase2） |

Phase2以降で追加される可能性のある独立Lambda：
- `SubstituteLambda`（欠員補充）
- `TrustScoreLambda`（信頼スコア更新）
- `CompatibilityAnalysisLambda`（相性分析）
- `RecommendationLambda`（おすすめイベント生成、Bedrock活用を想定）

---

## 12. 共通実装方針

### 12.1 Lambda Layer

以下は共通処理としてLambda Layerに切り出し、全ドメインLambdaから参照する。

- DynamoDBクライアント初期化・共通クエリヘルパー
- 権限チェック（ログイン確認・コミュニティ所属確認・操作権限確認、機能要件書6章の共通制御に対応）
- OperationLog書き込み関数（`before`/`after`差分の記録、`ttl`属性の付与、ログイン等コミュニティ非紐付け操作は`LOG#GLOBAL#{userId}`として書き込み）
- 共通エラーレスポンス生成（`USER_NOT_FOUND`等の共通エラーコード）

### 12.2 IAM設計の考え方

各ドメインLambdaには、DynamoDB物理設計書v1.1のPKプレフィックス単位で`Condition`（`dynamodb:LeadingKeys`）を使った最小権限ポリシーを付与する。例えば`AvailabilityLambda`には`Availability`関連のPKプレフィックス（`COMMUNITY#*`のうちSKが`AVAIL#`で始まるアイテム、および対応するGSI1）以外への書き込み権限を与えない。

### 12.3 冪等性・トランザクション

DynamoDB物理設計書v1.1の5章（トランザクション・冪等性の設計方針）に準拠し、以下は`TransactWriteItems`または`ConditionExpression`を用いる。

- 参加リクエスト承認（CommunityLambda）
- OWNER変更（CommunityLambda）
- イベント承認（EventLambda）
- キャンセル承認の二重実行防止（EventLambda）

---

## 13. 各設計書との対応関係

| 本書のLambda | 対応する要件定義書v1.1 | 対応する機能要件書v1.1 | 対応するAPI設計書v1.1 |
|---|---|---|---|
| UserLambda | 8章 | F-001〜F-003 | 3章 |
| CommunityLambda | 9〜10章, 18章 | F-101〜F-107 | 4章, 8.5, 8.6 |
| AvailabilityLambda | 11章, **28章[v1.2]** | F-201〜F-204, **F-205/F-206[v1.2]** | 5章 |
| MatchingLambda | 12〜13章 | F-301〜F-304, F-401〜F-404 | 6章, 7章 |
| EventLambda | 14〜15章, 17章 | F-501〜F-605 | 8章, 9章 |
| ResultLambda | 19章（v1.0要件定義書相当） | F-801〜F-804 | 10章 |
| NotificationLambda | 16章, **27章[v1.2]** | F-701, F-702, **F-703/F-704[v1.2]** | 11章 |

---

## 14. 未決事項 **[v1.2修正]**

1. **欠員補充Lambdaの実装方式**（EventBridge連鎖 vs Step Functions併用）：実装段階で決定
2. **承認待ちタイムアウト・リマインド**：EventBridge Schedulerの追加要否をMVP運用後に判断
3. ~~AWSシステム構成設計書11章の通知チャネル記載修正~~：**[v1.2解消]** 9.3の方針をアプリ内通知+Webプッシュ通知に更新し、AWSシステム構成設計書側も合わせて更新済み
4. **EventStatusHistoryへの書き込み処理**：EventLambda内の直接書き込みで開始し、将来的な分析要件次第で専用Lambda化を検討
5. **公平性指標（fairnessCount）の計算タイミング**：候補一覧取得の都度計算（6.8）で開始し、コミュニティ規模が大きくなった場合は非同期の事前集計に切り替えるかを検討
6. **複数コミュニティ横断の優先度比較（Phase3）**：Membershipの`priorityWeight`/`desiredFrequency`をどのLambdaがどう使うかは、満足度の定義が固まってから設計する
7. **VAPID鍵の生成・ローテーション方式** [v1.2追加]：Secrets Manager保管までは決定済みだが、初回生成の手順（手動 or デプロイ時自動生成）とローテーション周期は実装段階で決定する
8. **AvailabilityRequestの未提出者確認のスケーリング** [v1.2追加]：DynamoDB物理設計書v1.4 8章の未決事項8と同一。コミュニティ規模拡大時に事前集計化を検討

---

## v1.0 → v1.1 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | MatchingLambdaに`EventConfirmed`購読ハンドラーを追加（6.7 ダブルブッキング事後検知） | 候補4：確定後の事後通知 |
| 2 | MatchingLambdaの候補生成フローにCandidateMember書き込みを追加（6.3） | 衝突検知・公平性指標の共通基盤 |
| 3 | 候補一覧取得（6.2）に公平性指標（fairnessCount）の付与を追加（6.8） | 「候補止まり」の可視化 |
| 4 | EventLambdaの承認処理にダブルブッキング事前チェックを追加（7.2b） | 候補3：確定時ハードチェック |
| 5 | EventBridge発行イベントに`CandidateConflictDetected`を追加、NotificationLambdaの購読対象に追加 | 衝突検知の通知経路 |
| 6 | MatchingLambda/EventLambdaのIAM権限にCandidateMember・GSI1・PutEvents権限を追加 | 上記機能の実装に伴う権限拡張 |

---

## v1.1 → v1.2 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | AvailabilityLambdaに空き予定提出リクエスト作成・一覧・未提出メンバー確認ハンドラーを追加（5.2）、`AvailabilityRequestCreated`発行権限を追加（5.3） | 要件定義書v1.3 28章：管理者からの空き予定提出リクエスト（F-205/F-206） |
| 2 | EventBridge発行イベント一覧（7.3）に`AvailabilityRequestCreated`を追加 | 上記の通知経路 |
| 3 | NotificationLambdaにプッシュ通知購読登録・解除ハンドラーを追加（9.2）、Webプッシュ送信処理を新規追加（9.3b）、IAM権限にPushSubscription・Secrets Manager権限を追加（9.4） | 要件定義書v1.3 27章：PWA化とWebプッシュ通知（F-703/F-704） |
| 4 | 9.3のMVP通知チャネル方針を「アプリ内通知のみ」から「アプリ内通知+Webプッシュ通知」に更新 | Push通知のMVP前倒し（メール/SNS採用ではないため既存の矛盾解消方針とは非矛盾） |
| 5 | 各設計書との対応関係表（13章）・未決事項（14章）を更新 | 整合性維持 |
