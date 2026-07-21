# MeetFlow Lambda設計書 v1.9

> 要件定義書v1.1・機能要件書v1.1・API設計書v1.1・DynamoDB物理設計書v1.1を踏まえて設計。v1.1→v1.2は要件定義書v1.3・機能要件書v1.3・API設計書v1.5・DynamoDB物理設計書v1.4を踏まえて更新。v1.2→v1.3は機能要件書v1.5・API設計書v1.7・DynamoDB物理設計書v1.6を踏まえて更新。v1.3→v1.4はAPI設計書v1.8（招待URL無効化・OperationLog閲覧APIの実装）を踏まえて更新。v1.7→v1.8はAPI設計書v1.19（Issue #42：登録済み対局セッションの削除API新設）を踏まえて更新。v1.8→v1.9は要件定義書v1.9・機能要件書v1.11・API設計書v1.25・DynamoDB物理設計書v1.19（Issue #40：コミュニティ内ランキング機能）を踏まえて更新。
> **設計方針決定：ドメイン単位（7個）+ マッチング処理の分離**

---

## 1. 設計方針

- Lambdaは**ドメイン単位**で分離する（エンドポイント単位の細分化はしない）
- 1つのドメインLambda内では、API Gatewayからのルーティング情報（HTTPメソッド＋パス）に応じて内部でハンドラー関数を振り分ける（ルーター的な構成）
- **重い処理（マッチング候補生成）は独立したLambdaに分離する**。理由：処理時間・メモリ使用量が他のCRUD処理と性質が異なり、タイムアウト設定やメモリ割当を個別最適化したいため
- Lambda間は直接呼び出さず、非同期処理はEventBridge経由で連携する
- ユーザー登録はAPI Gateway経由の公開エンドポイントを持たず、**Cognito Post Confirmationトリガー**として実装する
- 認証（JWT検証）は独自Lambdaを作らず、**API GatewayのCognito Authorizer**に任せる。各ドメインLambdaはAPI Gatewayが検証済みのクレーム（userId等）をevent経由で受け取るだけでよい

---

## 2. Lambda一覧（8ドメイン + 補助）**[v1.7修正]**

| Lambda名 | ドメイン | 対応API領域 |
|---|---|---|
| UserLambda | ユーザー・プロフィール | 3章 |
| CommunityLambda | コミュニティ・メンバー・招待・会場 | 4章, 8.5, 8.6 |
| AvailabilityLambda | 空き予定 | 5章 |
| **MatchingLambda**（分離） | 開催条件・マッチング候補生成 | 6章, 7章 |
| EventLambda | イベント・参加者・キャンセル | 8章（8.5/8.6除く）, 9章 |
| ResultLambda | 成績管理 | 10章 |
| NotificationLambda | 通知 | 11章 |
| **FeedbackLambda** [v1.7新規] | フィードバック・アップデート予告 | 12b章, 12c章 |

> 操作ログ（OperationLog）は専用Lambdaを持たず、各ドメインLambda内の共通関数（Lambda Layerとして共有）から書き込む。
>
> **[v1.3追加]** 操作ログ閲覧API/画面は現時点で未実装（`GET /communities/{communityId}/logs`等はハンドラー未接続）。Phase2以降で実装する際は、ログの`userId`（および`communityId`）から12.1の表示名解決関数（`meetflow_common.display_name`）で表示名を解決すること。ログ自体にはuserIdのみを記録し、表示名のスナップショットは持たない。
>
> **[v1.4解消]** 上記の閲覧API（`GET /communities/{communityId}/logs`, `GET /users/{userId}/logs`）をCommunityLambdaに実装した（4.2参照）。`GET /users/{userId}/logs`はURLパスこそ`/users/`始まりだが、権限判定（本人 or 対象ユーザーと同一コミュニティのOWNER/ADMIN）がMembership/roleに依存するため、それらを扱うCommunityLambda側に置いている。表示名は指針通り閲覧のたびに`meetflow_common.display_name`で解決する。

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
| `POST /invites/{token}/revoke` | **招待URL無効化（Invite.revoked更新）。既に無効化済みなら冪等に成功扱い [v1.4新規]** |
| `GET /communities/{communityId}/members` | F-104 メンバー一覧 |
| `PUT /communities/{communityId}/members/{userId}` | F-104 権限変更・一時停止・退出処理 |
| `PUT /communities/{communityId}/members/me/display-name` | **F-108 コミュニティごとの表示名設定・変更（重複時409 DISPLAY_NAME_ALREADY_TAKEN） [v1.3新規]** |
| `POST /communities/{communityId}/join-requests/{requestId}/approve` | F-104b 参加リクエスト承認（`TransactWriteItems`でJoinRequest更新＋Membership作成） |
| `POST /communities/{communityId}/join-requests/{requestId}/reject` | F-104c 参加リクエスト却下 |
| `POST /communities/{communityId}/owner-transfer` | F-106 管理者変更（`TransactWriteItems`で新OWNER付与＋元OWNERをMEMBERに更新） |
| `GET /communities/{communityId}/locations` | F-107 会場一覧（Place、GSI1経由） |
| `POST /communities/{communityId}/locations` | F-107 会場登録（Place、`ownerType=COMMUNITY`固定） |
| `GET /communities/{communityId}/logs` | **F-1302 コミュニティ操作ログ取得（OWNER/ADMIN限定、PK=LOG#{communityId}をQuery） [v1.4新規]** |
| `GET /users/{userId}/logs` | **F-1302 ユーザー操作ログ取得（本人 or 同一コミュニティのOWNER/ADMIN限定、GSI1経由） [v1.4新規]** |
| `PUT /communities/{communityId}/ranking-settings` | **F-806 コミュニティ内ランキング設定（種目・集計期間・指標・足切りのデフォルト値を一括更新。OWNER/ADMIN限定、4.2c テーマカラー設定と同一パターン） [v1.9新規]** |

### 4.3 IAM最小権限

- DynamoDB: `PutItem`/`GetItem`/`UpdateItem`/`Query`（Community, Membership, Invite, JoinRequest, Place の各PKプレフィックスに限定）
- `TransactWriteItems`（参加リクエスト承認、OWNER変更のみ）

> **[v1.3追加]** コミュニティごとの表示名設定（F-108）は既存Membership itemへの`UpdateItem`（属性追加のみ、PK/SK/GSI1は不変）に過ぎず、新規のPKプレフィックスやTransactWriteItemsを必要としないため、上記IAM権限の変更は不要。
>
> **[v1.4追加]** 招待URL無効化（Invite.revokedの`UpdateItem`）とOperationLog閲覧（LOG#プレフィックスおよびGSI1への`Query`）はいずれも既存の許可action（`UpdateItem`/`Query`）の範囲内であり、新規のIAM権限追加は不要。12.2の通り、本設計のIAM境界はPKプレフィックス単位ではなくaction単位（`dynamodb:LeadingKeys`条件はbegins_with非対応のため）であり、プレフィックス分離はLambdaコード側の責務である点は変わらない。
>
> **[v1.9追加]** ランキング設定（F-806）はCommunity METADATAアイテムへの`UpdateItem`（属性追加のみ、PK/SKは不変）に過ぎず、新規IAM権限は不要。

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
| **EventBridge（`EventAwaitingApproval`/`EventConfirmed`購読）** | **他コミュニティでイベントが仮確定（または全員自動承認で即時本確定）した際、自コミュニティのPENDING候補に衝突警告を立てる（衝突検知、6.7参照）[v1.1新規、v1.6で購読対象を`EventAwaitingApproval`に拡張]** |

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
候補メンバーごとに参加頻度上限の実効値・集計期間内カウントを取得（6.9参照）[v1.5新規]
  ↓
スコア計算（F-403: 信頼度は対象外＝Phase2。加点要素関数は将来の信頼度/NG設定追加を見据えて分離した関数として実装。参加頻度上限超過者がいれば減点しreasonsに明記 [v1.5追加]）
  ↓
MatchCandidate保存
  ↓
候補メンバー1人ごとにCandidateMemberレコードを書き込み [v1.1新規]（DynamoDB物理設計書v1.3 3.11b）
```

### 6.4 設定

- タイムアウト：デフォルト3秒→**30秒に拡張**（性能目標「候補生成10秒以内」に対し余裕を持たせる）
- メモリ：512MB〜（コミュニティ規模拡大時に見直し）
- 将来、信頼度・相性分析・NG設定（Phase2/3）が加わってもこのLambda内の関数分割で対応できるよう、スコア計算部分は独立関数として実装しておく

### 6.5 IAM最小権限 **[v1.1修正、v1.5修正]**

- DynamoDB: `Query`（Availability, EventTemplate）, `PutItem`/`GetItem`/`Query`（MatchCandidate、GSI2含む）, **`PutItem`/`UpdateItem`/`Query`（CandidateMember、GSI1含む）[v1.1追加]**
- **`GetItem`（User, Membership。参加頻度上限の実効値解決用）、`Query`（Participant、GSI1含む。参加頻度上限のジャンル横断カウント用）[v1.5追加]**
- **`events:PutEvents`（`CandidateConflictDetected`発行用）[v1.1追加]**
- EventBridgeルール（`EventConfirmed`）のターゲットとして呼び出されるための実行権限

### 6.6 実行契機についての補足

> **[前回決定の反映]** MVPでは「管理者による手動実行（API呼び出し）」のみ有効。ただし内部処理は「開催条件（テンプレート）ID単位の実行」として関数化しておき、将来のEventBridge Scheduler定期実行や空き予定登録時の自動トリガーからも同一関数を呼び出せる構成とする。API自体の追加は不要（呼び出し元が増えるだけ）。

### 6.7 ダブルブッキング事後検知（衝突検知）**[v1.1新規、v1.6修正]**

EventLambdaが発行する`EventAwaitingApproval`/`EventConfirmed`イベントをMatchingLambdaが購読し、以下を実行する。**[v1.6修正]** 実際の「予約」（Participant行の作成・重複Availabilityの削除）はイベント仮確定（`AWAITING_MEMBER_APPROVAL`への遷移）時点で発生するようになったため、衝突検知もその時点で走る必要がある。全員自動承認ONで`AWAITING_MEMBER_APPROVAL`を経由せず直接`CONFIRMED`になるケースを取りこぼさないよう、`EventConfirmed`も引き続き購読する（ハンドラー自体は`participantIds`/`startTime`/`endTime`のみを読むため、detail-typeによる処理分岐はない）。

```
EventAwaitingApproval または EventConfirmed受信（対象イベントの参加者userId一覧・時間帯を含む）
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

### 6.9 参加頻度上限の算出 **[v1.5新規]**

候補生成処理（6.3）の中で、候補メンバーごとに以下を算出しスコア計算（F-403）へ渡す。

```
User/Membershipの参加頻度上限設定をGetItemで取得（Membership優先、未設定ならUser側にフォールバック。共通Layer meetflow_common.frequency_limit）
  ↓
上限が設定されていなければスキップ（減点なし）
  ↓
設定された期間（週/月）から、候補日時が属する集計期間の開始・終了を算出
  ↓
Participant GSI1（USER#{userId}, GSI1SK between PARTICIPANT#{periodStart}~{periodEnd}）をQuery
  ↓
communityGenreが候補生成対象コミュニティのgenreと一致する行の件数をカウント
  ↓
件数が上限以上であれば、該当メンバーの (limit, count) をスコア計算関数へ渡す
```

> **[v1.5追加]** 6.8の公平性指標（fairnessCount）とは異なり、こちらは**実際にF-403のスコア計算へ組み込む**。ただし候補メンバー構成そのもの（誰を候補に含めるか）には影響させず、候補は生成した上でスコアを下げ、成立理由（reasons）に明記するに留める。候補から機械的に除外しないのは、19章のヒューマン・イン・ザ・ループ原則（システムは提案するのみで確定は常に人間が行う）に沿うため（要件定義書v1.6 30.3参照）。DynamoDB物理設計書v1.9 3.11の`communityGenre`非正規化により、EventTemplateへのN+1 GetItemを避けている。

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
| `POST /events/{eventId}/confirm` | F-502 **イベント仮確定**（管理者のみ）。**[v1.6修正：「イベント承認」から名称変更]** `TransactWriteItems`実行前に、候補メンバー全員分についてダブルブッキング事前チェック（7.2b参照）を行う。問題なければ候補メンバーごとに実効自動承認設定（`meetflow_common.get_auto_approve`）を解決し、Event状態を`AWAITING_MEMBER_APPROVAL`（1人以上が自動承認OFF）または`CONFIRMED`（全員自動承認ON）に更新＋Participant一括作成（自動承認ONのメンバーのみ`CONFIRMED`、それ以外は`AWAITING_APPROVAL`）→ 前者はEventBridgeへ`EventAwaitingApproval`、後者は`EventConfirmed`を発行。**[v1.5追加]** Participant作成時、Community METADATAの`genre`を`GetItem`で取得し`communityGenre`属性としてコピーする（参加頻度上限のジャンル横断カウント用、DynamoDB物理設計書v1.9 3.11参照） |
| `POST /events/{eventId}/participants/me/approve` **[v1.6新規]** | F-502b **参加者本人による個別承認**。`ConditionExpression: status=AWAITING_APPROVAL`でParticipant.statusをCONFIRMEDに更新（二重応答防止、`409 PARTICIPANT_ALREADY_RESPONDED`）。全Participantが`CONFIRMED`になった時点でEvent.statusを`AWAITING_MEMBER_APPROVAL`→`CONFIRMED`へ本確定し、EventBridgeへ`EventConfirmed`を発行（詳細は7.2c参照） |
| `POST /events/{eventId}/participants/me/reject` **[v1.6新規]** | F-502c **参加者本人による明示的な辞退**。`ConditionExpression: status=AWAITING_APPROVAL`でParticipant.statusをREJECTEDに更新（同上のエラーコードで二重応答防止）。Event.statusは変更せず、EventBridgeへ`EventParticipantRejected`を発行して管理者に通知するのみ（要件定義書v1.7 §17/§19のヒューマン・イン・ザ・ループ原則により、システムは自動でイベントを中止しない。中止判断は既存の`POST /events/{eventId}/cancel`に委ねる） |
| `POST /events/{eventId}/cancel` | F-605 **イベント全体の中止**（管理者のみ）→ EventBridgeへ`EventCancelled`発行（全参加者への通知トリガー）。**[v1.6]** `AWAITING_MEMBER_APPROVAL`状態からも中止可能（既存の許可分岐が自然にカバーするためコード変更不要） |
| `GET /events/{eventId}/participants` | 9.1 参加者一覧 |
| `POST /events/{eventId}/cancel-request` | F-601 **個人キャンセル申請**（MVP対象。自動では確定しない） |
| `POST /events/{eventId}/cancel-requests/{userId}/approve` | F-602 **キャンセル申請承認**（管理者のみ。`ConditionExpression: status=PENDING`で二重承認防止）→ EventBridgeへ`CancelApproved`発行 |

> **[v1.1整合]** `EventLambda`は8.4（v1.0 API設計書での旧称）を「イベント中止」、9.2/9.3を「個人キャンセル申請・承認」として明確に役割分離している。

### 7.2b イベント仮確定時のダブルブッキング事前チェック **[v1.1新規、v1.6修正：判定対象statusを拡張]**

```
仮確定リクエスト受信
  ↓
候補メンバー全員について、Participant GSI1（USER#{userId}, GSI1SK between PARTICIPANT#{eventStartTime}~{eventEndTime}）をQuery
  ↓
status=CONFIRMED または AWAITING_APPROVAL の既存Participantが1件でも見つかった場合
  ↓
TransactWriteItemsを実行せず、409 PARTICIPANT_SCHEDULE_CONFLICT エラーを返却して中断
  ↓
（問題なければ）候補メンバーごとに実効自動承認設定を解決し、TransactWriteItemsでEvent状態更新＋Participant一括作成 → EventAwaitingApproval または EventConfirmed発行
```

> 前回会話の「候補3」に対応。実害（二重予定の確定）を防ぐ最後の砦として、仮確定処理の中で同期的に実行する。DynamoDB物理設計書v1.3 5章のトランザクション設計方針に準拠。**[v1.6修正]** 仮確定＝承認待ちの時点で参加者の時間枠は事実上「予約済み」になるため、判定対象を`CONFIRMED`だけでなく`AWAITING_APPROVAL`にも拡張した（これをしないと、承認待ち中の参加者を別候補が同じ時間帯で仮確定できてしまう抜け道になる）。

### 7.2c イベント本確定（全員承認完了） **[v1.6新規]**

```
参加者本人が POST .../participants/me/approve
  ↓
ConditionExpression: status=AWAITING_APPROVAL でParticipant.status→CONFIRMED
  ↓（失敗時）409 PARTICIPANT_ALREADY_RESPONDED で中断
  ↓（成功時）
全Participant行を再クエリし、全員がCONFIRMEDか判定（PK=EVENT#{id}, SK begins_with PARTICIPANT#。DynamoDB物理設計書v1.10 3.11アクセスパターンNo.32）
  ↓ NO（他に承認待ち/拒否済みが残っている）
そのまま200を返す（本確定はしない）
  ↓ YES
ConditionExpression: status=AWAITING_MEMBER_APPROVAL でEvent.status→CONFIRMED
  ↓（失敗時）
Eventを再取得し実際のstatusを確認。既にCONFIRMED（他の承認呼び出しとの無害な競合）ならEventConfirmedを発行せず200を返す。
CANCELLED等（承認待ち中に管理者がイベント全体を中止していた）の場合もEventConfirmedは発行しない。
自分自身の承認自体は成功しているため、いずれの場合も呼び出し元にはエラーを返さない。
  ↓（成功時）
write_status_history、write_operation_log、EventBridgeへEventConfirmed発行
```

> 拒否者（Participant.status=REJECTED）が1件でも残っている限り、他メンバー全員が承認しても本確定はされない。欠員補充によるメンバー差し替えはMVP対象外（要件定義書v1.7 §22-23）のため、拒否が出た場合の最終判断は管理者の`cancel_event`呼び出しに委ねる。

### 7.3 EventBridge発行イベント一覧

| イベント名 | 発行タイミング | 主なターゲット |
|---|---|---|
| `EventConfirmed` | 本確定時（全員自動承認ONで仮確定が直接本確定になった場合を含む） **[v1.6修正：発行タイミングが「承認処理完了時」から「本確定時」に変更]** | NotificationLambda（参加者へ確定通知）、**MatchingLambda（衝突検知、6.7参照）[v1.1追加、v1.6でEventAwaitingApprovedと併用]** |
| **`EventAwaitingApproval`** [v1.6新規] | 仮確定時、1人以上が自動承認OFFで`AWAITING_MEMBER_APPROVAL`へ遷移した時 | NotificationLambda（承認待ちの参加者へ承認依頼通知）、MatchingLambda（衝突検知。実際の「予約」はこの時点で発生するため） |
| **`EventParticipantRejected`** [v1.6新規] | 参加者が明示的に辞退した時 | NotificationLambda（該当コミュニティの管理者へ通知） |
| `EventCancelled` | イベント中止時 | NotificationLambda（全参加者へ中止通知） |
| `CancelApproved` | キャンセル承認完了時 | NotificationLambda（本人へ受理通知）※欠員補充（F-603）はPhase2のため、MVPでは通知のみで完結し後続処理は発火しない |
| `EventStatusChanged` | 状態遷移のたび | EventStatusHistoryへの追記（EventLambda内の共通関数で直接書き込みでも可。将来ここだけ切り出す可能性あり） |
| **`CandidateConflictDetected`** [v1.1新規] | MatchingLambdaが衝突を検知した時 | NotificationLambda（該当コミュニティの管理者へ通知） |
| **`AvailabilityRequestCreated`** [v1.2新規] | AvailabilityLambdaが空き予定提出リクエストを作成した時（5.2参照） | NotificationLambda（対象メンバーへ通知） |

### 7.4 IAM最小権限 **[v1.1修正、v1.5修正]**

- DynamoDB: `PutItem`/`GetItem`/`UpdateItem`/`Query`（Event, Participant, CancelRequest, EventStatusHistory。**ParticipantはGSI1も含む[v1.1追加]（ダブルブッキングチェック用）**）
- **`GetItem`（Community。イベント仮確定時に`genre`を取得しParticipant.communityGenreへコピーするため）[v1.5追加]**
- **`GetItem`（Membership。候補メンバーごとの実効自動承認設定を解決するため）[v1.6追加。既存のEvent向けgrantと同一テーブルのため新規IAM変更は不要]**
- `TransactWriteItems`（仮確定処理）
- `events:PutEvents`（EventBridgeへの発行権限。`EventAwaitingApproval`/`EventParticipantRejected`用途を追加 [v1.6]）

### 7.5 Phase2への拡張ポイント（現時点では未実装）

- 欠員補充（F-603）：`CancelApproved`イベントを受けて起動する別Lambda（`SubstituteLambda`等）を追加する想定。EventBridgeイベント連鎖で組むかStep Functionsを使うかは実装段階で決定（前回の保留事項どおり）
- イベント状態変化と管理者承認待ちのタイムアウト・リマインド：EventBridge Schedulerで「PENDING_APPROVAL状態のまま24時間経過したらリマインド」を追加する余地を残す

---

## 8. ResultLambda

### 8.1 トリガー

API Gatewayのみ。

### 8.2 ハンドラー **[v1.9修正]**

| メソッド/パス | 対応機能 |
|---|---|
| `POST /events/{eventId}/sessions` | F-801〜F-803 ゲームセッション・結果登録。コミュニティのアクティブなメンバーであれば誰でも実行可能 |
| `PUT /events/{eventId}/sessions/{sessionNo}` | 登録済み対局セッションの編集。OWNER/ADMIN限定。参加者構成（userIdの集合）は変更不可 |
| `DELETE /events/{eventId}/sessions/{sessionNo}` **[v1.8新規]** | Issue #42：登録済み対局セッションの削除。OWNER/ADMIN限定（PUTと同じ権限方針）。GameSession本体・全参加者分のGameResult・GameResultChipを`TransactWriteItems`でまとめて削除する |
| `GET /events/{eventId}/sessions` | イベント内の登録済み対局セッション一覧。コミュニティメンバーであれば誰でも閲覧可能 |
| `GET /communities/{communityId}/game-sessions/last-settings` | 呼び出しユーザー自身の直近の対局設定（配給原点・返し点・ウマ・計算モード）取得。次回入力時のデフォルト値として利用 |
| `GET /users/{userId}/results` | F-804 成績取得。**権限チェック：閲覧者と対象ユーザーが同一コミュニティに所属している場合のみ返却**（DynamoDB物理設計書v1.1のGSI1SK設計＝`COMMUNITY#{communityId}#{playedAt}`で担保） |
| `GET /communities/{communityId}/rankings` **[v1.9新規]** | F-805 コミュニティ内ランキング取得。閲覧権限はコミュニティメンバーであれば誰でも可（管理者限定にしない） |

### 8.3 集計処理について **[v1.9修正]**

- 通算対局数・平均順位・1位率・ラス率・累計ポイントは、保存された累計値を持たず、`GET /users/{userId}/results`の読み取り時にGameResult（GSI1）から都度集計する方式で実装済み（旧版が記載していた「登録時にその場で加算更新」する専用の集計エンティティは、DynamoDB物理設計書に定義がなく採用していない）
- 将来データ量が増えて都度集計がボトルネックになった場合は、集計専用の非同期処理（EventBridge経由）への切り出しを検討
- **[v1.9追加]** コミュニティ内ランキング（`GET /communities/{communityId}/rankings`）も同じ「読み取り時集計」方式を踏襲するが、集計の起点が異なる。個人成績取得（`GET /users/{userId}/results`）はユーザー1人分をGSI1でQueryするのに対し、ランキングはコミュニティ×種目×期間の全メンバー分を**GSI2への1回のQuery**（`GSI2PK=COMMUNITY#{communityId}#{gameType}`, `GSI2SK between {startDate}~{endDate}`。DynamoDB物理設計書v1.19 §3.13参照）で一括取得し、Lambda側で`userId`ごとにグルーピングして集計する。メンバー一覧を起点にしないため、退会済みメンバーの対局記録も自動的に含まれる。イベントの`COMPLETED`判定（`_completed_event_ids`相当）も、Query結果に含まれるイベントID集合に対して1回だけキャッシュを構築すればよく、個人成績取得のロジックをメンバー数分ループする素朴な実装よりも無駄が少ない。

### 8.4 IAM最小権限 **[v1.9修正]**

- DynamoDB: `GetItem`/`PutItem`/`Query`（GameSession, GameResult, GameResultChip。GSI1含む）に加え、`DeleteItem`/`TransactWriteItems`（Issue #42の削除機能で、GameSession本体+GameResult+GameResultChipをまとめて削除するため。`TransactWriteItems`内のDelete操作には`dynamodb:DeleteItem`も別途必要）
- **[v1.9追加]** GSI2への`Query`権限を新規追加。ResultLambdaはv1.8時点ではGSI1のみを使用していたため、IAMポリシーの許可リソース（ARN）にGSI2のインデックスARNを追加する必要がある（`infra/meetflow_infra/meetflow_compute_stack.py`）。

---

## 9. NotificationLambda **[v1.2修正]**

### 9.1 トリガー **[v1.2修正]**

| トリガー | 用途 |
|---|---|
| EventBridge | 各ドメインLambdaが発行するイベント（`EventConfirmed`, `EventCancelled`, `CancelApproved`, `CandidateConflictDetected`[v1.1追加], `AvailabilityRequestCreated`[v1.2追加], **`EventAwaitingApproval`/`EventParticipantRejected`[v1.6追加]**等）を受けて通知レコードを作成 |
| API Gateway | 通知一覧取得・既読更新、**プッシュ通知購読登録・解除[v1.2追加]** |

### 9.2 ハンドラー **[v1.2修正]**

| メソッド/パス | 対応機能 |
|---|---|
| （EventBridgeイベント受信） | F-701 通知レコード作成（アプリ内通知 + Webプッシュ送信、9.3b参照）。**[v1.6追加]** `EventAwaitingApproval`は`detail.awaitingUserIds`（自動承認OFFで承認待ちのメンバーのみ、`participantIds`全員ではない）に承認依頼通知、`EventParticipantRejected`は該当コミュニティの管理者（OWNER/ADMIN）に辞退通知を送る。全員承認完了による本確定は、発行タイミングが仮確定時から遅くなるだけで意味は同じであるため、既存の`EventConfirmed`/確定通知メッセージをそのまま再利用する（新規メッセージは追加しない） |
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
>
> **[v1.3追加]** 現状の通知文言（`_MESSAGES`相当の定型文）は個人名を含まない定型文のみで、EventBridge detailにも行為者（actor）のuserIdは含まれていない。将来、個人名入りの通知文面（例：「〇〇さんがキャンセルしました」）を実装する場合は、EventBridge detailにactorのuserId・communityIdを含めるようイベント発行元（EventLambda等）を拡張したうえで、12.1の表示名解決関数（`meetflow_common.display_name`）を用いて通知対象ユーザーが所属するコミュニティの文脈で名前解決すること。今回（F-108）はこの通知文面自体の拡張は行わない。

### 9.4 IAM最小権限 **[v1.2修正]**

- DynamoDB: `PutItem`/`Query`/`UpdateItem`/`DeleteItem`（Notification, **PushSubscription** [v1.2追加]）
- EventBridgeルールのターゲットとして呼び出されるための実行権限（`lambda:InvokeFunction`をEventBridge側に許可）
- **`secretsmanager:GetSecretValue`（VAPID鍵の取得用）[v1.2追加]**

---

## 9b. FeedbackLambda **[v1.7新規]**

フィードバック（簡易評価・詳細投稿）とアップデート予告を担当する。8番目のドメインLambdaとして新設する。

### 9b.1 トリガー

API Gatewayのみ。

### 9b.2 ハンドラー

| メソッド/パス | 対応機能 |
|---|---|
| `POST /feedback` | F-1401/F-1402 フィードバック投稿（`kind`でQUICK/DETAILEDを分岐） |
| `POST /feedback/attachments/presign` | F-1402 スクリーンショット添付用のS3署名付きアップロードURL発行 |
| `GET /feedback` | F-1403 フィードバック一覧（**運営者限定**、9b.4参照） |
| `GET /feedback/{feedbackId}` | F-1403 フィードバック詳細（**運営者限定**） |
| `PATCH /feedback/{feedbackId}` | F-1403/F-1404 ステータス更新・優先度設定・返信（**運営者限定**。返信時はNotificationLambda向けにEventBridgeイベントを発行） |
| `GET /feedback/stats` | F-1405 集計ダッシュボード用データ（**運営者限定**） |
| `GET /announcements` | F-1406 アップデート予告一覧（一般ユーザーは公開中のみ、運営者は下書き含め取得可） |
| `POST /announcements` | F-1406 アップデート予告作成（**運営者限定**、DRAFTで作成） |
| `PUT /announcements/{announcementId}` | F-1406 アップデート予告更新・公開状態変更（**運営者限定**） |

### 9b.3 添付ファイル（S3）

スクリーンショットは、API Gateway/Lambda経由でバイナリを中継せず、フロントエンドがS3へ直接PUTする方式とする（他Lambdaの処理時間・ペイロードサイズへの影響を避けるため）。

```
POST /feedback/attachments/presign 受信
  ↓
S3オブジェクトキーを発行（feedback/{userId}/{uuid}.{ext}）
  ↓
署名付きPUT URL（有効期限5分）を生成して返却
  ↓
フロントエンドがuploadUrlへ直接PUT
  ↓
フロントエンドが POST /feedback のリクエストボディにattachmentKeyを含めて送信
```

> 専用のS3バケット（非公開、CloudFront経由の配信もしない）を新設する。運営者がフィードバック管理画面で閲覧する際は、FeedbackLambdaが都度署名付きGET URLを発行する想定（一般公開バケットにはしない）。

### 9b.4 運営者ロール（Operators）の認可

コミュニティ単位のMembership.role（OWNER/ADMIN/MEMBER）とは別軸の、システム全体の運営者ロールを新設する。既存の「認証はAPI GatewayのCognito Authorizerで完結し、各Lambdaはクレームのみを見る」という設計方針（1章）を踏襲し、新規の認可Lambda等は作らない。

- Cognito User Poolに`Operators`グループを新設する（インフラはCDKで定義、グループへの追加自体はMVPでは手動運用とし、管理画面上での自己申請・付与フローは設けない）
- FeedbackLambdaは`event.requestContext.authorizer.claims["cognito:groups"]`に`Operators`が含まれるかどうかで運営者限定エンドポイントの認可判定を行う
- コミュニティのOWNER/ADMINであることは運営者ロールの必要条件でも十分条件でもない（完全に別軸）

### 9b.5 IAM最小権限

- DynamoDB: `PutItem`/`GetItem`/`UpdateItem`/`Query`（Feedback, Announcement。GSI1/GSI2含む）
- **`s3:PutObject`（署名付きURL発行用）/`s3:GetObject`（フィードバック添付バケットの`feedback/*`プレフィックスに限定）**。MeetFlowの他ドメインLambdaは現時点でS3への直接アクセス権限を持たないため、本Lambdaが最初の例となる
- `events:PutEvents`（フィードバック返信通知用。NotificationLambdaへの`FeedbackReplied`発行）

### 9b.6 EventBridge発行イベント

| イベント名 | 発行タイミング | 主なターゲット |
|---|---|---|
| `FeedbackReplied` | 運営者がフィードバックに返信した時 | NotificationLambda（投稿者へ返信通知） |

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

## 11. MVP実装対象Lambda一覧 **[7ドメイン+マッチング分離の範囲で確定、v1.7でFeedbackLambda追加]**

| Lambda | MVP実装 |
|---|---|
| UserLambda | ✅ |
| CommunityLambda | ✅（参加リクエスト承認・会場管理含む） |
| AvailabilityLambda | ✅（バッチ登録含む） |
| MatchingLambda | ✅（手動実行のみ。定期実行はPhase2） |
| EventLambda | ✅（個人キャンセル申請・承認、イベント中止含む。欠員補充は含まない） |
| ResultLambda | ✅ |
| NotificationLambda | ✅（アプリ内通知のみ。メール・Push・LINEはPhase2） |
| **FeedbackLambda** [v1.7新規] | ✅（簡易フィードバック・詳細投稿・運営者レビュー・アップデート予告） |

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
- **[v1.3追加]** コミュニティ内の実効表示名解決（Membership.displayName優先、未設定時はUser.nicknameにフォールバック。F-108）。CommunityLambda（メンバー一覧）・MatchingLambda（候補メンバー表示）・EventLambda（参加者一覧）が共通で参照するため、各Lambdaで重複実装せずここに集約する。
- **[v1.5追加]** 参加頻度上限の実効値解決・集計期間算出・カウント集計（`meetflow_common.frequency_limit`。displayName解決と同じ「Membership優先、未設定時はUser側にフォールバック」構造）。CommunityLambda（F-003/F-109の設定API側バリデーション）・MatchingLambda（6.9のスコアリング反映）が共通で参照する。
- **[v1.6追加]** 自動承認の実効値解決（`meetflow_common.auto_approve`。displayName/frequencyLimitと同じ「Membership優先、未設定時はUser側にフォールバック」構造）。EventLambda（仮確定時の目標状態決定）が参照する。イベント確定フローの新規status定数（`AWAITING_MEMBER_APPROVAL`/`AWAITING_APPROVAL`/`REJECTED`、およびダブルブッキング判定対象の`RESERVED_PARTICIPANT_STATUSES`）は`meetflow_common.event_status`に集約する（既存の14ファイルに分散したステータス文字列の一括定数化は本Issueのスコープ外とし、新規導入分のみを対象とする）。

### 12.2 IAM設計の考え方

各ドメインLambdaには、DynamoDB物理設計書v1.1のPKプレフィックス単位で`Condition`（`dynamodb:LeadingKeys`）を使った最小権限ポリシーを付与する。例えば`AvailabilityLambda`には`Availability`関連のPKプレフィックス（`COMMUNITY#*`のうちSKが`AVAIL#`で始まるアイテム、および対応するGSI1）以外への書き込み権限を与えない。

### 12.3 冪等性・トランザクション

DynamoDB物理設計書v1.1の5章（トランザクション・冪等性の設計方針）に準拠し、以下は`TransactWriteItems`または`ConditionExpression`を用いる。

- 参加リクエスト承認（CommunityLambda）
- OWNER変更（CommunityLambda）
- イベント承認（EventLambda）
- キャンセル承認の二重実行防止（EventLambda）

### 12.4 運営者ロール（Operators）の認可方式 **[v1.7新規]**

FeedbackLambda（9b章）の管理系エンドポイントのみが必要とする、コミュニティ単位のMembership.roleとは別軸の「システム全体の運営者」を表す認可方式。9b.4の詳細を参照。

- 新規の認可Lambda・DynamoDBエンティティは作らず、Cognito User Poolの`Operators`グループ + JWTの`cognito:groups`クレームのみで完結させる（1章の「認証はAPI GatewayのCognito Authorizerで完結」という既存方針の範囲内）
- 他の7ドメインLambdaの認可（コミュニティ所属・role確認）とは判定軸・判定対象が異なるため、共通Layer（12.1）の権限チェック関数とは別に、FeedbackLambda内に閉じた小さな判定関数として実装する（無理に共通化しない）

---

## 13. 各設計書との対応関係

| 本書のLambda | 対応する要件定義書v1.1 | 対応する機能要件書v1.1 | 対応するAPI設計書v1.1 |
|---|---|---|---|
| UserLambda | 8章 | F-001〜F-003 | 3章 |
| CommunityLambda | 9〜10章, 18章 | F-101〜F-107, **F-108[v1.3]** | 4章, 8.5, 8.6 |
| AvailabilityLambda | 11章, **28章[v1.2]** | F-201〜F-204, **F-205/F-206[v1.2]** | 5章 |
| MatchingLambda | 12〜13章 | F-301〜F-304, F-401〜F-404 | 6章, 7章 |
| EventLambda | 14〜15章, 17章 | F-501〜F-605 | 8章, 9章 |
| ResultLambda | 19章（v1.0要件定義書相当）、32章 [v1.9] | F-801〜F-804, F-805 [v1.9] | 10章 |
| NotificationLambda | 16章, **27章[v1.2]** | F-701, F-702, **F-703/F-704[v1.2]** | 11章 |
| **FeedbackLambda** [v1.7新規] | **31章** | **F-1401〜F-1406** | **12b章, 12c章** |

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

---

## v1.2 → v1.3 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 2章に、共通Layerが提供する表示名解決関数（12.1）の存在を将来の操作ログ表示実装時の指針として注記 | 機能要件書v1.5 F-108：コミュニティごとの表示名 |
| 2 | CommunityLambdaのハンドラー表（4.2）に`PUT /communities/{communityId}/members/me/display-name`を追加、IAM権限（4.3）は変更不要である旨を明記 | 上記と同一の決定事項。既存Membership itemへの属性追加（UpdateItem）のみで新規PKプレフィックス・TransactWriteItemsを要しないため |
| 3 | 12.1 Lambda Layerの共通処理一覧に、コミュニティ内の実効表示名解決関数（Membership.displayName優先、フォールバックでUser.nickname）を追加。CommunityLambda・MatchingLambda・EventLambdaが共通で参照する | 上記と同一の決定事項。各Lambdaでの重複実装を避けるため |
| 4 | 9.3bに、通知文面への個人名埋め込みは今回のスコープ外であり、将来実装する際はEventBridge detailの拡張＋表示名解決関数の利用が必要である旨を注記 | F-108の適用範囲整理（通知文面自体の変更は別タスク） |

---

## v1.3 → v1.4 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | CommunityLambdaのハンドラー表（4.2）に`POST /invites/{token}/revoke`を追加 | API設計書v1.8 §4.3b：招待URL無効化。画面設計書v1.4 S-06が定義済みの「URL無効化ボタン」に対応するAPIが無かった食い違いの解消 |
| 2 | CommunityLambdaのハンドラー表（4.2）に`GET /communities/{communityId}/logs`・`GET /users/{userId}/logs`を追加、2章の「現時点で未実装」注記を解消 | OperationLog閲覧API（API設計書v1.7時点で既に定義済みだった仕様の実装） |
| 3 | 4.3 IAM最小権限に、上記2機能が既存の許可action範囲内で完結し新規権限追加が不要である旨を追記 | 上記2件と同一の決定事項 |

---

## v1.4 → v1.5 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | MatchingLambdaの候補生成フロー（6.3）にスコア計算前の参加頻度上限取得ステップを追加、新規6.9「参加頻度上限の算出」を追加 | 要件定義書v1.6 30章：体力・満足度等の理由による個人ごとの参加頻度上限。6.8の公平性指標とは異なり実際にF-403のスコア計算へ反映するが、候補メンバー構成自体は変えず候補から機械的除外はしない（ヒューマン・イン・ザ・ループ原則） |
| 2 | MatchingLambdaのIAM権限（6.5）にUser/MembershipのGetItem、ParticipantのQuery（GSI1）を追加 | 上記6.9の実装に伴う権限拡張 |
| 3 | EventLambdaのイベント承認ハンドラー（7.2）に、Community.genreをParticipant.communityGenreへ非正規化コピーする処理を追記、IAM権限（7.4）にCommunityのGetItemを追加 | DynamoDB物理設計書v1.9 3.11：参加頻度上限のジャンル横断カウントをGSI1レンジクエリ1発で完結させるための非正規化 |
| 4 | 12.1 Lambda Layerの共通処理一覧に、参加頻度上限の実効値解決・集計関数（`meetflow_common.frequency_limit`）を追加 | CommunityLambda・MatchingLambdaでの重複実装を避けるため |

---

## v1.5 → v1.6 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 7.2の`POST /events/{eventId}/confirm`を「イベント承認」から「イベント仮確定」に改称し、候補メンバーの実効自動承認設定に応じてEvent状態を`AWAITING_MEMBER_APPROVAL`または`CONFIRMED`に振り分ける処理に修正。新規`POST /events/{eventId}/participants/me/approve`（F-502b）・`POST /events/{eventId}/participants/me/reject`（F-502c）を追加 | Issue #10：イベント確定フローに「マッチング→仮確定→全員通知→全員承認→本確定」の多段階承認を追加 |
| 2 | 7.2bのダブルブッキング事前チェックの判定対象statusを`CONFIRMED`のみから`CONFIRMED`/`AWAITING_APPROVAL`に拡張。新規7.2c「イベント本確定（全員承認完了）」を追加 | 承認待ち＝仮確定の時点で参加者の時間枠は事実上予約済みになるため。全員承認完了時のfinalizeロジック（ConditionExpressionによる二重実行防止、承認待ち中のイベント中止との競合時の扱い）を明記 |
| 3 | 7.3のEventBridge発行イベント一覧に`EventAwaitingApproval`・`EventParticipantRejected`を追加。`EventConfirmed`の発行タイミングを「承認処理完了時」から「本確定時」に修正 | 上記の多段階承認フローに伴う発行タイミングの変更 |
| 4 | 7.4のIAM最小権限に、実効自動承認設定解決用のMembership GetItemを追記（既存grant範囲内のため権限追加は不要である旨を明記） | 上記の実装に伴う参照先エンティティの追加 |
| 5 | 6.1のMatchingLambdaトリガー・6.7のダブルブッキング事後検知の購読対象を`EventConfirmed`のみから`EventAwaitingApproval`/`EventConfirmed`の両方に拡張 | 実際の「予約」（Participant作成・Availability削除）が仮確定時点で発生するようになったため、事後衝突検知もその時点で走る必要がある。全員自動承認ONで仮確定を経由しないケースは`EventConfirmed`側で捕捉する |
| 6 | 9.1のNotificationLambdaトリガー・9.2のハンドラーに、`EventAwaitingApproval`（承認待ちメンバーへの承認依頼通知）・`EventParticipantRejected`（管理者への辞退通知）の処理を追加 | 上記の多段階承認フローに伴う新規通知種別。本確定通知は既存の`EventConfirmed`通知を再利用し新設しない |
| 7 | 12.1 Lambda Layerの共通処理一覧に、自動承認の実効値解決関数（`meetflow_common.auto_approve`）とイベント確定フロー新規status定数（`meetflow_common.event_status`）を追加 | EventLambdaでの参照、および新規導入したstatus文字列のtypo防止のための一元管理（既存の分散ハードコード文字列の一括定数化は本Issueのスコープ外） |

---

## v1.6 → v1.7 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 2章のLambda一覧を7ドメインから8ドメインに更新し、FeedbackLambdaを追加 | Issue #34：フィードバック機能の設計書追加 |
| 2 | 新規9b章「FeedbackLambda」を追加。ハンドラー一覧・S3署名付きURLによる添付フロー・運営者ロールの認可方式・IAM最小権限・EventBridge発行イベントを定義 | 上記と同一の決定事項 |
| 3 | 12.4に運営者ロール（Operators）の認可方式を新規追加（Cognitoグループ+JWTクレームのみで完結、新規認可Lambda不要） | 上記と同一の決定事項。既存の「認証はCognito Authorizerで完結」方針の範囲内であることを明記 |
| 4 | 11章MVP実装対象Lambda一覧・13章対応関係表にFeedbackLambdaを追加 | 整合性維持 |

---

## v1.7 → v1.8 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 8.2ハンドラー表に`DELETE /events/{eventId}/sessions/{sessionNo}`（登録済み対局セッションの削除、OWNER/ADMIN限定）を新規追加。あわせて実装済みだが未反映だった`PUT`（編集）・`GET /events/{eventId}/sessions`（一覧）・`GET .../last-settings`（直近設定取得）も表に追記 | Issue #42：成績登録画面のブラッシュアップの一環。半荘の誤登録を削除できる手段が無かったギャップの解消 |
| 2 | 8.3集計処理についての記述を実装（読み取り時にGameResultから都度集計）に合わせて修正。旧版の「登録時にその場で加算更新」は未実装のまま乖離していたため削除 | ドキュメントと実装の食い違い解消 |
| 3 | 8.4 IAM最小権限に`DeleteItem`/`TransactWriteItems`を追加（削除機能でGameSession本体+GameResult+GameResultChipをまとめて削除するため）。あわせて実装済みの`GetItem`も明記 | 上記No.1と同一の決定事項 |

---

## v1.8 → v1.9 変更点サマリ

| No | 変更内容 | 対応する決定事項 |
|---|---|---|
| 1 | 8.2 ResultLambdaハンドラー表に`GET /communities/{communityId}/rankings`（F-805 コミュニティ内ランキング取得）を新規追加 | Issue #40：コミュニティ内ランキング表示機能の追加 |
| 2 | 8.3集計処理についてに、ランキング集計がGSI2への1回のQueryでコミュニティ×種目×期間の全対局データを取得しLambda側でグルーピング集計する方式を追記（メンバー一覧を起点にしないため退会済みメンバーも自動的に含まれる） | 上記と同一の決定事項 |
| 3 | 8.4 IAM最小権限に、GSI2への`Query`権限の新規追加を明記（v1.8時点のResultLambdaはGSI1のみ使用） | 上記と同一の決定事項 |
| 4 | 4.2 CommunityLambdaハンドラー表に`PUT /communities/{communityId}/ranking-settings`（F-806 コミュニティ内ランキング設定）を新規追加 | 上記と同一の決定事項 |
| 5 | 13章対応関係表のResultLambda行にF-805・要件定義書32章を追加 | 上記と同一の決定事項 |

Issue #40「コミュニティ内ランキング表示機能の追加」に対応。
